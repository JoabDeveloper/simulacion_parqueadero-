"""
Gráficos interactivos para la interfaz web (Altair / Vega-Lite): tooltips, resaltado al pasar el cursor,
zoom en los que tienen eje de tiempo. graficos.py (matplotlib) se mantiene para la línea de comandos.

Paleta (validada con el verificador de daltonismo y contraste):
  * Categórica en orden fijo: azul #2a78d6, naranja #eb6834, aguamarina #1baf7a, amarillo #eda100.
  * Secuencial de un solo tono (azul) para magnitudes y mapas de calor.
  * Ordinal para la temporada: baja #86b6ef → media #2a78d6 → alta #104281.
  * Estados (solo para estados, con etiqueta): bien #0ca30c, atención #fab219, serio #ec835a, crítico #d03b3b.
Los números usan formato colombiano: punto de miles y coma decimal.
"""
from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd

SERIE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SECUENCIAL = ["#F4F8FD", "#cde2fb", "#9ec5f4", "#5598e7", "#256abf", "#184f95", "#0d366b"]
TEMPORADA = {"Baja": "#86b6ef", "Media": "#2a78d6", "Alta": "#104281"}
ESTADO = {"bien": "#0ca30c", "atencion": "#fab219", "serio": "#ec835a", "critico": "#d03b3b"}
TINTA, TINTA_2, TINTA_3, GRILLA, EJE, SUP = "#1E2733", "#4A5565", "#6B7585", "#E8ECF1", "#CDD5DF", "#FCFCFD"
FUENTE = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------
def expr_num(decimales: int = 0) -> str:
    """Expresión Vega que formatea datum.value como 12.345,6 (miles con punto, decimales con coma)."""
    return (f"replace(replace(replace(format(datum.value, ',.{decimales}f'), regexp(',', 'g'), '_'), "
            f"regexp('\\\\.', 'g'), ','), regexp('_', 'g'), '.')")


def n_es(v, d: int = 0) -> str:
    s = f"{v:,.{d}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def cop(v) -> str:
    return "$ " + n_es(v)


def hhmm(x) -> str:
    if pd.isna(x):
        return "—"
    m = int(round(float(x) * 60))
    return f"{m // 60:02d}:{m % 60:02d}"


def estilo(chart, titulo: str | None = None, subtitulo: str | None = None):
    if titulo:
        chart = chart.properties(title=alt.TitleParams(titulo, subtitle=subtitulo or "", anchor="start"))
    chart = chart.properties(padding={"left": 16, "right": 24, "top": 16, "bottom": 12},
                             autosize=alt.AutoSizeParams(type="fit", contains="padding", resize=True))
    return (chart.configure(background="transparent", font=FUENTE)
            .configure_view(stroke=None)
            .configure_axis(labelColor=TINTA_3, titleColor=TINTA_2, gridColor=GRILLA, domainColor=EJE, tickColor=EJE,
                            labelFontSize=11, titleFontSize=11, titleFontWeight=500, titlePadding=10, labelPadding=6,
                            tickSize=0, gridWidth=1)
            # en pantallas angostas Vega oculta solo las etiquetas que se solaparían (una sí, otra no…)
            .configure_axisX(grid=False, labelOverlap="greedy", labelSeparation=4)
            .configure_legend(orient="top", direction="horizontal", labelColor=TINTA_2, titleColor=TINTA_3, labelFontSize=11,
                              titleFontSize=11, titleFontWeight=500, symbolSize=110, symbolType="circle", columnPadding=16,
                              offset=8, labelLimit=260)
            .configure_title(color=TINTA, fontSize=14, fontWeight=600, subtitleColor=TINTA_3, subtitleFontSize=12,
                             subtitlePadding=4, offset=12)
            .configure_mark(color=SERIE[0]))


def _y(titulo: str, dec: int = 0, **kw):
    return alt.Axis(title=titulo, labelExpr=expr_num(dec), tickCount=5, **kw)


