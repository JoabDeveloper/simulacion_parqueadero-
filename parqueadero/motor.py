"""
Motor de simulación de Montecarlo de ENTRADAS y SALIDAS de vehículos.

Para cada réplica r y cada día d seleccionado en el calendario:
  1. Factor aleatorio del día:     Z = 1 + σ·√(−2 ln U1)·cos(2π U2)            (Box–Muller)
  2. Tasa de cada hora h:          λ(h) = λ_t(h) · Z · (1 + g) · F_temporada(d) · F_quincena(t)
  3. Llegadas en la hora:          N(h) ~ Poisson(λ(h))  por transformada inversa de su acumulada
     Hora de llegada:              h + U   (en un proceso de Poisson las llegadas son uniformes en la hora)
  4. Tipo de vehículo y cliente:   U se ubica en la probabilidad acumulada de la mezcla (tabla de Montecarlo)
  5. Permanencia:                  S = F⁻¹(U)  con los percentiles 0..100 del grupo (transformada inversa empírica)
  6. ENTRADA: si hay celda libre en su zona entra; si está llena espera la primera SALIDA
     solo si ocurre dentro de su tolerancia; si no, se va (rechazo = ingreso perdido).
     SALIDA = entrada + permanencia.
  7. Se cobra la tarifa y se registran ocupación por hora, esperas, rechazos e ingresos.
Repetir R réplicas permite medir promedios, percentiles y probabilidades (riesgo).
"""
from __future__ import annotations

import datetime as dt
import heapq
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import calendario as cal
from .generador import crear_generador
from .parametros import CATS_ROT, HORAS, HORAS_OCUP, VEH_MEN, Parametros, franja_de_hora

VEH = ["Automóvil", "Camioneta", "Motocicleta", "Furgón"]
CLI = ["Visitante", "Convenio", "Mensualidad"]
ZONAS = ["A_rot", "M_rot", "A_men", "M_men", "C"]
ZONA_NOMBRE = {"A_rot": "Carros (rotación)", "M_rot": "Motos (rotación)", "A_men": "Carros (mensualidad)", "M_men": "Motos (mensualidad)", "C": "Muelle de carga"}
NH, NO = len(HORAS), len(HORAS_OCUP)


@dataclass
class Config:
    replicas: int = 300
    semilla: int = 12345
    generador: str = "congruencial"
    crecimiento: float = 0.0               # 0,25 = 25 % más demanda de rotación que octubre
    tolerancia_min: float = 10.0           # minutos que un conductor espera por una celda
    tolerancia_prov_min: float = 30.0      # minutos que espera un proveedor en el muelle
    capacidad: dict | None = None          # si es None se usa la de los datos
    tarifas: dict | None = None
    meta_pct: float = 1.0                  # meta = % del ingreso de referencia (comportamiento de octubre)
    meta_fija: float | None = None         # o una meta fija en COP para todos los días seleccionados
    meta_temporada: bool = True            # la meta de cada día se ajusta por su factor de temporada
    franja: tuple = (7, 22)                # lapso horario evaluado en el riesgo: llegadas desde (incl.) hasta (excl.)
    factores_mes: dict | None = None
    factores_eventos: dict | None = None
    factor_puente: float = 1.0
    externo: dict = field(default_factory=lambda: dict(carros=60, motos=20, aceptacion=0.6, factor_tarifa=1.0, costo_fijo=450000, costo_var=1500))
    guardar_registro: bool = True          # guarda cada vehículo de la réplica 1 (para ver entradas y salidas)


@dataclass
class Resultado:
    dias: list                 # DiaInfo de cada día simulado
    cfg: Config
    capacidad: dict
    RD: dict                   # métricas por réplica y día: arrays (R, D)
    DH: dict                   # sumas por día y hora: arrays (D, 15 o 17)
    registro: pd.DataFrame     # vehículos de la réplica 1
    llegadas_muestra: np.ndarray
    segundos: float
    generador: str


