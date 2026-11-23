"""Gráficos con matplotlib (se usan en la interfaz y en la línea de comandos)."""
from __future__ import annotations

import calendar as _cal

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from . import calendario as cal

AZUL, NARANJA, VERDE, GRIS, ROJO = "#3A6EA5", "#E07A5F", "#5FA8A0", "#9AA5B1", "#C8553D"
AMBAR, AZUL_OSC, TEXTO, BORDE = "#E9B872", "#24476E", "#1F2A37", "#E3E8EF"
COLOR_TEMPORADA = {"Alta": "#E07A5F", "Media": "#3A6EA5", "Baja": "#AEB8C4"}
CMAP_AZUL = LinearSegmentedColormap.from_list("azul", ["#F7F9FC", "#C9DAEE", "#6F9BCB", "#24476E"])
CMAP_ROJO = LinearSegmentedColormap.from_list("rojo", ["#FDF8F5", "#F4CDBE", "#DB7F62", "#9C3D27"])
plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans", "Arial", "sans-serif"], "font.size": 9, "text.color": TEXTO,
    "axes.labelcolor": "#4B5563", "xtick.color": "#6B7280", "ytick.color": "#6B7280",
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False, "axes.edgecolor": "#C9D1DC",
    "axes.titleweight": "bold", "axes.titlesize": 11, "axes.titlepad": 12, "axes.titlelocation": "left",
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": "#EDF0F4", "grid.linewidth": 0.9, "axes.axisbelow": True,
    "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False, "figure.facecolor": "white",
    "axes.facecolor": "white", "savefig.facecolor": "white",
})


def mapa_calor(df: pd.DataFrame, titulo: str, fmt: str = "{:.0f}", rojo: bool = False, vmin=None, vmax=None, etiqueta=""):
    filas, cols = df.shape
    fig, ax = plt.subplots(figsize=(min(16, 2 + cols * 0.62), max(2.6, 0.9 + filas * 0.32)))
    ax.grid(False)
    im = ax.imshow(df.values, aspect="auto", cmap=CMAP_ROJO if rojo else CMAP_AZUL, vmin=vmin, vmax=vmax)
    ax.set_xticks(range(cols)); ax.set_xticklabels(df.columns, rotation=0 if cols <= 12 else 45, ha="center" if cols <= 12 else "right")
    ax.set_yticks(range(filas)); ax.set_yticklabels(df.index)
    if filas * cols <= 700:
        top = np.nanmax(df.values) if vmax is None else vmax
        for i in range(filas):
            for j in range(cols):
                v = df.values[i, j]
                if np.isnan(v):
                    continue
                ax.text(j, i, fmt.format(v), ha="center", va="center", fontsize=7,
                        color="white" if top and v > 0.6 * top else "#1b1b1b")
    ax.set_title(titulo, loc="left")
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    cb.set_label(etiqueta)
    cb.outline.set_visible(False)
    fig.tight_layout()
    return fig


def perfil_entradas_salidas(perfil: pd.DataFrame, capacidad: int, titulo="Entradas y salidas por hora (promedio de los días simulados)"):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 5.6), sharex=True, gridspec_kw={"height_ratios": [1.1, 1]})
    x = np.arange(len(perfil))
    a1.bar(x - 0.2, perfil["Entradas"], 0.4, color=AZUL, label="Entradas")
    a1.bar(x + 0.2, perfil["Salidas"], 0.4, color=AMBAR, label="Salidas")
    a1.set_ylabel("Vehículos por hora"); a1.legend(frameon=False, ncol=2, loc="upper left"); a1.set_title(titulo, loc="left")
    a2.fill_between(x, perfil["Ocupación carros"], color=AZUL, alpha=0.10)
    a2.plot(x, perfil["Ocupación carros"], color=AZUL_OSC, lw=2.2, marker="o", ms=3.5, label="Carros dentro (máximo de la hora)")
    a2.axhline(capacidad, color=ROJO, ls="--", lw=1.2, label=f"Capacidad de rotación ({capacidad})")
    a2.set_ylabel("Carros dentro"); a2.set_ylim(0, max(capacidad, perfil["Ocupación carros"].max()) * 1.32)
    a2.legend(frameon=False, loc="upper left", ncol=2)
    a2.set_xticks(x); a2.set_xticklabels(perfil.index, rotation=45, ha="right")
    fig.tight_layout()
    return fig