# ---------------------------------------------------------------------------
# resultados por día
# ---------------------------------------------------------------------------
def barras_dias(d: pd.DataFrame):
    t = pd.DataFrame({
        "Día": d["Día"], "orden": np.arange(len(d)), "media": d["Llegadas (media)"], "p5": d["Llegadas P5"], "p95": d["Llegadas P95"],
        "Temporada": d["Temporada"], "festivo": d["Festivo"].where(d["Festivo"] != "", "—"),
        "marca": np.where(d["Festivo"] != "", "F", ""),
        "t_media": d["Llegadas (media)"].map(n_es), "t_rango": [f"{n_es(a)} – {n_es(b)}" for a, b in zip(d["Llegadas P5"], d["Llegadas P95"])],
        "t_lleno": (100 * d["Prob. carros llenos"]).map(lambda v: n_es(v, 1) + " %"), "t_ing": d["Ingreso (media)"].map(cop),
        "t_tipo": d["Tipo de día"], "t_hora": d["Hora pico llegadas"],
    })
    orden = list(t["Día"])
    hover = alt.selection_point(on="pointerover", fields=["Día"], nearest=False, empty=False, clear="pointerout")
    x = alt.X("Día:N", sort=orden, title=None, axis=alt.Axis(labelAngle=-50, labelFontSize=10, labelLimit=80))
    tooltip = [alt.Tooltip("Día:N"), alt.Tooltip("t_tipo:N", title="Tipo de día"), alt.Tooltip("festivo:N", title="Festivo"),
               alt.Tooltip("Temporada:N"), alt.Tooltip("t_media:N", title="Vehículos (media)"),
               alt.Tooltip("t_rango:N", title="Rango P5–P95"), alt.Tooltip("t_lleno:N", title="Prob. carros llenos"),
               alt.Tooltip("t_hora:N", title="Hora pico"), alt.Tooltip("t_ing:N", title="Ingreso esperado")]
    base = alt.Chart(t).encode(x=x)
    barras = base.mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        y=alt.Y("media:Q", axis=_y("Vehículos por día")),
        color=alt.Color("Temporada:N", scale=alt.Scale(domain=list(TEMPORADA), range=list(TEMPORADA.values())),
                        legend=alt.Legend(title="Temporada")),
        opacity=alt.when(hover).then(alt.value(1)).otherwise(alt.value(0.88)),
        stroke=alt.when(hover).then(alt.value(TINTA)).otherwise(alt.value(None)),
        tooltip=tooltip).add_params(hover)
    rango = base.mark_rule(color=TINTA_2, strokeWidth=1.2, opacity=0.55).encode(y="p5:Q", y2="p95:Q", tooltip=tooltip)
    marca = base.mark_text(dy=-7, fontSize=10, fontWeight=700, color="#A12A2A").encode(y="p95:Q", text="marca:N")
    return estilo((barras + rango + marca).properties(height=320).configure_scale(bandPaddingInner=0.22),
                  "Vehículos esperados por día", "Barra = media de las réplicas · línea = rango P5–P95 · F = festivo")


# ---------------------------------------------------------------------------
# mapas de calor
# ---------------------------------------------------------------------------
def mapa_calor(m: pd.DataFrame, titulo: str, unidad: str = "vehículos", porcentaje: bool = False, etiquetas: bool | None = None,
               subtitulo: str | None = None):
    filas = [str(i) for i in m.index]
    t = m.copy()
    t.index = filas
    t = t.reset_index(names="fila").melt(id_vars="fila", var_name="hora", value_name="valor")
    t["t_valor"] = t["valor"].map(lambda v: "—" if pd.isna(v) else (n_es(v, 1) + " %" if porcentaje else n_es(v, 1)))
    vmax = 100 if porcentaje else float(np.nanmax(t["valor"])) if len(t) else 1
    t["oscuro"] = t["valor"] > 0.55 * (vmax or 1)
    if etiquetas is None:
        etiquetas = len(filas) <= 8
    hover = alt.selection_point(on="pointerover", fields=["fila", "hora"], empty=False, clear="pointerout")
    base = alt.Chart(t).encode(
        x=alt.X("hora:O", title=None, axis=alt.Axis(labelAngle=0 if m.shape[1] <= 12 else -45, orient="top", labelFontSize=10)),
        y=alt.Y("fila:N", sort=filas, title=None, axis=alt.Axis(labelFontSize=11, labelLimit=120)))
    celdas = base.mark_rect(cornerRadius=3, stroke=SUP, strokeWidth=2).encode(
        color=alt.Color("valor:Q", scale=alt.Scale(range=SECUENCIAL, domain=[0, vmax], clamp=True),
                        legend=alt.Legend(title=unidad, orient="right", direction="vertical", gradientLength=140,
                                          labelExpr=expr_num(0))),
        strokeWidth=alt.when(hover).then(alt.value(2.5)).otherwise(alt.value(2)),
        stroke=alt.when(hover).then(alt.value(TINTA)).otherwise(alt.value(SUP)),
        tooltip=[alt.Tooltip("fila:N", title="Día"), alt.Tooltip("hora:O", title="Hora"), alt.Tooltip("t_valor:N", title=titulo)],
    ).add_params(hover)
    capas = celdas
    if etiquetas:
        capas = celdas + base.mark_text(fontSize=9.5).encode(
            text="t_txt:N", color=alt.when(alt.datum.oscuro).then(alt.value("#FFFFFF")).otherwise(alt.value(TINTA_2)),
        ).transform_calculate(t_txt=f"datum.valor == null ? '' : {expr_num(0).replace('datum.value', 'datum.valor')}")
    alto = max(160, 30 * len(filas) + 40)
    return estilo(capas.properties(height=min(alto, 900)), titulo, subtitulo)


