"""
Lectura y limpieza del registro de movimientos del parqueadero (hoja "Registro" del Excel).
Cada fila es un vehículo: fecha y hora de entrada, fecha y hora de salida, tipo, cliente, celda.
"""
from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import numpy as np
import pandas as pd

COLUMNAS = {
    "N° ticket": "ticket", "Fecha entrada": "fecha_entrada", "Hora entrada": "hora_entrada",
    "Tipo de vehículo": "vehiculo", "Tipo de cliente": "cliente", "Celda": "celda",
    "Fecha salida": "fecha_salida", "Hora salida": "hora_salida", "Ticket extraviado": "extraviado",
    "Medio de pago": "medio_pago",
}

# Tarifas por defecto: el archivo original no traía la hoja "Tarifas" (sus fórmulas daban #REF!).
TARIFAS_DEFECTO = {
    "tarifa_hora": {"Automóvil": 4000, "Camioneta": 4500, "Motocicleta": 2000, "Furgón": 6000},
    "tope_24h": {"Automóvil": 32000, "Camioneta": 36000, "Motocicleta": 16000, "Furgón": 48000},
    "descuento": {"Visitante": 0.0, "Convenio": 0.40, "Mensualidad": 1.0},
    "gracia_min": 15,
    "recargo_extravio": 15000,
}


def _combinar(fecha: pd.Series, hora: pd.Series) -> pd.Series:
    texto = hora.astype(str).where(hora.notna(), None)
    return pd.to_datetime(fecha, errors="coerce") + pd.to_timedelta(texto, errors="coerce")


def cargar_registro(ruta: str | Path) -> pd.DataFrame:
    """Lee la hoja Registro y agrega columnas útiles para la simulación."""
    crudo = pd.read_excel(ruta, sheet_name="Registro", usecols=list(COLUMNAS))
    df = crudo.rename(columns=COLUMNAS)
    df["entrada"] = _combinar(df["fecha_entrada"], df["hora_entrada"])
    df["salida"] = _combinar(df["fecha_salida"], df["hora_salida"])
    df = df.dropna(subset=["entrada"]).copy()
    df["permanencia_min"] = (df["salida"] - df["entrada"]).dt.total_seconds() / 60
    df["fecha"] = df["entrada"].dt.date
    df["hora"] = df["entrada"].dt.hour
    df["hora_decimal"] = df["entrada"].dt.hour + df["entrada"].dt.minute / 60 + df["entrada"].dt.second / 3600
    df["zona"] = df["celda"].astype(str).str[0]
    df["flujo"] = np.where(df["cliente"] == "Mensualidad", "MEN", np.where(df["vehiculo"] == "Furgón", "PRO", "ROT"))
    df["extraviado"] = df["extraviado"].astype(str).str.strip().eq("Sí")
    return df.reset_index(drop=True)


def cargar_tarifas(ruta: str | Path) -> dict:
    """Si el libro trae la hoja Tarifas (versión reparada) la usa; si no, usa los supuestos por defecto."""
    tar = {k: (dict(v) if isinstance(v, dict) else v) for k, v in TARIFAS_DEFECTO.items()}
    try:
        t = pd.read_excel(ruta, sheet_name="Tarifas", header=None, nrows=23, usecols="A:C")
    except Exception:
        return tar
    try:
        for i in range(4, 8):
            veh = str(t.iat[i, 0]).strip()
            if veh in tar["tarifa_hora"]:
                tar["tarifa_hora"][veh] = float(t.iat[i, 1]); tar["tope_24h"][veh] = float(t.iat[i, 2])
        for i in range(10, 13):
            cli = str(t.iat[i, 0]).strip()
            if cli in tar["descuento"]:
                tar["descuento"][cli] = float(t.iat[i, 1])
        tar["gracia_min"] = float(t.iat[15, 1]); tar["recargo_extravio"] = float(t.iat[16, 1])
    except Exception:
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in TARIFAS_DEFECTO.items()}
    return tar


def cobrar(permanencia_min, vehiculo, cliente, extraviado, tarifas: dict) -> np.ndarray:
    """Valor a pagar: hora o fracción, tope por cada 24 h, gracia, descuento por cliente y recargo."""
    p = np.asarray(permanencia_min, dtype=float)
    veh = np.asarray(vehiculo); cli = np.asarray(cliente)
    hora = np.vectorize(tarifas["tarifa_hora"].get)(veh).astype(float)
    tope = np.vectorize(tarifas["tope_24h"].get)(veh).astype(float)
    desc = np.vectorize(tarifas["descuento"].get)(cli).astype(float)
    bruto = np.minimum(np.ceil(p / 60) * hora, np.ceil(p / 1440) * tope)
    bruto = np.where(p <= tarifas["gracia_min"], 0.0, bruto)
    valor = bruto * (1 - desc) + np.where(np.asarray(extraviado, bool), tarifas["recargo_extravio"], 0.0)
    return np.where(np.isnan(p), np.nan, valor)


def tabla_sturges(valores, etiqueta_hora: bool = True) -> tuple[pd.DataFrame, dict]:
    """
    Tabla de frecuencias con la Ley de Sturges: k = 1 + 3,322·log10(n).
    Devuelve la tabla y los parámetros (n, k, mínimo, máximo, rango, amplitud).
    """
    x = np.asarray(valores, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    k_real = 1 + 3.322 * math.log10(n)
    k = int(round(k_real))
    vmin, vmax = float(x.min()), float(x.max())
    rango = vmax - vmin
    amplitud = math.ceil(rango / k * 1000) / 1000
    bordes = vmin + amplitud * np.arange(k + 1)
    fi, _ = np.histogram(x, bins=bordes)
    hi = fi / n
    def fmt(h):
        hh = int(h); mm = int(round((h - hh) * 60))
        if mm == 60:
            hh, mm = hh + 1, 0
        return f"{hh:02d}:{mm:02d}"
    tabla = pd.DataFrame({
        "Clase": np.arange(1, k + 1),
        "Desde": [fmt(b) if etiqueta_hora else round(b, 4) for b in bordes[:-1]],
        "Hasta": [fmt(b) if etiqueta_hora else round(b, 4) for b in bordes[1:]],
        "Marca de clase": [fmt(m) if etiqueta_hora else round(m, 4) for m in (bordes[:-1] + bordes[1:]) / 2],
        "fi": fi, "hi": hi, "Fi": np.cumsum(fi), "Hi": np.cumsum(hi),
        "U desde": np.concatenate([[0], np.cumsum(hi)[:-1]]), "U hasta": np.cumsum(hi),
    })
    info = dict(n=n, k_real=k_real, k=k, minimo=vmin, maximo=vmax, rango=rango, amplitud=amplitud, bordes=bordes)
    return tabla, info