# ---------------------------------------------------------------------------
def poisson_inversa(lam: np.ndarray, u: np.ndarray) -> np.ndarray:
    """N = mínimo k tal que F(k) ≥ U, con F la acumulada de Poisson(λ) (transformada inversa discreta)."""
    lam = np.asarray(lam, float); u = np.asarray(u, float)
    n = np.zeros(lam.shape, dtype=np.int64)
    p = np.exp(-lam)
    F = p.copy()
    pendiente = u > F
    k = 0
    while pendiente.any() and k < 5000:
        k += 1
        p = p * lam / k
        F = F + p
        n[pendiente] = k
        pendiente &= u > F
    return n


def atender(llegada: np.ndarray, estancia: np.ndarray, cap: int, tolerancia: float):
    """
    Asigna celda a cada vehículo de una zona (tiempos en horas).
    Devuelve la hora de ENTRADA de cada uno (NaN si se fue sin parquear).
    Atajo exacto: si con entrada inmediata la ocupación nunca supera la capacidad, nadie espera.
    """
    n = len(llegada)
    entrada = np.full(n, np.nan)
    if n == 0:
        return entrada
    orden = np.argsort(llegada, kind="stable")
    a, s = llegada[orden], estancia[orden]
    if cap <= 0:
        return entrada
    ocup = np.arange(1, n + 1) - np.searchsorted(np.sort(a + s), a, side="right")
    if ocup.max() <= cap:
        entrada[orden] = a
        return entrada
    heap: list[float] = []          # horas de salida de los vehículos dentro (cola de prioridad)
    ent = np.full(n, np.nan)
    for i in range(n):
        t = a[i]
        while heap and heap[0] <= t:
            heapq.heappop(heap)                        # SALIDAS que ya ocurrieron liberan celdas
        if len(heap) < cap:
            heapq.heappush(heap, t + s[i]); ent[i] = t  # ENTRADA inmediata
        elif heap[0] - t <= tolerancia:
            libre = heap[0]
            heapq.heapreplace(heap, libre + s[i]); ent[i] = libre   # espera la primera salida
        # si no: rechazo (ent queda NaN)
    entrada[orden] = ent
    return entrada


def _ocupacion(entradas: np.ndarray, salidas: np.ndarray) -> np.ndarray:
    """Máximo de vehículos dentro en cada hora 07–23."""
    e = np.sort(entradas); s = np.sort(salidas)
    hmax = np.searchsorted(e, HORAS_OCUP, "right") - np.searchsorted(s, HORAS_OCUP, "right")
    if len(e):
        occ = np.arange(1, len(e) + 1) - np.searchsorted(s, e, "right")
        idx = np.clip(np.floor(e).astype(int) - 7, 0, NO - 1)
        np.maximum.at(hmax, idx, occ)
    return hmax


def _hist_horas(t: np.ndarray, desde: int, n: int) -> np.ndarray:
    idx = np.floor(t).astype(int) - desde
    idx = idx[(idx >= 0) & (idx < n)]
    return np.bincount(idx, minlength=n)