# ---------------------------------------------------------------------------
# entradas, salidas y ocupación por hora
# ---------------------------------------------------------------------------
def perfil_flujo(perfil: pd.DataFrame):
    t = perfil[["Entradas", "Salidas"]].reset_index(names="hora").melt("hora", var_name="Movimiento", value_name="v")
    t["t_v"] = t["v"].map(lambda v: n_es(v, 1))
    hover = alt.selection_point(on="pointerover", fields=["hora"], empty=False, clear="pointerout")
    ch = alt.Chart(t).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("hora:O", title=None, axis=alt.Axis(labelAngle=0, labelFontSize=10)),
        xOffset=alt.XOffset("Movimiento:N", sort=["Entradas", "Salidas"]),
        y=alt.Y("v:Q", axis=_y("Vehículos por hora")),
        color=alt.Color("Movimiento:N", scale=alt.Scale(domain=["Entradas", "Salidas"], range=SERIE[:2]), legend=alt.Legend(title=None)),
        opacity=alt.when(hover).then(alt.value(1)).otherwise(alt.value(0.85)),
        tooltip=[alt.Tooltip("hora:O", title="Hora"), alt.Tooltip("Movimiento:N"), alt.Tooltip("t_v:N", title="Vehículos (promedio)")],
    ).add_params(hover).properties(height=260)
    return estilo(ch.configure_scale(bandPaddingInner=0.18), "Entradas y salidas por hora", "Promedio de los días simulados")


def perfil_ocupacion(perfil: pd.DataFrame, capacidad: int):
    t = perfil[["Ocupación carros"]].reset_index(names="hora").rename(columns={"Ocupación carros": "v"})
    t["t_v"] = t["v"].map(lambda v: n_es(v, 0))
    t["t_pct"] = (100 * t["v"] / max(1, capacidad)).map(lambda v: n_es(v, 1) + " %")
    cerca = alt.selection_point(on="pointerover", nearest=True, fields=["hora"], empty=False, clear="pointerout")
    x = alt.X("hora:O", title=None, axis=alt.Axis(labelAngle=0, labelFontSize=10))
    base = alt.Chart(t).encode(x=x)
    area = base.mark_area(color=SERIE[0], opacity=0.10, interpolate="monotone").encode(
        y=alt.Y("v:Q", axis=_y("Carros dentro"), scale=alt.Scale(domain=[0, max(capacidad, float(t["v"].max())) * 1.12])))
    linea = base.mark_line(color=SERIE[0], strokeWidth=2, interpolate="monotone").encode(y="v:Q")
    puntos = base.mark_point(filled=True, size=70, color=SERIE[0], stroke=SUP, strokeWidth=2).encode(
        y="v:Q", opacity=alt.when(cerca).then(alt.value(1)).otherwise(alt.value(0)),
        tooltip=[alt.Tooltip("hora:O", title="Hora"), alt.Tooltip("t_v:N", title="Carros dentro (máx.)"),
                 alt.Tooltip("t_pct:N", title="% de la capacidad")]).add_params(cerca)
    guia = base.mark_rule(color=EJE, strokeWidth=1).encode(opacity=alt.when(cerca).then(alt.value(1)).otherwise(alt.value(0)))
    cap = alt.Chart(pd.DataFrame({"c": [capacidad], "txt": [f"Capacidad de rotación: {n_es(capacidad)} celdas"]}))
    regla = cap.mark_rule(color="#A12A2A", strokeDash=[5, 4], strokeWidth=1.3).encode(y="c:Q")
    texto = cap.mark_text(align="left", dx=4, dy=-8, fontSize=11, color="#A12A2A", fontWeight=600).encode(
        y="c:Q", text="txt:N", x=alt.value(0))
    return estilo((area + guia + linea + puntos + regla + texto).properties(height=250),
                  "Carros dentro del parqueadero", "Máximo de cada hora, promedio de los días simulados")


