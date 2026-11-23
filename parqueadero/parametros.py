"""
Estimación de los parámetros del Montecarlo a partir del registro histórico.

Qué se estima (todo sale de los datos de octubre 2026):
  λ(t, h)  vehículos que llegan en la hora h en un día de tipo t (Lun–Jue, Viernes, Sábado, Domingo/festivo),
           separado en tres flujos: rotación (visitantes y convenios), mensualidades y proveedores.
  F_q(t)   aumento de la demanda en días de quincena.
  σ        variación aleatoria entre días del mismo tipo (factor del día Z ~ Normal(1, σ)).
  Mezcla   probabilidad de cada tipo de vehículo y cliente por hora y tipo de día.
  S        distribución empírica de la permanencia (percentiles 0 a 100) por grupo.
  Capacidad de cada zona (celdas) y tarifas.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import calendario as cal
from .datos import cargar_registro, cargar_tarifas, cobrar, tabla_sturges

HORAS = list(range(7, 22))           # horas de llegada 07:00–21:59
HORAS_OCUP = list(range(7, 24))      # horas en que se mide la ocupación
CATS_ROT = [("Automóvil", "Visitante"), ("Automóvil", "Convenio"), ("Camioneta", "Visitante"),
            ("Camioneta", "Convenio"), ("Motocicleta", "Visitante"), ("Motocicleta", "Convenio")]
VEH_MEN = ["Automóvil", "Camioneta", "Motocicleta"]
FLUJOS = ["ROT", "MEN", "PRO"]
FLUJO_NOMBRE = {"ROT": "Rotación (visitantes y convenios)", "MEN": "Mensualidades", "PRO": "Proveedores (furgones)"}


def clave_estancia(cliente: str, grupo: str, clase_dia: str, franja: int) -> str:
    return f"{cliente}|{grupo}|{clase_dia}|{franja}"


def franja_de_hora(h: int) -> int:
    return 0 if h <= 11 else (1 if h <= 16 else 2)


@dataclass
class Parametros:
    lam: dict                      # flujo -> array (4 tipos, 15 horas)
    f_quincena: dict               # tipo -> factor
    sigma_dia: float
    mix_rot: np.ndarray            # (4, 15, 6)
    mix_men: np.ndarray            # (3,)
    estancias: dict                # clave -> percentiles (101)
    p_extraviado: float
    capacidad: dict                # A_rot, A_men, M_rot, M_men, C
    tarifas: dict
    ingreso_ref: dict              # (tipo, quincena) -> ingreso promedio del día en octubre
    cuota_hora: dict = field(default_factory=dict)   # tipo -> fracción del ingreso del día según la hora de llegada (15)
    historico: dict = field(default_factory=dict)
    fuente: str = ""


def _conteo_hora(df: pd.DataFrame, fechas: list) -> pd.DataFrame:
    m = df.groupby(["fecha", "hora"]).size().unstack(fill_value=0)
    return m.reindex(index=fechas, columns=HORAS, fill_value=0)


def ocupacion_max_por_hora(entradas: np.ndarray, salidas: np.ndarray) -> np.ndarray:
    """Máximo de vehículos dentro en cada hora 07–23 a partir de horas de entrada y salida (en horas)."""
    e = np.sort(entradas)
    s = np.sort(np.where(np.isnan(salidas), 1e9, salidas))
    occ_inicio = np.array([np.searchsorted(e, h, "right") - np.searchsorted(s, h, "right") for h in HORAS_OCUP])
    hmax = occ_inicio.copy()
    if len(e):
        occ_e = np.arange(1, len(e) + 1) - np.searchsorted(s, e, "right")
        idx = np.clip(np.floor(e).astype(int) - 7, 0, len(HORAS_OCUP) - 1)
        np.maximum.at(hmax, idx, occ_e)
    return hmax


def estimar(df: pd.DataFrame, tarifas: dict, fuente: str = "") -> Parametros:
    df = df.copy()
    fechas = sorted(df["fecha"].unique())
    info = {f: cal.clasificar(f) for f in fechas}
    tipo = {f: info[f].tipo for f in fechas}
    quinc = {f: info[f].quincena for f in fechas}
    fact = {f: info[f].factor_temporada for f in fechas}      # se "desestacionaliza" cada día histórico
    ti = {t: i for i, t in enumerate(cal.TIPOS)}

    conteos = {fl: _conteo_hora(df[df["flujo"] == fl], fechas) for fl in FLUJOS}
    rot = conteos["ROT"].div(pd.Series(fact), axis=0)

    lam = {fl: np.zeros((4, len(HORAS))) for fl in FLUJOS}
    for t in cal.TIPOS:
        base = [f for f in fechas if tipo[f] == t and not quinc[f]]
        todos = [f for f in fechas if tipo[f] == t]
        if base:
            lam["ROT"][ti[t]] = rot.loc[base].mean().values
        elif todos:
            lam["ROT"][ti[t]] = rot.loc[todos].mean().values
        if todos:
            lam["MEN"][ti[t]] = conteos["MEN"].loc[todos].mean().values
            lam["PRO"][ti[t]] = conteos["PRO"].loc[todos].mean().values

    # factor de quincena por tipo de día (con respaldo agrupado)
    real_tot, esp_tot, fq = 0.0, 0.0, {}
    for t in cal.TIPOS:
        qd = [f for f in fechas if tipo[f] == t and quinc[f]]
        if qd and lam["ROT"][ti[t]].sum() > 0:
            r = rot.loc[qd].values.sum(); e = lam["ROT"][ti[t]].sum() * len(qd)
            fq[t] = r / e; real_tot += r; esp_tot += e
    agrupado = real_tot / esp_tot if esp_tot else 1.0
    f_quincena = {t: round(float(fq.get(t, agrupado)), 4) for t in cal.TIPOS}

    # variabilidad entre días (factor Z): varianza extra sobre la de Poisson
    num = den = 0.0
    for t in cal.TIPOS:
        base = [f for f in fechas if tipo[f] == t and not quinc[f]]
        if len(base) > 1:
            tot = rot.loc[base].sum(axis=1)
            mu, var = tot.mean(), tot.var(ddof=1)
            num += max(0.0, (var - mu) / mu ** 2) * (len(base) - 1); den += len(base) - 1
    sigma = float(np.sqrt(num / den)) if den else 0.05

    # mezcla de vehículo y cliente (rotación) por tipo de día y hora
    r = df[df["flujo"] == "ROT"].copy()
    r["t"] = r["fecha"].map(tipo)
    r["cat"] = [CATS_ROT.index((v, c)) if (v, c) in CATS_ROT else -1 for v, c in zip(r["vehiculo"], r["cliente"])]
    mix = np.zeros((4, len(HORAS), len(CATS_ROT)))
    for t in cal.TIPOS:
        rt = r[r["t"] == t]
        general = np.bincount(rt["cat"][rt["cat"] >= 0], minlength=len(CATS_ROT)).astype(float)
        general = general / general.sum() if general.sum() else np.full(len(CATS_ROT), 1 / len(CATS_ROT))
        for j, h in enumerate(HORAS):
            c = np.bincount(rt.loc[rt["hora"] == h, "cat"].clip(lower=0), minlength=len(CATS_ROT)).astype(float)
            mix[ti[t], j] = c / c.sum() if c.sum() >= 20 else general
    men = df[df["flujo"] == "MEN"]["vehiculo"].value_counts()
    mix_men = np.array([men.get(v, 0) for v in VEH_MEN], dtype=float)
    mix_men = mix_men / mix_men.sum()

    # permanencias: percentiles 0..100 por grupo (transformada inversa empírica)
    q = np.linspace(0, 100, 101)
    d = df.dropna(subset=["permanencia_min"]).copy()
    d["clase"] = np.where(d["fecha"].map(tipo).isin(["SA", "DF"]), "FS", "ES")
    d["franja"] = d["hora"].map(franja_de_hora)
    d["grupo"] = np.where(d["vehiculo"] == "Motocicleta", "Moto", "Carro")
    est = {}
    for cli in ["Visitante", "Convenio"]:
        for g in ["Carro", "Moto"]:
            for cl in ["ES", "FS"]:
                sub = d[(d["flujo"] == "ROT") & (d["cliente"] == cli) & (d["grupo"] == g) & (d["clase"] == cl)]
                for fr in range(3):
                    x = sub[sub["franja"] == fr]["permanencia_min"]
                    if len(x) < 80:
                        x = sub["permanencia_min"]
                    if len(x) < 20:
                        x = d[(d["flujo"] == "ROT") & (d["grupo"] == g)]["permanencia_min"]
                    est[clave_estancia(cli, g, cl, fr)] = np.percentile(x, q)
    for g in ["Carro", "Moto"]:
        x = d[(d["flujo"] == "MEN") & (d["grupo"] == g)]["permanencia_min"]
        est[f"Mensualidad|{g}"] = np.percentile(x if len(x) else d["permanencia_min"], q)
    x = d[d["flujo"] == "PRO"]["permanencia_min"]
    est["Proveedor|Furgón"] = np.percentile(x if len(x) else d["permanencia_min"], q)

    # capacidad por zona según la numeración de celdas
    num = df["celda"].astype(str).str.extract(r"([A-Z])-(\d+)")
    num.columns = ["z", "n"]; num["n"] = pd.to_numeric(num["n"], errors="coerce")
    num["men"] = df["cliente"].eq("Mensualidad")
    cap_total = num.groupby("z")["n"].max()
    cap_men = num[num["men"]].groupby("z")["n"].max()
    capacidad = {
        "A_rot": int(cap_total.get("A", 400) - cap_men.get("A", 0)), "A_men": int(cap_men.get("A", 0)),
        "M_rot": int(cap_total.get("M", 90) - cap_men.get("M", 0)), "M_men": int(cap_men.get("M", 0)),
        "C": int(cap_total.get("C", 6)),
    }

    # ingreso de referencia por día (comportamiento de octubre) para la meta
    df["valor"] = cobrar(df["permanencia_min"], df["vehiculo"], df["cliente"], df["extraviado"], tarifas)
    diario = df.groupby("fecha").agg(vehiculos=("ticket", "size"), ingreso=("valor", "sum"))
    diario["tipo"] = [tipo[f] for f in diario.index]
    diario["quincena"] = [quinc[f] for f in diario.index]
    ing_ref = {}
    for t in cal.TIPOS:
        for qq in (False, True):
            sel = diario[(diario["tipo"] == t) & (diario["quincena"] == qq)]["ingreso"]
            if len(sel) == 0:
                sel = diario[diario["tipo"] == t]["ingreso"]
            ing_ref[(t, qq)] = float(sel.mean()) if len(sel) else float(diario["ingreso"].mean())
    # qué parte del ingreso diario aporta cada hora de llegada (sirve para la meta de una franja horaria)
    tipo_fila = df["fecha"].map(tipo)
    cuota = {}
    for t in cal.TIPOS:
        v = df[tipo_fila == t].groupby("hora")["valor"].sum().reindex(HORAS, fill_value=0.0).values
        if v.sum() == 0:
            v = df.groupby("hora")["valor"].sum().reindex(HORAS, fill_value=0.0).values
        cuota[t] = v / v.sum()

    p = Parametros(lam=lam, f_quincena=f_quincena, sigma_dia=round(sigma, 4), mix_rot=mix, mix_men=mix_men,
                   estancias=est, p_extraviado=float(df["extraviado"].mean()), capacidad=capacidad, tarifas=tarifas,
                   ingreso_ref=ing_ref, cuota_hora=cuota, fuente=fuente)
    p.historico = historico(df, info)
    return p


def historico(df: pd.DataFrame, info: dict) -> dict:
    """Resúmenes del registro real para comparar y para los mapas de calor históricos."""
    fechas = sorted(info)
    df = df.copy()
    df["dia_semana"] = df["entrada"].dt.weekday
    df["h_sal"] = df["salida"].dt.hour
    df["dsem_sal"] = df["salida"].dt.weekday
    diario = []
    occ_fecha = {}
    for f in fechas:
        sub = df[df["fecha"] == f]
        e = (sub["entrada"] - pd.Timestamp(f)).dt.total_seconds().values / 3600
        s = (sub["salida"] - pd.Timestamp(f)).dt.total_seconds().values / 3600
        a_rot = ((sub["zona"] == "A") & (sub["flujo"] != "MEN")).values
        occ = ocupacion_max_por_hora(e[a_rot], s[a_rot])
        occ_fecha[f] = occ
        i = info[f]
        diario.append(dict(fecha=f, dia=cal.DIA_SEMANA[f.weekday()], tipo=cal.TIPO_NOMBRE[i.tipo],
                           festivo=i.festivo["nombre"] if i.festivo else "", quincena=i.quincena, puente=i.puente or "",
                           evento=", ".join(ev.nombre for ev in i.eventos), vehiculos=len(sub),
                           rotacion=int((sub["flujo"] == "ROT").sum()), mensualidad=int((sub["flujo"] == "MEN").sum()),
                           proveedores=int((sub["flujo"] == "PRO").sum()), ingreso=float(sub["valor"].sum()),
                           pico_carros=int(occ.max())))
    diario = pd.DataFrame(diario)
    n_dias = diario.groupby("dia").size()
    ent = df.groupby(["dia_semana", "hora"]).size().unstack(fill_value=0).reindex(index=range(7), columns=range(7, 24), fill_value=0)
    sal = df.groupby(["dsem_sal", "h_sal"]).size().unstack(fill_value=0).reindex(index=range(7), columns=range(7, 24), fill_value=0)
    dias_por = np.array([n_dias.get(cal.DIA_SEMANA[w], 1) for w in range(7)])[:, None]
    occ_dsem = np.zeros((7, len(HORAS_OCUP))); cnt = np.zeros(7)
    for f, occ in occ_fecha.items():
        occ_dsem[f.weekday()] += occ; cnt[f.weekday()] += 1
    occ_dsem /= np.maximum(cnt, 1)[:, None]
    idx = cal.DIA_SEMANA
    cols = [f"{h:02d}:00" for h in HORAS_OCUP]
    sturges, sturges_info = tabla_sturges(df["hora_decimal"])
    por_tipo = diario.groupby("tipo")["vehiculos"].agg(["count", "mean", "std", "min", "max"]).round(1)
    return dict(
        diario=diario,
        entradas_dsem_hora=pd.DataFrame(ent.values / dias_por, index=idx, columns=cols),
        salidas_dsem_hora=pd.DataFrame(sal.values / dias_por, index=idx, columns=cols),
        ocupacion_dsem_hora=pd.DataFrame(occ_dsem, index=idx, columns=cols),
        entradas_fecha_hora=pd.DataFrame(np.array([[((df["fecha"] == f) & (df["hora"] == h)).sum() for h in HORAS] for f in fechas]),
                                         index=[info[f].etiqueta for f in fechas], columns=[f"{h:02d}:00" for h in HORAS]),
        sturges=sturges, sturges_info=sturges_info, por_tipo=por_tipo, n=len(df),
        periodo=(min(fechas), max(fechas)),
    )


def cargar_y_estimar(ruta) -> tuple[pd.DataFrame, Parametros]:
    df = cargar_registro(ruta)
    tar = cargar_tarifas(ruta)
    return df, estimar(df, tar, fuente=str(ruta))
