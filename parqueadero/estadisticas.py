"""
Estadísticas de la simulación: KPIs, resumen por día, mapas de calor por hora, picos y valles,
Sturges de las llegadas simuladas, riesgo de pérdida de ingresos y validación con el histórico.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from . import calendario as cal
from .datos import tabla_sturges
from .motor import Config, Resultado, simular
from .parametros import HORAS, HORAS_OCUP, Parametros

COL_H = [f"{h:02d}:00" for h in HORAS]
COL_O = [f"{h:02d}:00" for h in HORAS_OCUP]


def _pct(a, q):
    return np.percentile(a, q, axis=0)


def resumen(res: Resultado, P: Parametros) -> dict:
    RD, DH, R, D = res.RD, res.DH, res.cfg.replicas, len(res.dias)
    cap = res.capacidad

    # -------- por día --------
    filas = []
    for d, info in enumerate(res.dias):
        lleg = RD["llegadas"][:, d]; ing = RD["ingreso"][:, d]
        esp_n = RD["esperan"][:, d].sum()
        hp = int(np.argmax(DH["llegadas"][d])); ho = int(np.argmax(DH["occ_carros"][d]))
        filas.append({
            "Fecha": info.fecha, "Día": info.etiqueta, "Día de la semana": cal.DIA_SEMANA[info.fecha.weekday()],
            "Tipo de día": cal.TIPO_NOMBRE[info.tipo], "Festivo": info.festivo["nombre"] if info.festivo else "",
            "Quincena": "Sí" if info.quincena else "", "Puente": info.puente or "", "Temporada": info.temporada,
            "Factor de temporada": round(info.factor_temporada, 3), "Eventos": ", ".join(e.nombre for e in info.eventos),
            "Llegadas (media)": lleg.mean(), "Llegadas P5": np.percentile(lleg, 5), "Llegadas P95": np.percentile(lleg, 95),
            "Entradas (media)": RD["atendidos"][:, d].mean(),
            "Sin cupo (media)": (RD["rech_carros"][:, d] + RD["rech_motos"][:, d]).mean(),
            "Prob. carros llenos": RD["lleno_carros"][:, d].mean(), "Prob. motos llenas": RD["lleno_motos"][:, d].mean(),
            "Prob. muelle lleno": RD["lleno_muelle"][:, d].mean(),
            "Pico carros (media)": RD["pico_carros"][:, d].mean(), "Pico carros P95": np.percentile(RD["pico_carros"][:, d], 95),
            "% ocupación pico": RD["pico_carros"][:, d].mean() / cap["A_rot"],
            "Espera prom. (min)": RD["espera_min"][:, d].sum() / esp_n if esp_n else 0.0,
            "Ingreso (media)": ing.mean(), "Ingreso P5": np.percentile(ing, 5), "Ingreso P95": np.percentile(ing, 95),
            "Ingreso perdido (media)": RD["ingreso_perdido"][:, d].mean(), "Meta del día": RD["meta"][0, d],
            "Prob. ingreso < meta": (ing < RD["meta"][:, d]).mean(),
            "Ingreso en la franja (media)": RD["ingreso_franja"][:, d].mean(), "Meta de la franja": RD["meta_franja"][0, d],
            "Prob. franja < meta": (RD["ingreso_franja"][:, d] < RD["meta_franja"][:, d]).mean(),
            "Pérdida por cupo en la franja": RD["perdido_franja"][:, d].mean(),
            "Hora pico llegadas": f"{HORAS[hp]:02d}:00", "Hora pico ocupación": f"{HORAS_OCUP[ho]:02d}:00",
        })
    dias = pd.DataFrame(filas)
    if len(dias) >= 4:
        q75, q25 = dias["Llegadas (media)"].quantile([.75, .25])
        dias["Nivel"] = np.where(dias["Llegadas (media)"] >= q75, "Pico", np.where(dias["Llegadas (media)"] <= q25, "Valle", "Normal"))
    else:
        dias["Nivel"] = "Normal"

    # -------- mapas de calor --------
    etiquetas = [i.etiqueta for i in res.dias]
    mapas_fecha = {
        "Llegadas por hora": pd.DataFrame(DH["llegadas"] / R, index=etiquetas, columns=COL_H),
        "Entradas por hora": pd.DataFrame(DH["entradas"] / R, index=etiquetas, columns=COL_O),
        "Salidas por hora": pd.DataFrame(DH["salidas"] / R, index=etiquetas, columns=COL_O),
        "Ocupación de carros (%)": pd.DataFrame(100 * DH["occ_carros"] / R / cap["A_rot"], index=etiquetas, columns=COL_O),
        "Ocupación de motos (%)": pd.DataFrame(100 * DH["occ_motos"] / R / max(1, cap["M_rot"]), index=etiquetas, columns=COL_O),
        "Probabilidad de carros llenos (%)": pd.DataFrame(100 * DH["lleno_carros"] / R, index=etiquetas, columns=COL_O),
        "Vehículos sin cupo por hora": pd.DataFrame(DH["rechazos"] / R, index=etiquetas, columns=COL_H),
    }
    dsem = np.array([i.fecha.weekday() for i in res.dias])
    mapas_dsem = {}
    for nombre, m in mapas_fecha.items():
        filas_d = {cal.DIA_SEMANA[w]: m.values[dsem == w].mean(axis=0) for w in range(7) if (dsem == w).any()}
        mapas_dsem[nombre] = pd.DataFrame(filas_d, index=m.columns).T

    # -------- perfil horario (entradas vs salidas) --------
    perfil = pd.DataFrame({"Entradas": DH["entradas"].sum(0) / R / D, "Salidas": DH["salidas"].sum(0) / R / D,
                           "Ocupación carros": DH["occ_carros"].sum(0) / R / D, "Ocupación total": DH["occ_total"].sum(0) / R / D},
                          index=COL_O)
    perfil["Flujo neto (entradas − salidas)"] = perfil["Entradas"] - perfil["Salidas"]
    tipos = np.array([i.tipo for i in res.dias])
    perfil_tipo = {cal.TIPO_NOMBRE[t]: pd.DataFrame({"Entradas": DH["entradas"][tipos == t].mean(0) / R,
                                                      "Salidas": DH["salidas"][tipos == t].mean(0) / R,
                                                      "Ocupación carros": DH["occ_carros"][tipos == t].mean(0) / R}, index=COL_O)
                   for t in cal.TIPOS if (tipos == t).any()}

    # -------- picos y valles de horas --------
    lleg_h = DH["llegadas"].sum(0) / R / D
    mx = lleg_h.max()
    horas = pd.DataFrame({"Hora": COL_H, "Llegadas promedio": lleg_h,
                          "Nivel": np.where(lleg_h >= 0.8 * mx, "Pico", np.where(lleg_h <= 0.35 * mx, "Valle", "Normal"))})

    # -------- Sturges de las llegadas simuladas --------
    sturges, st_info = tabla_sturges(res.llegadas_muestra) if len(res.llegadas_muestra) > 10 else (pd.DataFrame(), {})

    # -------- riesgo de pérdida de ingresos (lapso = días seleccionados × franja horaria) --------
    ing_tot = RD["ingreso_franja"].sum(1)
    perd_tot = RD["perdido_franja"].sum(1)
    meta_tot = res.cfg.meta_fija if res.cfg.meta_fija else RD["meta_franja"][0].sum()
    falt = np.maximum(0, meta_tot - ing_tot)
    se = ing_tot.std(ddof=1) / np.sqrt(R) if R > 1 else 0
    riesgo = {
        "ingreso_media": ing_tot.mean(), "ingreso_sd": ing_tot.std(ddof=1) if R > 1 else 0, "ingreso_p5": np.percentile(ing_tot, 5),
        "ingreso_p50": np.percentile(ing_tot, 50), "ingreso_p95": np.percentile(ing_tot, 95), "ic95": (ing_tot.mean() - 1.96 * se, ing_tot.mean() + 1.96 * se),
        "error_estandar": se, "meta": meta_tot, "prob_bajo_meta": (ing_tot < meta_tot).mean(), "faltante_esperado": falt.mean(),
        "var95_faltante": np.percentile(falt, 95), "ingreso_en_riesgo": ing_tot.mean() - np.percentile(ing_tot, 5),
        "prob_perdida_cupo": (perd_tot > 0).mean(), "perdida_cupo_media": perd_tot.mean(), "perdida_cupo_p95": np.percentile(perd_tot, 95),
        "ingreso_por_replica": ing_tot, "perdida_por_replica": perd_tot, "faltante_por_replica": falt,
        "convergencia": np.cumsum(ing_tot) / np.arange(1, R + 1),
        "franja": f"{res.cfg.franja[0]:02d}:00 – {res.cfg.franja[1]:02d}:00", "dias": D,
        "ingreso_dia_completo": RD["ingreso"].sum(1).mean(),
    }
    rel_cupo = riesgo["perdida_cupo_p95"] / riesgo["ingreso_media"] if riesgo["ingreso_media"] else 0
    riesgo["perdida_cupo_pct"] = rel_cupo
    riesgo["nivel_cupo"] = "Alto" if rel_cupo >= .05 else ("Medio" if rel_cupo >= .01 else "Bajo")
    rel = riesgo["var95_faltante"] / meta_tot if meta_tot else 0
    riesgo["var95_pct_meta"] = rel
    riesgo["nivel_meta"] = "Alto" if rel >= .10 else ("Medio" if rel >= .05 else "Bajo")

    # -------- parqueadero externo --------
    ex = res.cfg.externo
    ben_dia = RD["ext_ingreso"] - ex["costo_var"] * RD["ext_captados"] - ex["costo_fijo"]      # (R, D)
    sel = ben_dia.mean(0) > 0
    ben_sel = ben_dia[:, sel].sum(1) if sel.any() else np.zeros(R)
    externo = {"dias_rentables": [res.dias[i].etiqueta for i in np.where(sel)[0]], "beneficio_todo": ben_dia.sum(1).mean(),
               "beneficio_sel": ben_sel.mean(), "prob_ganar_sel": (ben_sel > 0).mean() if sel.any() else 0.0,
               "decision": ("VIABLE SOLO EN DÍAS PICO" if sel.sum() < D else "VIABLE TODO EL PERIODO") if sel.any() and (ben_sel > 0).mean() >= .75
               else ("VIABLE CON RIESGO" if sel.any() else "NO VIABLE")}

    # -------- KPIs --------
    lleg_tot = RD["llegadas"].sum(1)
    esp_n, esp_m = RD["esperan"].sum(), RD["espera_min"].sum()
    kpi = {
        "dias": D, "replicas": R, "jornadas": R * D,
        "llegadas_total": lleg_tot.mean(), "llegadas_ic": (np.percentile(lleg_tot, 2.5), np.percentile(lleg_tot, 97.5)),
        "llegadas_dia": lleg_tot.mean() / D, "entradas_total": RD["atendidos"].sum(1).mean(),
        "sin_cupo_total": (RD["rech_carros"] + RD["rech_motos"]).sum(1).mean(),
        "prob_carros_llenos": RD["lleno_carros"].mean(), "prob_motos_llenas": RD["lleno_motos"].mean(), "prob_muelle_lleno": RD["lleno_muelle"].mean(),
        "ocupacion_pico": dias["% ocupación pico"].max(), "dia_ocupacion_pico": dias.loc[dias["% ocupación pico"].idxmax(), "Día"],
        "pico_p95": dias["Pico carros P95"].max(), "espera_prom": esp_m / esp_n if esp_n else 0.0,
        "pct_esperan": esp_n / max(1, RD["llegadas"].sum()), "permanencia_prom": RD["permanencia_sum"].sum() / max(1, RD["atendidos"].sum()),
        "utilizacion": (DH["occ_carros"].sum() / R) / (cap["A_rot"] * NO_HORAS * D),
        "max_tx_hora": np.percentile(RD["max_tx"], 90),
    }
    return dict(dias=dias, mapas_fecha=mapas_fecha, mapas_dsem=mapas_dsem, perfil=perfil, perfil_tipo=perfil_tipo, horas=horas,
                sturges=sturges, sturges_info=st_info, riesgo=riesgo, externo=externo, kpi=kpi)


NO_HORAS = len(HORAS_OCUP)


def recomendaciones(S: dict) -> list[str]:
    """Frases de acción a partir de los resultados (se usan en la interfaz y en el Excel)."""
    k, d, h, e = S["kpi"], S["dias"], S["horas"], S["externo"]
    pct = lambda v: f"{100 * v:.1f} %".replace(".", ",")
    out = []
    if k["prob_carros_llenos"] > 0.10:
        criticos = d[d["Prob. carros llenos"] > 0.5]["Día"].tolist()
        out.append(f"Riesgo de lleno en la zona de carros: ocurre en {pct(k['prob_carros_llenos'])} de las jornadas. "
                   f"Días críticos (más de 50 %): {', '.join(criticos) or 'ninguno'}.")
    else:
        out.append(f"La zona de carros casi nunca se llena ({pct(k['prob_carros_llenos'])} de las jornadas): la capacidad actual es suficiente.")
    if k["prob_muelle_lleno"] > 0.10:
        out.append(f"El muelle de carga se llena en {pct(k['prob_muelle_lleno'])} de las jornadas: conviene programar turnos de proveedores.")
    if k["espera_prom"] > 5:
        out.append(f"Quien espera lo hace {k['espera_prom']:.1f} min en promedio: reforzar el personal de entrada en las horas pico.")
    hp = ", ".join(h[h["Nivel"] == "Pico"]["Hora"])
    hv = ", ".join(h[h["Nivel"] == "Valle"]["Hora"])
    out.append(f"Concentrar personal de caja y control en las horas pico ({hp}); las horas valle ({hv}) sirven para mantenimiento y cambios de turno.")
    out.append(f"Parqueadero externo: {e['decision'].lower()}"
               + (f" (días: {', '.join(e['dias_rentables'])})" if e["dias_rentables"] else "") + ".")
    return out


def validar(P: Parametros, replicas: int = 200, semilla: int = 12345) -> dict:
    """Simula los mismos días del histórico y compara llegadas diarias y ocupación pico con lo real."""
    hist = P.historico["diario"]
    fechas = list(hist["fecha"])
    res = simular(P, fechas, Config(replicas=replicas, semilla=semilla, guardar_registro=False))
    sim = res.RD["llegadas"]; p5, p95 = np.percentile(sim, 5, axis=0), np.percentile(sim, 95, axis=0)
    real = hist["vehiculos"].values
    tabla = pd.DataFrame({"Fecha": fechas, "Tipo": hist["tipo"], "Real": real, "Simulado (media)": sim.mean(0),
                          "P5": p5, "P95": p95, "Pico real carros": hist["pico_carros"], "Pico simulado carros": res.RD["pico_carros"].mean(0)})
    tabla["Error %"] = (tabla["Simulado (media)"] - tabla["Real"]).abs() / tabla["Real"]
    tabla["Dentro de P5–P95"] = (real >= p5) & (real <= p95)
    return dict(tabla=tabla, mape=tabla["Error %"].mean(), cobertura=tabla["Dentro de P5–P95"].mean(),
                mape_pico=((tabla["Pico simulado carros"] - tabla["Pico real carros"]).abs() / tabla["Pico real carros"]).mean(),
                total_real=int(real.sum()), total_sim=float(sim.mean(0).sum()))