# ---------------------------------------------------------------------------
# un día vehículo por vehículo
# ---------------------------------------------------------------------------
COLORES_ESTADO = {"Entró": SERIE[0], "Entró tras esperar": ESTADO["atencion"], "Al parqueadero externo": ESTADO["serio"],
                  "Se fue sin cupo": ESTADO["critico"]}


def gantt_dia(reg: pd.DataFrame, max_vehiculos: int = 420):
    paso = max(1, int(np.ceil(len(reg) / max_vehiculos)))
    m = reg.iloc[::paso].copy()
    m["fin"] = m["salida_h"].clip(upper=24)
    m["x0"] = m["entrada_h"].fillna(m["llegada_h"])
    m["x1"] = m["fin"].fillna(m["llegada_h"] + 0.08)
    for c in ("llegada_h", "entrada_h", "salida_h"):
        m["t_" + c] = m[c].map(hhmm)
    m["t_perm"] = m["permanencia_min"].map(lambda v: n_es(v, 0) + " min")
    m["t_esp"] = m["espera_min"].map(lambda v: "—" if pd.isna(v) else n_es(v, 1) + " min")
    m["t_val"] = m["valor_cop"].map(cop)
    sel = alt.selection_point(fields=["estado"], bind="legend")
    zoom = alt.selection_interval(bind="scales", encodings=["x"])
    tooltip = [alt.Tooltip("vehiculo_id:Q", title="Vehículo N°"), alt.Tooltip("tipo_vehiculo:N", title="Tipo"),
               alt.Tooltip("tipo_cliente:N", title="Cliente"), alt.Tooltip("zona:N", title="Zona"), alt.Tooltip("estado:N", title="Estado"),
               alt.Tooltip("t_llegada_h:N", title="Llegada"), alt.Tooltip("t_entrada_h:N", title="Entrada"),
               alt.Tooltip("t_salida_h:N", title="Salida"), alt.Tooltip("t_perm:N", title="Permanencia"),
               alt.Tooltip("t_esp:N", title="Espera"), alt.Tooltip("t_val:N", title="Valor cobrado")]
    color = alt.Color("estado:N", scale=alt.Scale(domain=list(COLORES_ESTADO), range=list(COLORES_ESTADO.values())),
                      legend=alt.Legend(title="Estado (clic para filtrar)"))
    x = alt.X("x0:Q", title="Hora del día", scale=alt.Scale(domain=[7, 24]),
              axis=alt.Axis(values=list(range(7, 25)), labelExpr="(datum.value < 10 ? '0' : '') + datum.value + ':00'", grid=True))
    y = alt.Y("vehiculo_id:Q", title="Vehículo (orden de llegada)", axis=alt.Axis(labelExpr=expr_num(0), grid=False),
              scale=alt.Scale(reverse=True, nice=False))
    op = alt.when(sel).then(alt.value(0.9)).otherwise(alt.value(0.07))
    m = m.drop(columns=["fecha"], errors="ignore")
    dentro = m[m["estado"].str.startswith("Entró")]
    fuera = m[~m["estado"].str.startswith("Entró")]
    lineas = alt.Chart(dentro).mark_rule(strokeWidth=1.6, strokeCap="round").encode(x=x, x2="x1:Q", y=y, color=color, opacity=op, tooltip=tooltip)
    cruces = alt.Chart(fuera).mark_point(shape="cross", size=46, filled=True).encode(
        x=alt.X("llegada_h:Q", scale=alt.Scale(domain=[7, 24])), y=y, color=color, opacity=op, tooltip=tooltip)
    ch = (lineas + cruces).add_params(sel, zoom).properties(height=440)
    sub = f"{n_es(len(reg))} vehículos" + (f" · se dibuja 1 de cada {paso}" if paso > 1 else "") + \
          " · rueda del ratón para acercar, arrastra para moverte, doble clic para restablecer"
    return estilo(ch, "Cada línea es un vehículo, de su entrada a su salida", sub)