def gantt_dia(reg: pd.DataFrame, capacidad: int, max_vehiculos: int = 260):
    """Cada línea es un vehículo: empieza en su ENTRADA y termina en su SALIDA. Abajo, la ocupación resultante."""
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 7.2), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    paso = max(1, len(reg) // max_vehiculos)
    m = reg.iloc[::paso]
    colores = {"Entró": AZUL, "Entró tras esperar": AMBAR, "Se fue sin cupo": ROJO, "Al parqueadero externo": NARANJA}
    for est, col in colores.items():
        s = m[m["estado"] == est]
        if len(s) == 0:
            continue
        if est in ("Se fue sin cupo", "Al parqueadero externo"):
            a1.scatter(s["llegada_h"], s["vehiculo_id"], marker="x", color=col, s=14, label=est)
        else:
            a1.hlines(s["vehiculo_id"], s["entrada_h"], s["salida_h"].clip(upper=24), color=col, lw=1, alpha=0.85, label=est)
    a1.grid(False)
    a1.set_ylabel("Vehículo (orden de llegada)")
    a1.set_title(f"Entradas y salidas de un día simulado ({len(reg)} vehículos; se muestra 1 de cada {paso})", loc="left")
    a1.legend(frameon=False, loc="upper left", fontsize=8)
    rot = reg[reg["zona"] == "Carros (rotación)"]
    ev2 = pd.concat([pd.DataFrame({"t": rot["entrada_h"], "d": 1}), pd.DataFrame({"t": rot["salida_h"], "d": -1})]).dropna().sort_values("t")
    ev2 = ev2[ev2["t"] <= 24]
    a2.step(ev2["t"], ev2["d"].cumsum(), where="post", color=AZUL, lw=1.6, label="Carros de rotación dentro")
    a2.axhline(capacidad, color=ROJO, ls="--", lw=1.2, label=f"Capacidad ({capacidad})")
    a2.set_ylabel("Carros dentro"); a2.set_xlabel("Hora del día"); a2.legend(frameon=False, loc="upper left", fontsize=8, ncol=2)
    a2.set_xlim(7, 24); a2.set_xticks(range(7, 25)); a2.set_xticklabels([f"{h:02d}" for h in range(7, 25)])
    a2.set_ylim(0, capacidad * 1.32)
    fig.tight_layout()
    return fig


def barras_dias(dias: pd.DataFrame, columna="Llegadas (media)", p5="Llegadas P5", p95="Llegadas P95", titulo="Vehículos esperados por día"):
    fig, ax = plt.subplots(figsize=(max(7, 0.38 * len(dias) + 2), 3.8))
    x = np.arange(len(dias))
    col = [COLOR_TEMPORADA[t] for t in dias["Temporada"]]
    ax.bar(x, dias[columna], color=col, width=0.68)
    if p5 in dias and p95 in dias:
        ax.vlines(x, dias[p5], dias[p95], color="#4B5563", lw=1, alpha=0.55)
    for i, f in enumerate(dias["Festivo"]):
        if f:
            ax.text(i, dias[p95].iloc[i] if p95 in dias else dias[columna].iloc[i], "F", ha="center", va="bottom", color=ROJO, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(dias["Día"], rotation=60, ha="right", fontsize=7.5)
    ax.set_title(titulo + "  (color = temporada; F = festivo; línea = P5–P95)", loc="left")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=c, label=f"Temporada {t.lower()}") for t, c in COLOR_TEMPORADA.items()], frameon=False, ncol=3, fontsize=8)
    fig.tight_layout()
    return fig


def histograma_sturges(valores: np.ndarray, titulo: str, linea=None, etiqueta_linea="", millones=True):
    v = np.asarray(valores, float)
    k = int(round(1 + 3.322 * np.log10(len(v)))) if len(v) > 1 else 1
    fig, ax = plt.subplots(figsize=(8, 3.6))
    escala = 1e6 if millones else 1
    ax.hist(v / escala, bins=k, color=AZUL, edgecolor="white", linewidth=1.2, alpha=0.92)
    if linea is not None:
        ax.axvline(linea / escala, color=ROJO, ls="--", lw=1.4, label=etiqueta_linea); ax.legend(frameon=False)
    ax.set_title(f"{titulo} (Sturges: k = {k} clases)", loc="left")
    ax.set_xlabel("Millones de COP" if millones else ""); ax.set_ylabel("Réplicas")
    fig.tight_layout()
    return fig