# ---------------------------------------------------------------------------
def simular(P: Parametros, fechas: list[dt.date], cfg: Config, progreso=None) -> Resultado:
    t0 = time.time()
    fechas = sorted(set(fechas))
    D, R = len(fechas), int(cfg.replicas)
    gen = crear_generador(cfg.generador, cfg.semilla)
    cap = dict(P.capacidad); cap.update(cfg.capacidad or {})
    tar = cfg.tarifas or P.tarifas
    ext = cfg.externo
    tol, tolp = cfg.tolerancia_min / 60, cfg.tolerancia_prov_min / 60
    dias = [cal.clasificar(f, cfg.factores_mes, cfg.factores_eventos, cfg.factor_puente) for f in fechas]
    ti = {t: i for i, t in enumerate(cal.TIPOS)}

    # tablas numéricas para vectorizar
    t_hora = np.array([tar["tarifa_hora"][v] for v in VEH], float)
    t_tope = np.array([tar["tope_24h"][v] for v in VEH], float)
    t_desc = np.array([tar["descuento"][c] for c in CLI], float)
    cat_veh = np.array([VEH.index(v) for v, _ in CATS_ROT]); cat_cli = np.array([CLI.index(c) for _, c in CATS_ROT])
    claves = list(P.estancias); Q = np.array([P.estancias[k] for k in claves]); kid = {k: i for i, k in enumerate(claves)}
    cum_men = np.cumsum(P.mix_men)

    F = lambda: np.zeros((R, D))
    RD = {k: F() for k in ["llegadas", "llegadas_rot", "atendidos", "rech_carros", "rech_motos", "rech_muelle", "rech_men",
                           "esperan", "espera_min", "esperan_muelle", "espera_muelle_min", "ingreso", "ingreso_perdido",
                           "ext_captados", "ext_ingreso", "pico_carros", "pico_motos", "pico_muelle", "lleno_carros",
                           "lleno_motos", "lleno_muelle", "max_tx", "permanencia_sum", "factor_z", "meta",
                           "llegadas_franja", "ingreso_franja", "perdido_franja", "meta_franja"]}
    DH = {"llegadas": np.zeros((D, NH)), "entradas": np.zeros((D, NO)), "salidas": np.zeros((D, NO)),
          "occ_carros": np.zeros((D, NO)), "occ_motos": np.zeros((D, NO)), "lleno_carros": np.zeros((D, NO)),
          "lleno_motos": np.zeros((D, NO)), "occ_total": np.zeros((D, NO)), "rechazos": np.zeros((D, NH))}
    registros, muestra = [], []

    def cobro(perm_min, v, c, extr):
        bruto = np.minimum(np.ceil(perm_min / 60) * t_hora[v], np.ceil(perm_min / 1440) * t_tope[v])
        bruto = np.where(perm_min <= tar["gracia_min"], 0.0, bruto)
        return bruto * (1 - t_desc[c]) + np.where(extr, tar["recargo_extravio"], 0.0)

    for di, info in enumerate(dias):
        t = ti[info.tipo]
        clase = "FS" if info.tipo in ("SA", "DF") else "ES"
        base_rot = P.lam["ROT"][t] * (1 + cfg.crecimiento) * info.factor_temporada * (P.f_quincena[info.tipo] if info.quincena else 1.0)
        cum_rot = np.cumsum(P.mix_rot[t], axis=1)
        # grupos de permanencia de la rotación por hora: índice de fila en Q
        gid_rot = np.array([[[kid[f"{cli}|{g}|{clase}|{franja_de_hora(h)}"] for h in HORAS] for g in ("Carro", "Moto")] for cli in ("Visitante", "Convenio")])
        meta_dia = P.ingreso_ref[(info.tipo, info.quincena)] * cfg.meta_pct * (info.factor_temporada if cfg.meta_temporada else 1.0)
        f0, f1 = cfg.franja
        cuota = P.cuota_hora.get(info.tipo) if P.cuota_hora else None
        meta_franja = meta_dia * (cuota[max(0, f0 - 7):max(0, f1 - 7)].sum() if cuota is not None else (f1 - f0) / NH)

        # --- 1 y 2: factor del día y número de llegadas por hora (todas las réplicas a la vez) ---
        u1, u2 = gen.random(R), gen.random(R)
        u1 = np.maximum(u1, 1e-12)
        Z = np.clip(1 + P.sigma_dia * np.sqrt(-2 * np.log(u1)) * np.cos(2 * np.pi * u2), 0.5, 1.5)
        lam = np.concatenate([np.outer(Z, base_rot), np.tile(P.lam["MEN"][t], (R, 1)), np.tile(P.lam["PRO"][t], (R, 1))], axis=1)
        N = poisson_inversa(lam, gen.random(R * 3 * NH).reshape(R, 3 * NH))

        horas3 = np.tile(np.array(HORAS), 3)
        flujo3 = np.repeat(np.arange(3), NH)
        for r in range(R):
            n = int(N[r].sum())
            hora = np.repeat(horas3, N[r]); flujo = np.repeat(flujo3, N[r])
            jh = hora - 7
            u = gen.random(5 * n).reshape(5, n) if n else np.zeros((5, 0))
            llegada = hora + u[0]
            v = np.empty(n, int); c = np.empty(n, int); g = np.empty(n, int)
            es_rot, es_men, es_pro = flujo == 0, flujo == 1, flujo == 2
            # --- 4: tipo de vehículo y cliente (tabla de Montecarlo por hora) ---
            cat = np.minimum((u[1][es_rot, None] > cum_rot[jh[es_rot]]).sum(axis=1), len(CATS_ROT) - 1)
            v[es_rot] = cat_veh[cat]; c[es_rot] = cat_cli[cat]
            vm = np.minimum(np.searchsorted(cum_men, u[1][es_men]), 2)
            v[es_men] = vm; c[es_men] = 2                  # mismo orden: Automóvil, Camioneta, Motocicleta
            v[es_pro] = 3; c[es_pro] = 0
            moto = v == 2
            # --- 5: permanencia por transformada inversa empírica ---
            g[es_rot] = gid_rot[c[es_rot], moto[es_rot].astype(int), jh[es_rot]]
            g[es_men] = np.where(moto[es_men], kid["Mensualidad|Moto"], kid["Mensualidad|Carro"])
            g[es_pro] = kid["Proveedor|Furgón"]
            x = u[2] * 100; i0 = np.minimum(x.astype(int), 99); fr = x - i0
            perm = Q[g, i0] + fr * (Q[g, i0 + 1] - Q[g, i0])           # minutos
            extr = u[3] < P.p_extraviado
            valor = cobro(perm, v, c, extr)
            est_h = perm / 60

            # --- 6: entradas y salidas por zona ---
            entrada = np.full(n, np.nan)
            zona = np.where(es_pro, "C", np.where(es_men, np.where(moto, "M_men", "A_men"), np.where(moto, "M_rot", "A_rot")))
            for zm, zr in (("A_men", "A_rot"), ("M_men", "M_rot")):
                sel = np.where(zona == zm)[0]
                e = atender(llegada[sel], est_h[sel], cap[zm], tol)
                entrada[sel] = e
                zona[sel[np.isnan(e)]] = zr                              # mensualidad sin celda fija usa rotación
            for zr in ("A_rot", "M_rot", "C"):
                sel = np.where(zona == zr)[0]
                entrada[sel] = atender(llegada[sel], est_h[sel], cap[zr], tolp if zr == "C" else tol)
            salida = entrada + est_h
            ok = ~np.isnan(entrada)
            rech = ~ok
            # parqueadero externo para los rechazados de rotación
            capt = np.zeros(n, bool)
            cand = np.where(rech & (zona != "C"))[0]
            if len(cand):
                acepta = cand[u[4][cand] < ext["aceptacion"]]
                for zc, capx in (("A", ext["carros"]), ("M", ext["motos"])):
                    s2 = acepta[np.char.startswith(zona[acepta].astype(str), zc)]
                    if len(s2):
                        capt[s2] = ~np.isnan(atender(llegada[s2], est_h[s2], int(capx), 0.0))

            # --- 7: indicadores de la jornada ---
            espera = np.where(ok, (entrada - llegada) * 60, 0.0)
            muelle = zona == "C"
            k = r, di
            RD["llegadas"][k] = n; RD["llegadas_rot"][k] = es_rot.sum(); RD["atendidos"][k] = ok.sum()
            RD["rech_carros"][k] = (rech & (zona == "A_rot")).sum(); RD["rech_motos"][k] = (rech & (zona == "M_rot")).sum()
            RD["rech_muelle"][k] = (rech & muelle).sum(); RD["rech_men"][k] = (rech & es_men).sum()
            w = ok & ~muelle & (espera > 1e-6)
            RD["esperan"][k] = w.sum(); RD["espera_min"][k] = espera[w].sum()
            wm = ok & muelle & (espera > 1e-6)
            RD["esperan_muelle"][k] = wm.sum(); RD["espera_muelle_min"][k] = espera[wm].sum()
            RD["ingreso"][k] = valor[ok].sum(); RD["ingreso_perdido"][k] = valor[rech].sum()
            RD["ext_captados"][k] = capt.sum(); RD["ext_ingreso"][k] = (valor[capt] * ext["factor_tarifa"]).sum()
            RD["permanencia_sum"][k] = perm[ok].sum(); RD["factor_z"][k] = Z[r]; RD["meta"][k] = meta_dia
            en_fr = (hora >= f0) & (hora < f1)
            RD["llegadas_franja"][k] = en_fr.sum(); RD["ingreso_franja"][k] = valor[ok & en_fr].sum()
            RD["perdido_franja"][k] = valor[rech & en_fr].sum(); RD["meta_franja"][k] = meta_franja
            occ = {}
            for zz, key in (("A_rot", "carros"), ("M_rot", "motos"), ("C", "muelle")):
                m = ok & (zona == zz)
                occ[key] = _ocupacion(entrada[m], salida[m])
                RD[f"pico_{key}"][k] = occ[key].max()
                RD[f"lleno_{key}"][k] = float(occ[key].max() >= cap[zz])
            occ_t = _ocupacion(entrada[ok], salida[ok])
            ent_h = _hist_horas(entrada[ok], 7, NO); sal_h = _hist_horas(salida[ok], 7, NO)
            RD["max_tx"][k] = (ent_h + sal_h).max()
            DH["llegadas"][di] += _hist_horas(llegada, 7, NH)
            DH["rechazos"][di] += _hist_horas(llegada[rech], 7, NH)
            DH["entradas"][di] += ent_h; DH["salidas"][di] += sal_h
            DH["occ_carros"][di] += occ["carros"]; DH["occ_motos"][di] += occ["motos"]; DH["occ_total"][di] += occ_t
            DH["lleno_carros"][di] += occ["carros"] >= cap["A_rot"]; DH["lleno_motos"][di] += occ["motos"] >= cap["M_rot"]

            if r == 0:
                muestra.append(llegada)
                if cfg.guardar_registro:
                    estado = np.where(ok, np.where(espera > 1e-6, "Entró tras esperar", "Entró"), np.where(capt, "Al parqueadero externo", "Se fue sin cupo"))
                    registros.append(pd.DataFrame({
                        "fecha": info.fecha, "vehiculo_id": np.arange(1, n + 1), "flujo": np.array(["Rotación", "Mensualidad", "Proveedor"])[flujo],
                        "tipo_vehiculo": np.array(VEH)[v], "tipo_cliente": np.array(CLI)[c], "zona": [ZONA_NOMBRE[zz] for zz in zona],
                        "llegada_h": llegada, "entrada_h": entrada, "salida_h": salida, "permanencia_min": perm,
                        "espera_min": np.where(ok, espera, np.nan), "estado": estado, "valor_cop": np.where(ok, valor, 0.0),
                    }).sort_values("llegada_h").assign(vehiculo_id=lambda d: np.arange(1, len(d) + 1)))
        if progreso:
            progreso((di + 1) / D)

    registro = pd.concat(registros, ignore_index=True) if registros else pd.DataFrame()
    return Resultado(dias=dias, cfg=cfg, capacidad=cap, RD=RD, DH=DH, registro=registro,
                     llegadas_muestra=np.concatenate(muestra) if muestra else np.array([]),
                     segundos=time.time() - t0, generador=gen.nombre)