def ocupacion_dia(reg: pd.DataFrame, capacidad: int):
    rot = reg[reg["zona"] == "Carros (rotación)"]
    ev = pd.concat([pd.DataFrame({"t": rot["entrada_h"], "d": 1}), pd.DataFrame({"t": rot["salida_h"], "d": -1})]).dropna().sort_values("t")
    ev = ev[ev["t"] <= 24].copy()
    ev["carros"] = ev["d"].cumsum()
    # se reduce a un punto por minuto (el máximo) para que el gráfico sea liviano
    ev["min"] = (ev["t"] * 60).astype(int)
    t = ev.groupby("min", as_index=False)["carros"].max()
    t["h"] = t["min"] / 60
    t["t_h"] = t["h"].map(hhmm)
    t["t_pct"] = (100 * t["carros"] / max(1, capacidad)).map(lambda v: n_es(v, 1) + " %")
    cerca = alt.selection_point(on="pointerover", nearest=True, fields=["min"], empty=False, clear="pointerout")
    x = alt.X("h:Q", title="Hora del día", scale=alt.Scale(domain=[7, 24]),
              axis=alt.Axis(values=list(range(7, 25)), labelExpr="(datum.value < 10 ? '0' : '') + datum.value + ':00'"))
    base = alt.Chart(t).encode(x=x)
    linea = base.mark_line(interpolate="step-after", color=SERIE[0], strokeWidth=2).encode(
        y=alt.Y("carros:Q", axis=_y("Carros de rotación dentro"), scale=alt.Scale(domain=[0, capacidad * 1.15])))
    puntos = base.mark_point(filled=True, size=60, color=SERIE[0], stroke=SUP, strokeWidth=2).encode(
        y="carros:Q", opacity=alt.when(cerca).then(alt.value(1)).otherwise(alt.value(0)),
        tooltip=[alt.Tooltip("t_h:N", title="Hora"), alt.Tooltip("carros:Q", title="Carros dentro"), alt.Tooltip("t_pct:N", title="% capacidad")],
    ).add_params(cerca)
    cap = alt.Chart(pd.DataFrame({"c": [capacidad], "txt": [f"Capacidad ({n_es(capacidad)})"]}))
    regla = cap.mark_rule(color="#A12A2A", strokeDash=[5, 4], strokeWidth=1.3).encode(y="c:Q")
    texto = cap.mark_text(align="left", dx=4, dy=-8, fontSize=11, color="#A12A2A", fontWeight=600).encode(y="c:Q", text="txt:N", x=alt.value(0))
    return estilo((linea + puntos + regla + texto).properties(height=220), "Carros dentro a lo largo del día",
                  "Resulta de contar entradas menos salidas, minuto a minuto")