def convergencia(conv: np.ndarray, titulo="Convergencia: media acumulada del ingreso"):
    fig, ax = plt.subplots(figsize=(13, 3.4))
    ax.plot(np.arange(1, len(conv) + 1), conv / 1e6, color=AZUL, lw=2)
    ax.fill_between(np.arange(1, len(conv) + 1), conv / 1e6, conv[-1] / 1e6, color=AZUL, alpha=0.08)
    ax.set_xlabel("Número de réplicas"); ax.set_ylabel("Millones de COP"); ax.set_title(titulo, loc="left")
    fig.tight_layout()
    return fig


def historico_diario(diario: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(11, 3.8))
    colores = {"Lun–Jue": "#A9C4E2", "Viernes": "#5F8FC4", "Sábado": "#24476E", "Domingo/festivo": NARANJA}
    x = np.arange(len(diario))
    ax.bar(x, diario["vehiculos"], color=[colores[t] for t in diario["tipo"]], width=0.75)
    for i, r in diario.iterrows():
        marca = []
        if r["festivo"]:
            marca.append("Festivo")
        if r["quincena"]:
            marca.append("Q")
        if r["evento"]:
            marca.append(r["evento"])
        if marca:
            ax.text(i, r["vehiculos"] + 15, "\n".join(marca), ha="center", va="bottom", fontsize=6.5, color=ROJO if r["festivo"] else "#333")
    ax.set_xticks(x); ax.set_xticklabels([f"{f.day:02d} {d[:3]}" for f, d in zip(diario["fecha"], diario["dia"])], rotation=60, ha="right", fontsize=7.5)
    ax.set_ylabel("Vehículos que ingresaron"); ax.set_ylim(0, diario["vehiculos"].max() * 1.22)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=c, label=t) for t, c in colores.items()], frameon=False, ncol=4, fontsize=8, loc="upper left")
    ax.set_title("Datos reales de octubre: vehículos por día (Q = quincena)", loc="left")
    fig.tight_layout()
    return fig


def barras_sturges(tabla: pd.DataFrame, titulo: str):
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.bar(range(len(tabla)), tabla["fi"], color=VERDE, width=0.92)
    ax.set_xticks(range(len(tabla))); ax.set_xticklabels(tabla["Desde"], rotation=45, ha="right")
    ax.set_ylabel("Vehículos (fi)"); ax.set_title(titulo, loc="left")
    fig.tight_layout()
    return fig


def calendario_resultados(dias: pd.DataFrame, anio: int, mes: int, columna: str, fmt="{:.0f}", rojo=False):
    """Calendario mensual coloreado con un indicador por día (para la línea de comandos)."""
    semanas = cal.semanas_del_mes(anio, mes)
    datos = {r["Fecha"]: r[columna] for _, r in dias.iterrows()}
    vals = [v for f, v in datos.items() if f.month == mes and f.year == anio]
    vmax = max(vals) if vals else 1
    fig, ax = plt.subplots(figsize=(8, 0.9 + 0.9 * len(semanas)))
    cmap = CMAP_ROJO if rojo else CMAP_AZUL
    for w, sem in enumerate(semanas):
        for d, f in enumerate(sem):
            y = len(semanas) - 1 - w
            fondo = "#ffffff"
            if f in datos:
                fondo = cmap(0.15 + 0.85 * (datos[f] / vmax if vmax else 0))
            ax.add_patch(matplotlib.patches.Rectangle((d, y), 0.96, 0.9, color=fondo, ec="#cccccc"))
            colt = "#bbbbbb" if f.month != mes else "#111111"
            ax.text(d + 0.06, y + 0.68, str(f.day), fontsize=8, color=colt, fontweight="bold")
            if cal.festivo(f) and f.month == mes:
                ax.text(d + 0.9, y + 0.68, "F", fontsize=8, color=ROJO, ha="right", fontweight="bold")
            if f in datos:
                v = datos[f]
                ax.text(d + 0.48, y + 0.28, fmt.format(v), fontsize=8, ha="center",
                        color="white" if vmax and v > 0.6 * vmax else "#111")
    for d, n in enumerate(["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]):
        ax.text(d + 0.48, len(semanas) + 0.15, n, ha="center", fontsize=8, fontweight="bold")
    ax.set_xlim(0, 7); ax.set_ylim(0, len(semanas) + 0.5); ax.axis("off")
    ax.set_title(f"{cal.MESES[mes - 1]} {anio} – {columna}", loc="left")
    fig.tight_layout()
    return fig