# ---------------------------------------------------------------------------
# riesgo
# ---------------------------------------------------------------------------
def histograma(valores, titulo: str, linea=None, etiqueta_linea: str = "", millones: bool = True):
    v = np.asarray(valores, float) / (1e6 if millones else 1)
    k = int(round(1 + 3.322 * np.log10(len(v)))) if len(v) > 1 else 1
    if np.ptp(v) == 0:
        bordes = np.array([v.min() - 0.5, v.min() + 0.5])
    else:
        bordes = np.linspace(v.min(), v.max(), k + 1)
    n, _ = np.histogram(v, bordes)
    u = " M" if millones else ""
    t = pd.DataFrame({"a": bordes[:-1], "b": bordes[1:], "n": n,
                      "t_rango": [f"{n_es(a, 1)} – {n_es(b, 1)}{u}" for a, b in zip(bordes[:-1], bordes[1:])],
                      "t_pct": [n_es(100 * x / max(1, len(v)), 1) + " %" for x in n]})
    hover = alt.selection_point(on="pointerover", fields=["a"], empty=False, clear="pointerout")
    # Ojo: con barras de intervalo (x/x2) Vega-Lite deja de dibujarlas si se usa cornerRadiusTopLeft/Right.
    barras = alt.Chart(t).mark_bar(color=SERIE[0], stroke=SUP, strokeWidth=2).encode(
        x=alt.X("a:Q", bin="binned", title="Millones de COP" if millones else "", axis=alt.Axis(labelExpr=expr_num(1), tickCount=6)),
        x2="b:Q", y=alt.Y("n:Q", axis=_y("Réplicas")),
        opacity=alt.when(hover).then(alt.value(1)).otherwise(alt.value(0.85)),
        tooltip=[alt.Tooltip("t_rango:N", title="Intervalo"), alt.Tooltip("n:Q", title="Réplicas"), alt.Tooltip("t_pct:N", title="% de réplicas")],
    ).add_params(hover)
    capas = barras
    if linea is not None:
        lv = linea / (1e6 if millones else 1)
        d = pd.DataFrame({"x": [lv], "txt": [f"{etiqueta_linea}: {n_es(lv, 1)}{u}"]})
        # la etiqueta lleva un halo del color de la superficie para leerse aunque pase sobre una barra
        halo = alt.Chart(d).mark_text(align="left", dx=6, y=-6, fontSize=11, fontWeight=600, stroke=SUP, strokeWidth=4,
                                      strokeJoin="round", color=SUP).encode(x="x:Q", text="txt:N")
        texto = alt.Chart(d).mark_text(align="left", dx=6, y=-6, fontSize=11, fontWeight=600, color="#A12A2A").encode(x="x:Q", text="txt:N")
        capas = capas + alt.Chart(d).mark_rule(color="#A12A2A", strokeWidth=1.5, strokeDash=[5, 4]).encode(x="x:Q") + halo + texto
    return estilo(capas.properties(height=260), titulo, f"Clases por la regla de Sturges: k = {k}")


def convergencia(conv: np.ndarray):
    t = pd.DataFrame({"r": np.arange(1, len(conv) + 1), "v": np.asarray(conv) / 1e6})
    t["t_v"] = t["v"].map(lambda v: n_es(v, 2) + " M")
    final = float(t["v"].iloc[-1])
    cerca = alt.selection_point(on="pointerover", nearest=True, fields=["r"], empty=False, clear="pointerout")
    base = alt.Chart(t).encode(x=alt.X("r:Q", title="Número de réplicas", axis=alt.Axis(labelExpr=expr_num(0))))
    banda = alt.Chart(pd.DataFrame({"a": [final * 0.99], "b": [final * 1.01]})).mark_rect(color=SERIE[0], opacity=0.07).encode(y="a:Q", y2="b:Q")
    linea = base.mark_line(color=SERIE[0], strokeWidth=2).encode(
        y=alt.Y("v:Q", axis=_y("Millones de COP", 1), scale=alt.Scale(zero=False)))
    puntos = base.mark_point(filled=True, size=60, color=SERIE[0], stroke=SUP, strokeWidth=2).encode(
        y="v:Q", opacity=alt.when(cerca).then(alt.value(1)).otherwise(alt.value(0)),
        tooltip=[alt.Tooltip("r:Q", title="Réplicas"), alt.Tooltip("t_v:N", title="Media acumulada")]).add_params(cerca)
    return estilo((banda + linea + puntos).properties(height=230), "Convergencia de la media del ingreso",
                  "La franja sombreada es ±1 % del valor final: si la curva ya está dentro, las réplicas son suficientes")


# ---------------------------------------------------------------------------
# datos reales y modelo
# ---------------------------------------------------------------------------
TIPOS_DIA = ["Lun–Jue", "Viernes", "Sábado", "Domingo/festivo"]


def historico_diario(diario: pd.DataFrame):
    t = diario.copy()
    t["Día"] = [f"{f.day:02d} {d[:3].lower()}" for f, d in zip(t["fecha"], t["dia"])]
    t["t_v"] = t["vehiculos"].map(n_es)
    t["t_ing"] = t["ingreso"].map(cop)
    t["t_fest"] = t["festivo"].where(t["festivo"] != "", "—")
    t["t_ev"] = t["evento"].where(t["evento"] != "", "—")
    t["t_q"] = np.where(t["quincena"], "Sí", "No")
    t = t.drop(columns=["fecha"])
    hover = alt.selection_point(on="pointerover", fields=["Día"], empty=False, clear="pointerout")
    sel = alt.selection_point(fields=["tipo"], bind="legend")
    ch = alt.Chart(t).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X("Día:N", sort=list(t["Día"]), title=None, axis=alt.Axis(labelAngle=-50, labelFontSize=10)),
        y=alt.Y("vehiculos:Q", axis=_y("Vehículos que ingresaron")),
        color=alt.Color("tipo:N", scale=alt.Scale(domain=TIPOS_DIA, range=SERIE), legend=alt.Legend(title="Tipo de día (clic para filtrar)")),
        opacity=alt.when(sel).then(alt.value(0.95)).otherwise(alt.value(0.15)),
        stroke=alt.when(hover).then(alt.value(TINTA)).otherwise(alt.value(None)),
        tooltip=[alt.Tooltip("Día:N"), alt.Tooltip("tipo:N", title="Tipo"), alt.Tooltip("t_v:N", title="Vehículos"),
                 alt.Tooltip("t_fest:N", title="Festivo"), alt.Tooltip("t_q:N", title="Quincena"), alt.Tooltip("t_ev:N", title="Evento"),
                 alt.Tooltip("t_ing:N", title="Ingreso del día"), alt.Tooltip("pico_carros:Q", title="Pico de carros")],
    ).add_params(hover, sel).properties(height=300)
    return estilo(ch.configure_scale(bandPaddingInner=0.2), "Octubre real: vehículos por día", "Pasa el cursor para ver festivos, quincenas e ingreso")


def barras_sturges(tabla: pd.DataFrame):
    t = tabla.copy()
    t["t_r"] = t["Desde"].astype(str) + " – " + t["Hasta"].astype(str)
    t["t_hi"] = (100 * t["hi"]).map(lambda v: n_es(v, 1) + " %")
    hover = alt.selection_point(on="pointerover", fields=["Clase"], empty=False, clear="pointerout")
    ch = alt.Chart(t).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color=SERIE[0]).encode(
        x=alt.X("Desde:N", sort=list(t["Desde"]), title="Hora de entrada (inicio del intervalo)", axis=alt.Axis(labelAngle=-45)),
        y=alt.Y("fi:Q", axis=_y("Vehículos (fi)")),
        opacity=alt.when(hover).then(alt.value(1)).otherwise(alt.value(0.85)),
        tooltip=[alt.Tooltip("Clase:Q"), alt.Tooltip("t_r:N", title="Intervalo"), alt.Tooltip("fi:Q", title="fi"),
                 alt.Tooltip("t_hi:N", title="hi")],
    ).add_params(hover).properties(height=280)
    return estilo(ch.configure_scale(bandPaddingInner=0.12), "Vehículos por intervalo de Sturges")


def validacion(tabla: pd.DataFrame):
    t = tabla.copy()
    t["Día"] = [f"{f.day:02d}" for f in t["Fecha"]]
    t["t_rango"] = [f"{n_es(a)} – {n_es(b)}" for a, b in zip(t["P5"], t["P95"])]
    t["t_err"] = (100 * t["Error %"]).map(lambda v: n_es(v, 1) + " %")
    t["t_dentro"] = np.where(t["Dentro de P5–P95"], "Sí", "No")
    t = t.drop(columns=["Fecha"])
    largo = t.melt(id_vars=["Día", "Tipo", "t_rango", "t_err", "t_dentro"], value_vars=["Simulado (media)", "Real"], var_name="Serie", value_name="v")
    largo["t_v"] = largo["v"].map(n_es)
    tooltip = [alt.Tooltip("Día:N", title="Día de octubre"), alt.Tooltip("Tipo:N"), alt.Tooltip("t_rango:N", title="Rango simulado P5–P95"),
               alt.Tooltip("t_err:N", title="Error"), alt.Tooltip("t_dentro:N", title="Real dentro del rango")]
    x = alt.X("Día:N", sort=list(t["Día"]), title="Día de octubre", axis=alt.Axis(labelAngle=0, labelFontSize=10))
    rango = alt.Chart(t).mark_rule(color=SERIE[0], opacity=0.18, strokeWidth=12, strokeCap="round").encode(
        x=x, y=alt.Y("P5:Q", axis=_y("Vehículos")), y2="P95:Q", tooltip=tooltip)
    puntos = alt.Chart(largo).mark_point(filled=True, size=70, stroke=SUP, strokeWidth=1.5, opacity=1).encode(
        x=x, y="v:Q", color=alt.Color("Serie:N", scale=alt.Scale(domain=["Simulado (media)", "Real"], range=SERIE[:2]), legend=alt.Legend(title=None)),
        shape=alt.Shape("Serie:N", scale=alt.Scale(domain=["Simulado (media)", "Real"], range=["circle", "diamond"]), legend=None),
        tooltip=tooltip + [alt.Tooltip("Serie:N"), alt.Tooltip("t_v:N", title="Vehículos")])
    return estilo((rango + puntos).properties(height=280), "Validación: real contra simulado",
                  "Franja = rango P5–P95 de las réplicas · círculo = media simulada · rombo = valor real")


def dispersion_u(u: np.ndarray, n: int = 2500):
    u = np.asarray(u)[: n + 1]
    t = pd.DataFrame({"a": u[:-1], "b": u[1:]})
    ch = alt.Chart(t).mark_circle(size=9, opacity=0.45, color=SERIE[0]).encode(
        x=alt.X("a:Q", title="Uᵢ", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(grid=True, labelExpr=expr_num(1))),
        y=alt.Y("b:Q", title="Uᵢ₊₁", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(labelExpr=expr_num(1))),
        tooltip=[alt.Tooltip("a:Q", title="Uᵢ", format=".4f"), alt.Tooltip("b:Q", title="Uᵢ₊₁", format=".4f")],
    ).properties(height=320)
    return estilo(ch, "Pares consecutivos (Uᵢ, Uᵢ₊₁)", "Si el generador es bueno, los puntos cubren el cuadrado sin patrones")


def lambdas(lam: pd.DataFrame):
    """lam: filas = tipo de día, columnas = hora. Una línea por tipo de día."""
    t = lam.reset_index(names="tipo").melt("tipo", var_name="hora", value_name="v")
    t["t_v"] = t["v"].map(lambda v: n_es(v, 1))
    cerca = alt.selection_point(on="pointerover", nearest=True, fields=["hora"], empty=False, clear="pointerout")
    base = alt.Chart(t).encode(x=alt.X("hora:O", title=None, axis=alt.Axis(labelAngle=0, labelFontSize=10)),
                               color=alt.Color("tipo:N", scale=alt.Scale(domain=TIPOS_DIA, range=SERIE), legend=alt.Legend(title="Tipo de día")))
    lineas = base.mark_line(strokeWidth=2, interpolate="monotone").encode(y=alt.Y("v:Q", axis=_y("Vehículos por hora (λ)")))
    puntos = base.mark_point(filled=True, size=55, stroke=SUP, strokeWidth=1.5).encode(
        y="v:Q", opacity=alt.when(cerca).then(alt.value(1)).otherwise(alt.value(0)),
        tooltip=[alt.Tooltip("tipo:N", title="Tipo de día"), alt.Tooltip("hora:O", title="Hora"), alt.Tooltip("t_v:N", title="λ")]).add_params(cerca)
    guia = alt.Chart(t).mark_rule(color=EJE).encode(x="hora:O", opacity=alt.when(cerca).then(alt.value(1)).otherwise(alt.value(0)))
    return estilo((guia + lineas + puntos).properties(height=280), "Tasa de llegadas por hora (rotación)",
                  "Estimada de octubre, sin quincena ni temporada")
