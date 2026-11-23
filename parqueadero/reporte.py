"""
Exporta la simulación a un libro de Excel organizado y con gráficas nativas de Excel.

Hojas del libro:
  Resumen            tablero: tarjetas con los indicadores clave, recomendaciones y 4 gráficas
  Por día            una fila por día simulado (vehículos, lleno, ocupación, ingreso, meta…)
  Por hora           entradas, salidas y ocupación por hora, horas pico/valle, Sturges y un día vehículo por vehículo
  Calor semana       mapas de calor día de la semana × hora
  Calor fechas       mapas de calor fecha × hora
  Riesgo             ingreso esperado, meta, VaR, histogramas (Sturges) y convergencia
  Externo            beneficio de abrir un parqueadero externo
  Calendario         temporada, festivos y motivo de cada día
  Réplicas           ingreso, pérdida y faltante de cada réplica
  Vehículos          cada vehículo de la réplica 1 (llegada, entrada, salida, estado, valor)
  Parámetros y guía  qué contiene cada hoja y con qué supuestos se simuló
"""
from __future__ import annotations

import datetime as dt
import io
import math

import numpy as np
import pandas as pd
import xlsxwriter

from . import calendario as cal
from .estadisticas import recomendaciones

# Paleta (la misma de la interfaz)
PRI, PRI_OSC, TEAL, CORAL, AMBAR = "#3A6EA5", "#24476E", "#5FA8A0", "#E07A5F", "#E9B872"
TEXTO, GRIS, BORDE, FONDO = "#1F2A37", "#6B7280", "#E3E8EF", "#F4F6F9"
AZUL_CLARO, CORAL_CLARO = "#DCE7F3", "#F9E1D9"


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------
def _py(v):
    """Convierte valores de numpy/pandas a tipos que entiende Excel (NaN → celda vacía)."""
    if v is None:
        return None
    if isinstance(v, (np.bool_, bool)):
        return "Sí" if v else "No"
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if (math.isnan(v) or math.isinf(v)) else float(v)
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    return v


class _Formatos:
    def __init__(self, wb):
        base = {"font_name": "Calibri", "font_size": 10, "font_color": TEXTO, "valign": "vcenter"}
        f = lambda **k: wb.add_format({**base, **k})
        self.titulo = f(font_size=16, bold=True, font_color=PRI_OSC)
        self.subtitulo = f(font_size=10, font_color=GRIS, italic=True)
        self.seccion = f(font_size=12, bold=True, font_color=PRI_OSC, bottom=2, bottom_color=PRI)
        self.banner = f(font_size=18, bold=True, font_color="#FFFFFF", bg_color=PRI, align="left", indent=1)
        self.banner_sub = f(font_size=10, font_color="#FFFFFF", bg_color=PRI_OSC, align="left", indent=1)
        self.header = f(bold=True, font_color="#FFFFFF", bg_color=PRI, text_wrap=True, align="center", border=1, border_color=PRI)
        self.header_hora = f(bold=True, font_color=TEXTO, bg_color=AZUL_CLARO, align="center", font_size=9)
        self.etiqueta = f(bold=True, bg_color=FONDO, font_size=9)
        self.texto = f()
        self.texto_wrap = f(text_wrap=True, valign="top")
        self.nota = f(font_size=9, font_color=GRIS, italic=True, text_wrap=True, valign="top")
        self.entero = f(num_format="#,##0")
        self.decimal = f(num_format="#,##0.0")
        self.dec3 = f(num_format="0.000")
        self.pct = f(num_format="0.0%")
        self.cop = f(num_format='"$" #,##0')
        self.fecha = f(num_format="dd/mm/yyyy", align="left")
        self.hora = f(num_format="[h]:mm", align="center")
        self.mapa = f(num_format="0", align="center", font_size=9)
        self.mapa_pct = f(num_format='0" %"', align="center", font_size=9)
        self.bullet = f(text_wrap=True, valign="top", font_size=10.5, bg_color=FONDO, indent=1)
        # tarjetas del resumen
        tarjeta = dict(bg_color=FONDO, align="left", indent=1)
        self.card_barra = {c: f(bg_color=c) for c in (PRI, TEAL, CORAL, AMBAR)}
        self.card_lab = f(**tarjeta, font_size=9, font_color=GRIS, bold=True)
        self.card_nota = f(**tarjeta, font_size=8.5, font_color=GRIS, italic=True)
        self.card_val = {
            "entero": f(**tarjeta, font_size=20, bold=True, num_format="#,##0"),
            "pct": f(**tarjeta, font_size=20, bold=True, num_format="0.0%"),
            "cop": f(**tarjeta, font_size=17, bold=True, num_format='"$" #,##0'),
            "texto": f(**tarjeta, font_size=12, bold=True, text_wrap=True),
        }
        self.bien = f(bg_color="#E3F1EE", font_color="#1E6B5F")
        self.mal = f(bg_color=CORAL_CLARO, font_color="#8C3A24")


def _formato_col(nombre: str, serie: pd.Series, F: _Formatos):
    n = nombre.lower()
    if pd.api.types.is_datetime64_any_dtype(serie) or (len(serie) and isinstance(serie.iloc[0], (dt.date, dt.datetime))):
        return F.fecha
    if not pd.api.types.is_numeric_dtype(serie) or pd.api.types.is_bool_dtype(serie):
        return F.texto
    if n.startswith("prob") or "% " in n or n.startswith("%") or n in ("hi", "hi acum.", "% de réplicas", "u desde", "u hasta"):
        return F.pct
    if any(p in n for p in ("ingreso", "meta", "pérdida", "valor", "beneficio", "cop", "faltante", "media acumulada")):
        return F.cop
    if "factor" in n:
        return F.dec3
    if pd.api.types.is_integer_dtype(serie):
        return F.entero
    return F.decimal


def _ancho(nombre: str, serie: pd.Series) -> float:
    muestra = serie.head(60).map(lambda v: len(f"{v:,.0f}") + 3 if isinstance(v, (int, float, np.number)) and not pd.isna(v) else len(str(v)))
    largo = max([len(nombre) * 0.85] + list(muestra))
    return float(min(46, max(9, largo + 2)))


def _tabla(ws, fila: int, col: int, df: pd.DataFrame, F: _Formatos, formatos: dict | None = None, anchos=True, total=False) -> int:
    """Escribe df como tabla de Excel (con filtros y filas alternadas). Devuelve la última fila usada."""
    formatos = formatos or {}
    if df is None or len(df) == 0:
        ws.write(fila, col, "Sin datos para este periodo.", F.nota)
        return fila
    df = df.reset_index(drop=True)
    datos = [[_py(v) for v in fila_v] for fila_v in df.itertuples(index=False, name=None)]
    columnas = []
    for c in df.columns:
        fmt = formatos.get(c) or _formato_col(str(c), df[c], F)
        columnas.append({"header": str(c), "format": fmt, "header_format": F.header})
    ws.add_table(fila, col, fila + len(df), col + len(df.columns) - 1,
                 {"data": datos, "columns": columnas, "style": "Table Style Light 1", "autofilter": True})
    ws.set_row(fila, 30)
    if anchos:
        for j, c in enumerate(df.columns):
            ws.set_column(col + j, col + j, _ancho(str(c), df[c]))
    return fila + len(df)


def _grafica(wb, tipo: str, titulo: str, subtipo: str | None = None, eje_x="", eje_y="", fmt_y=None, rotar=False):
    g = wb.add_chart({"type": tipo, **({"subtype": subtipo} if subtipo else {})})
    g.set_title({"name": titulo, "name_font": {"size": 11, "bold": True, "color": TEXTO, "name": "Calibri"}, "overlay": False})
    g.set_chartarea({"border": {"none": True}, "fill": {"color": "#FFFFFF"}})
    g.set_plotarea({"fill": {"color": "#FFFFFF"}})
    g.set_legend({"position": "bottom", "font": {"size": 9, "color": GRIS}})
    eje_cat = {"name": eje_x, "name_font": {"size": 9, "color": GRIS, "bold": False}, "num_font": {"size": 8, "color": GRIS,
               **({"rotation": -45} if rotar else {})}, "line": {"color": BORDE}, "major_tick_mark": "none"}
    eje_val = {"name": eje_y, "name_font": {"size": 9, "color": GRIS, "bold": False}, "num_font": {"size": 8, "color": GRIS},
               "line": {"none": True}, "major_gridlines": {"visible": True, "line": {"color": "#EEF1F5"}}, "major_tick_mark": "none"}
    if fmt_y:
        eje_val["num_format"] = fmt_y
    if tipo == "bar":
        g.set_x_axis(eje_val); g.set_y_axis(eje_cat)
    else:
        g.set_x_axis(eje_cat); g.set_y_axis(eje_val)
    return g


def _mapa(ws, fila: int, titulo: str, df: pd.DataFrame, F: _Formatos, rojo=False, porcentaje=False) -> int:
    """Bloque de mapa de calor: título, horas en columnas y escala de color de Excel. Devuelve la siguiente fila libre."""
    ws.write(fila, 1, titulo, F.seccion)
    ws.write(fila + 1, 1, "", F.header_hora)
    for j, h in enumerate(df.columns):
        ws.write(fila + 1, 2 + j, h, F.header_hora)
    for i, (idx, valores) in enumerate(df.iterrows()):
        ws.write(fila + 2 + i, 1, str(idx), F.etiqueta)
        for j, v in enumerate(valores.values):
            ws.write(fila + 2 + i, 2 + j, _py(v), F.mapa_pct if porcentaje else F.mapa)
    r0, r1, c1 = fila + 2, fila + 1 + len(df), 1 + len(df.columns)
    colores = ("#FFFFFF", "#F2B8A2", "#B4492F") if rojo else ("#FFFFFF", "#A9C4E2", "#24476E")
    regla = {"type": "3_color_scale", "min_color": colores[0], "mid_color": colores[1], "max_color": colores[2],
             "mid_type": "percentile", "mid_value": 50}
    if porcentaje:
        regla.update(min_type="num", min_value=0, max_type="num", max_value=100, mid_type="num", mid_value=50)
    ws.conditional_format(r0, 2, r1, c1, regla)
    return r1 + 3


def _histograma(valores: np.ndarray):
    v = np.asarray(valores, float)
    k = max(1, int(round(1 + 3.322 * math.log10(len(v))))) if len(v) > 1 else 1
    fi, bordes = np.histogram(v, bins=k)
    return pd.DataFrame({"Rango (millones)": [f"{a / 1e6:,.1f} – {b / 1e6:,.1f}" for a, b in zip(bordes[:-1], bordes[1:])],
                         "Desde (COP)": bordes[:-1], "Hasta (COP)": bordes[1:], "Réplicas": fi.astype(int),
                         "% de réplicas": fi / len(v)}), k


def _imagen(fig) -> io.BytesIO:
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# libro
# ---------------------------------------------------------------------------
def a_excel(S: dict, res, P) -> bytes:
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": True, "default_date_format": "dd/mm/yyyy"})
    wb.set_properties({"title": "Simulación Montecarlo del parqueadero", "subject": "Entradas y salidas de vehículos",
                       "comments": "Generado por el simulador del C.C. Plaza El Mirador"})
    F = _Formatos(wb)
    hojas = {n: wb.add_worksheet(n) for n in ["Resumen", "Por día", "Por hora", "Calor semana", "Calor fechas", "Riesgo",
                                               "Externo", "Calendario", "Réplicas", "Vehículos", "Parámetros y guía"]}
    for ws in hojas.values():
        ws.hide_gridlines(2)
        ws.set_zoom(90)
        ws.set_column(0, 0, 2)

    k, r, e, d = S["kpi"], S["riesgo"], S["externo"], S["dias"]
    D, R = k["dias"], k["replicas"]
    periodo = f"{res.dias[0].fecha:%d/%m/%Y} – {res.dias[-1].fecha:%d/%m/%Y}"
    cap = res.capacidad

    # ======================= Por día =======================
    ws = hojas["Por día"]
    ws.write(0, 1, "Resultados por día simulado", F.titulo)
    ws.write(1, 1, f"Promedio de {R} réplicas por día. P5 y P95: 5 % de las réplicas quedó por debajo / por encima.", F.subtitulo)
    cols_dia = ["Fecha", "Día", "Tipo de día", "Festivo", "Quincena", "Temporada", "Factor de temporada", "Eventos",
                "Llegadas (media)", "Llegadas P5", "Llegadas P95", "Entradas (media)", "Sin cupo (media)", "Prob. carros llenos",
                "% ocupación pico", "Pico carros (media)", "Espera prom. (min)", "Ingreso (media)", "Ingreso P5", "Ingreso P95",
                "Meta del día", "Prob. ingreso < meta", "Ingreso perdido (media)", "Hora pico llegadas", "Hora pico ocupación", "Nivel"]
    tabla_dia = d[cols_dia].copy()
    F0 = 3
    fin = _tabla(ws, F0, 1, tabla_dia, F)
    ci = {c: 1 + j for j, c in enumerate(cols_dia)}
    ws.conditional_format(F0 + 1, ci["Llegadas (media)"], fin, ci["Llegadas (media)"],
                          {"type": "data_bar", "bar_color": "#9DBCE0", "bar_solid": True, "bar_no_border": True})
    for c in ("Prob. carros llenos", "% ocupación pico", "Prob. ingreso < meta"):
        ws.conditional_format(F0 + 1, ci[c], fin, ci[c], {"type": "3_color_scale", "min_color": "#FFFFFF", "mid_color": "#F6D3C6",
                                                          "max_color": "#D9785B", "min_type": "num", "min_value": 0,
                                                          "max_type": "num", "max_value": 1, "mid_type": "num", "mid_value": 0.5})
    ws.conditional_format(F0 + 1, ci["Nivel"], fin, ci["Nivel"], {"type": "cell", "criteria": "==", "value": '"Pico"', "format": F.mal})
    ws.conditional_format(F0 + 1, ci["Nivel"], fin, ci["Nivel"], {"type": "cell", "criteria": "==", "value": '"Valle"', "format": F.bien})
    ws.freeze_panes(F0 + 1, 3)
    ws.set_column(ci["Fecha"], ci["Fecha"], 11)

    def ref(col, hoja="Por día"):
        return [hoja, F0 + 1, ci[col], fin, ci[col]]

    # gráficas por día (cada llamada crea una gráfica nueva: en Excel una gráfica solo puede estar en un lugar)
    def graf_llegadas(tam):
        g = _grafica(wb, "column", "Vehículos esperados por día", eje_y="Vehículos", fmt_y="#,##0", rotar=D > 10)
        g.add_series({"name": "Llegadas (media)", "categories": ref("Día"), "values": ref("Llegadas (media)"),
                      "fill": {"color": PRI}, "gap": 60})
        linea = wb.add_chart({"type": "line"})
        linea.add_series({"name": "P95 (día alto)", "categories": ref("Día"), "values": ref("Llegadas P95"),
                          "line": {"color": CORAL, "width": 1.25, "dash_type": "dash"}})
        linea.add_series({"name": "P5 (día bajo)", "categories": ref("Día"), "values": ref("Llegadas P5"),
                          "line": {"color": GRIS, "width": 1.25, "dash_type": "dash"}})
        g.combine(linea)
        g.set_size(tam)
        return g

    def graf_ingreso(tam):
        g = _grafica(wb, "column", "Ingreso esperado por día frente a la meta", eje_y="COP", fmt_y='"$" #,##0.0,,"M"', rotar=D > 10)
        g.add_series({"name": "Ingreso esperado", "categories": ref("Día"), "values": ref("Ingreso (media)"),
                      "fill": {"color": TEAL}, "gap": 60})
        lmeta = wb.add_chart({"type": "line"})
        lmeta.add_series({"name": "Meta del día", "categories": ref("Día"), "values": ref("Meta del día"),
                          "line": {"color": CORAL, "width": 2},
                          "marker": {"type": "circle", "size": 4, "fill": {"color": CORAL}, "border": {"color": CORAL}}})
        g.combine(lmeta)
        g.set_size(tam)
        return g

    def graf_lleno(tam):
        g = _grafica(wb, "column", "Probabilidad de lleno y ocupación pico por día", eje_y="Probabilidad", fmt_y="0%", rotar=D > 10)
        g.add_series({"name": "Prob. carros llenos", "categories": ref("Día"), "values": ref("Prob. carros llenos"),
                      "fill": {"color": CORAL}, "gap": 60})
        g.add_series({"name": "% de ocupación en la hora pico", "categories": ref("Día"), "values": ref("% ocupación pico"),
                      "fill": {"color": AMBAR}, "gap": 60})
        g.set_y_axis({"num_format": "0%", "min": 0, "max": 1.05, "major_gridlines": {"visible": True, "line": {"color": "#EEF1F5"}},
                      "num_font": {"size": 8, "color": GRIS}, "line": {"none": True}})
        g.set_size(tam)
        return g

    ws.write(fin + 2, 1, "Gráficas", F.seccion)
    grande = {"width": 820, "height": 330}
    ws.insert_chart(fin + 4, 1, graf_llegadas(grande))
    ws.insert_chart(fin + 22, 1, graf_ingreso(grande))
    ws.insert_chart(fin + 40, 1, graf_lleno(grande))

    # ======================= Por hora =======================
    ws = hojas["Por hora"]
    ws.write(0, 1, "Entradas, salidas y ocupación por hora", F.titulo)
    ws.write(1, 1, "Promedio de todos los días simulados. La ocupación es el máximo de carros dentro durante esa hora.", F.subtitulo)
    perfil = S["perfil"].reset_index().rename(columns={"index": "Hora"})
    fin_p = _tabla(ws, 3, 1, perfil, F, formatos={c: F.decimal for c in perfil.columns if c != "Hora"})
    nP = len(perfil)

    def graf_hora(tam):
        g = _grafica(wb, "column", "Entradas y salidas por hora · carros dentro", eje_y="Vehículos por hora", fmt_y="#,##0")
        g.add_series({"name": "Entradas", "categories": ["Por hora", 4, 1, 3 + nP, 1], "values": ["Por hora", 4, 2, 3 + nP, 2],
                      "fill": {"color": PRI}, "gap": 40})
        g.add_series({"name": "Salidas", "categories": ["Por hora", 4, 1, 3 + nP, 1], "values": ["Por hora", 4, 3, 3 + nP, 3],
                      "fill": {"color": AMBAR}, "gap": 40})
        occ = wb.add_chart({"type": "line"})
        occ.add_series({"name": "Carros dentro (eje derecho)", "categories": ["Por hora", 4, 1, 3 + nP, 1],
                        "values": ["Por hora", 4, 4, 3 + nP, 4], "y2_axis": True, "smooth": True,
                        "line": {"color": PRI_OSC, "width": 2.25},
                        "marker": {"type": "circle", "size": 4, "fill": {"color": PRI_OSC}, "border": {"color": PRI_OSC}}})
        g.combine(occ)
        occ.set_y2_axis({"name": "Carros dentro", "num_format": "#,##0", "num_font": {"size": 8, "color": GRIS}, "name_font": {"size": 9, "color": GRIS},
                         "line": {"none": True}, "min": 0, "max": int(max(cap["A_rot"], perfil["Ocupación carros"].max()) * 1.15)})
        g.set_size(tam)
        return g

    ws.insert_chart(3, 9, graf_hora({"width": 760, "height": 340}))
    ws.write(fin_p + 1, 1, f"Capacidad de carros en rotación: {cap['A_rot']} celdas.", F.nota)

    fila = fin_p + 4
    ws.write(fila, 1, "Horas pico y valle (llegadas)", F.seccion)
    fin_h = _tabla(ws, fila + 2, 1, S["horas"], F, anchos=False)
    ws.conditional_format(fila + 3, 3, fin_h, 3, {"type": "cell", "criteria": "==", "value": '"Pico"', "format": F.mal})
    ws.conditional_format(fila + 3, 3, fin_h, 3, {"type": "cell", "criteria": "==", "value": '"Valle"', "format": F.bien})

    fila = fin_h + 3
    ws.write(fila, 1, "Carros dentro por tipo de día", F.seccion)
    tipos = S["perfil_tipo"]
    if tipos:
        occ_tipo = pd.DataFrame({n: t["Ocupación carros"] for n, t in tipos.items()}).reset_index().rename(columns={"index": "Hora"})
        fin_t = _tabla(ws, fila + 2, 1, occ_tipo, F, formatos={c: F.decimal for c in occ_tipo.columns if c != "Hora"}, anchos=False)
        g_tipo = _grafica(wb, "line", "Carros dentro por hora según el tipo de día", eje_y="Carros dentro", fmt_y="#,##0")
        paleta = [PRI, TEAL, AMBAR, CORAL]
        for j, n in enumerate(occ_tipo.columns[1:]):
            g_tipo.add_series({"name": n, "categories": ["Por hora", fila + 3, 1, fin_t, 1],
                               "values": ["Por hora", fila + 3, 2 + j, fin_t, 2 + j], "smooth": True,
                               "line": {"color": paleta[j % 4], "width": 2.25}})
        g_tipo.set_size({"width": 760, "height": 320})
        ws.insert_chart(fila, 9, g_tipo)
        fila = max(fin_t, fila + 17) + 3

    if len(S["sturges"]):
        ws.write(fila, 1, "Tabla de frecuencias de la hora de llegada (regla de Sturges)", F.seccion)
        si = S["sturges_info"]
        ws.write(fila + 1, 1, f"k = 1 + 3,322·log10({si['n']}) = {si['k_real']:.2f} ≈ {si['k']} clases · amplitud = {si['amplitud']:.3f} h", F.nota)
        stg = S["sturges"][["Clase", "Desde", "Hasta", "Marca de clase", "fi", "hi", "Fi", "Hi"]].rename(columns={"Fi": "Fi (acumulada)", "Hi": "Hi (acumulada)"})
        fin_s = _tabla(ws, fila + 3, 1, stg, F, formatos={"Hi (acumulada)": F.pct, "hi": F.pct}, anchos=False)
        g_st = _grafica(wb, "column", "Vehículos por intervalo de llegada (Sturges)", eje_y="Vehículos (fi)", fmt_y="#,##0")
        g_st.add_series({"name": "fi", "categories": ["Por hora", fila + 4, 2, fin_s, 2], "values": ["Por hora", fila + 4, 5, fin_s, 5],
                         "fill": {"color": TEAL}, "gap": 10})
        g_st.set_legend({"none": True})
        g_st.set_size({"width": 760, "height": 300})
        ws.insert_chart(fila, 9, g_st)
        fila = max(fin_s, fila + 16) + 3

    # un día vehículo por vehículo (imagen)
    if len(res.registro):
        try:
            from . import graficos as G
            i_pico = int(np.argmax(d["Llegadas (media)"].values))
            dia = res.dias[i_pico]
            reg = res.registro[res.registro["fecha"] == dia.fecha]
            if len(reg):
                ws.write(fila, 1, f"Un día simulado vehículo por vehículo: {dia.etiqueta} (el de mayor demanda, réplica 1)", F.seccion)
                ws.write(fila + 1, 1, "Cada línea es un vehículo desde que ENTRA hasta que SALE. Abajo: los carros que hay dentro "
                                      "en cada momento frente a la capacidad.", F.nota)
                ws.insert_image(fila + 3, 1, "dia.png", {"image_data": _imagen(G.gantt_dia(reg, cap["A_rot"])), "x_scale": 0.85, "y_scale": 0.85})
        except Exception:  # la imagen es un extra: si falla, el libro se entrega igual
            pass
    ws.set_column(1, 1, 10); ws.set_column(2, 7, 13)

    # ======================= Mapas de calor =======================
    for nombre_hoja, mapas, desc in [("Calor semana", S["mapas_dsem"], "Promedio por día de la semana"),
                                     ("Calor fechas", S["mapas_fecha"], "Cada fecha simulada")]:
        ws = hojas[nombre_hoja]
        ws.write(0, 1, f"Mapas de calor por hora · {desc}", F.titulo)
        ws.write(1, 1, "Más oscuro = más alto. Azul: volumen de vehículos. Coral: indicadores de riesgo (lleno, sin cupo).", F.subtitulo)
        fila = 3
        for indicador, m in mapas.items():
            pct_ = "%" in indicador
            fila = _mapa(ws, fila, indicador, m, F, rojo=pct_ or "sin cupo" in indicador, porcentaje=pct_)
        ws.set_column(1, 1, 16 if nombre_hoja == "Calor fechas" else 12)
        ws.set_column(2, 20, 6.5)
        ws.freeze_panes(0, 2)

    # ======================= Riesgo =======================
    ws = hojas["Riesgo"]
    ws.write(0, 1, "Riesgo de ingresos", F.titulo)
    ws.write(1, 1, f"Lapso evaluado: {r['dias']} días · vehículos que llegan entre {r['franja']} · {R} réplicas", F.subtitulo)
    ind = [("Ingreso esperado del lapso", r["ingreso_media"], F.cop), ("IC 95 % – límite inferior", r["ic95"][0], F.cop),
           ("IC 95 % – límite superior", r["ic95"][1], F.cop), ("Ingreso P5 (escenario malo)", r["ingreso_p5"], F.cop),
           ("Ingreso P50 (mediana)", r["ingreso_p50"], F.cop), ("Ingreso P95 (escenario bueno)", r["ingreso_p95"], F.cop),
           ("Meta del lapso", r["meta"], F.cop), ("Probabilidad de quedar bajo la meta", r["prob_bajo_meta"], F.pct),
           ("Faltante esperado frente a la meta", r["faltante_esperado"], F.cop), ("VaR 95 % del faltante", r["var95_faltante"], F.cop),
           ("Probabilidad de perder ingresos por falta de cupo", r["prob_perdida_cupo"], F.pct),
           ("Pérdida esperada por falta de cupo", r["perdida_cupo_media"], F.cop),
           ("Pérdida P95 por falta de cupo", r["perdida_cupo_p95"], F.cop),
           ("Nivel de riesgo frente a la meta", r["nivel_meta"], F.texto), ("Nivel de riesgo por falta de cupo", r["nivel_cupo"], F.texto)]
    ws.write(3, 1, "Indicador", F.header); ws.write(3, 2, "Valor", F.header)
    for i, (n, v, fmt) in enumerate(ind):
        ws.write(4 + i, 1, n, F.etiqueta); ws.write(4 + i, 2, _py(v), fmt)
    ws.set_column(1, 1, 44); ws.set_column(2, 2, 20)
    explicacion = ("Cómo leerlo: el ingreso esperado es el promedio de las réplicas. El IC 95 % dice dónde está ese promedio con 95 % de "
                   "confianza. P5 es un escenario malo (solo 5 % de las réplicas ganó menos). El VaR 95 % del faltante es lo máximo que "
                   "faltaría para la meta en el 95 % de los escenarios.")
    ws.merge_range(5 + len(ind), 1, 8 + len(ind), 2, explicacion, F.nota)

    fila = 11 + len(ind)
    hist, kh = _histograma(r["ingreso_por_replica"])
    ws.write(fila, 1, f"Distribución del ingreso (Sturges: k = {kh} clases)", F.seccion)
    fin_hi = _tabla(ws, fila + 2, 1, hist, F, anchos=False)
    g_hi = _grafica(wb, "column", "¿Cuánto se puede ingresar? Réplicas por rango de ingreso", eje_x="Millones de COP", eje_y="Réplicas", rotar=True)
    g_hi.add_series({"name": "Réplicas", "categories": ["Riesgo", fila + 3, 1, fin_hi, 1], "values": ["Riesgo", fila + 3, 4, fin_hi, 4],
                     "fill": {"color": PRI}, "gap": 8})
    g_hi.set_legend({"none": True}); g_hi.set_size({"width": 700, "height": 320})
    ws.insert_chart(3, 7, g_hi)

    fila = fin_hi + 3
    if np.ptp(r["perdida_por_replica"]) > 0:
        hp, kp = _histograma(r["perdida_por_replica"])
        ws.write(fila, 1, f"Ingreso perdido por falta de cupo (Sturges: k = {kp} clases)", F.seccion)
        fin_hp = _tabla(ws, fila + 2, 1, hp, F, anchos=False)
        g_hp = _grafica(wb, "column", "Ingreso perdido por falta de cupo", eje_x="Millones de COP", eje_y="Réplicas", rotar=True)
        g_hp.add_series({"name": "Réplicas", "categories": ["Riesgo", fila + 3, 1, fin_hp, 1], "values": ["Riesgo", fila + 3, 4, fin_hp, 4],
                         "fill": {"color": CORAL}, "gap": 8})
        g_hp.set_legend({"none": True}); g_hp.set_size({"width": 700, "height": 300})
        ws.insert_chart(21, 7, g_hp)
        fila = fin_hp + 3
    else:
        ws.write(fila, 1, "En ninguna réplica se perdieron ingresos por falta de cupo.", F.nota)
        fila += 2

    g_conv = _grafica(wb, "line", "Convergencia: media acumulada del ingreso", eje_x="Número de réplicas", eje_y="COP", fmt_y='"$" #,##0,,"M"')
    g_conv.add_series({"name": "Media acumulada", "categories": ["Réplicas", 4, 1, 3 + R, 1], "values": ["Réplicas", 4, 5, 3 + R, 5],
                       "line": {"color": PRI, "width": 2}})
    g_conv.set_legend({"none": True}); g_conv.set_size({"width": 700, "height": 280})
    g_conv.set_x_axis({"interval_unit": max(1, R // 10), "num_font": {"size": 8, "color": GRIS}, "line": {"color": BORDE},
                       "name": "Número de réplicas", "name_font": {"size": 9, "color": GRIS, "bold": False}})
    ws.insert_chart(38, 7, g_conv)
    ws.write(fila, 1, "Si la curva de convergencia se aplana al final, las réplicas son suficientes.", F.nota)

    fila += 2
    ws.write(fila, 1, "Riesgo por día (dentro de la franja)", F.seccion)
    cols_r = ["Día", "Ingreso en la franja (media)", "Meta de la franja", "Prob. franja < meta", "Pérdida por cupo en la franja"]
    fin_rd = _tabla(ws, fila + 2, 1, d[cols_r], F, anchos=False)
    ws.conditional_format(fila + 3, 4, fin_rd, 4, {"type": "3_color_scale", "min_color": "#FFFFFF", "mid_color": "#F6D3C6",
                                                   "max_color": "#D9785B", "min_type": "num", "min_value": 0, "max_type": "num",
                                                   "max_value": 1, "mid_type": "num", "mid_value": 0.5})
    ws.set_column(3, 3, 18)

    # ======================= Externo =======================
    ws = hojas["Externo"]
    ws.write(0, 1, "¿Conviene abrir un parqueadero externo?", F.titulo)
    ex = res.cfg.externo
    ws.write(1, 1, f"{ex['carros']} celdas para carros y {ex['motos']} para motos · {ex['aceptacion']:.0%} de los conductores sin cupo "
                   f"acepta ir · costo fijo $ {ex['costo_fijo']:,.0f} por día · $ {ex['costo_var']:,.0f} por vehículo".replace(",", "."), F.subtitulo)
    filas_e = [("Decisión", e["decision"], F.texto), ("Beneficio si se abre todos los días", e["beneficio_todo"], F.cop),
               ("Beneficio si se abre solo en los días rentables", e["beneficio_sel"], F.cop),
               ("Probabilidad de ganar abriendo en esos días", e["prob_ganar_sel"], F.pct),
               ("Días en que conviene abrirlo", ", ".join(e["dias_rentables"]) or "Ninguno", F.texto_wrap)]
    for i, (n, v, fmt) in enumerate(filas_e):
        ws.write(3 + i, 1, n, F.etiqueta); ws.write(3 + i, 2, _py(v), fmt)
    ws.set_row(7, 45)
    ext = pd.DataFrame({"Día": [i.etiqueta for i in res.dias], "Vehículos captados (media)": res.RD["ext_captados"].mean(0),
                        "Ingreso externo (media)": res.RD["ext_ingreso"].mean(0),
                        "Beneficio del día (media)": (res.RD["ext_ingreso"] - ex["costo_var"] * res.RD["ext_captados"] - ex["costo_fijo"]).mean(0)})
    fin_e = _tabla(ws, 10, 1, ext, F)
    ws.set_column(1, 1, 44); ws.set_column(2, 2, 30)
    g_e = _grafica(wb, "column", "Beneficio esperado de abrir el externo cada día", eje_y="COP", fmt_y='"$" #,##0', rotar=D > 10)
    g_e.add_series({"name": "Beneficio del día", "categories": ["Externo", 11, 1, fin_e, 1], "values": ["Externo", 11, 4, fin_e, 4],
                    "fill": {"color": TEAL}, "invert_if_negative": True, "invert_if_negative_color": CORAL, "gap": 60})
    g_e.set_legend({"none": True}); g_e.set_size({"width": 720, "height": 320})
    ws.insert_chart(3, 6, g_e)
    ws.write(fin_e + 2, 1, "Verde: el día deja ganancia. Coral: el día da pérdida (no compensa el costo fijo).", F.nota)

    # ======================= Calendario =======================
    ws = hojas["Calendario"]
    ws.write(0, 1, "Calendario de los días simulados", F.titulo)
    ws.write(1, 1, "Tipo de día, festivo, quincena, puente y temporada. El factor multiplica la demanda de octubre (octubre = 1,00).", F.subtitulo)
    temp = pd.DataFrame([{"Fecha": i.fecha, "Día": cal.DIA_SEMANA[i.fecha.weekday()], "Tipo de día": cal.TIPO_NOMBRE[i.tipo],
                          "Festivo": i.festivo["nombre"] if i.festivo else "", "Quincena": "Sí" if i.quincena else "",
                          "Puente": i.puente or "", "Eventos": ", ".join(ev.nombre for ev in i.eventos),
                          "Factor de temporada": round(i.factor_temporada, 3), "Temporada": i.temporada,
                          "Por qué": i.motivo_temporada} for i in res.dias])
    fin_c = _tabla(ws, 3, 1, temp, F)
    col_t = 1 + list(temp.columns).index("Temporada")
    ws.conditional_format(4, col_t, fin_c, col_t, {"type": "cell", "criteria": "==", "value": '"Alta"', "format": F.mal})
    ws.conditional_format(4, col_t, fin_c, col_t, {"type": "cell", "criteria": "==", "value": '"Baja"', "format": F.bien})
    ws.set_column(1 + list(temp.columns).index("Por qué"), 1 + list(temp.columns).index("Por qué"), 70)
    fest = pd.DataFrame([{"Fecha": i.fecha, "Festivo": i.festivo["nombre"], "Por qué es festivo": i.festivo["motivo"],
                          "Fecha original": i.festivo["fecha_original"]} for i in res.dias if i.festivo])
    ws.write(fin_c + 3, 1, "Festivos del periodo", F.seccion)
    _tabla(ws, fin_c + 5, 1, fest, F, anchos=False)

    # ======================= Réplicas =======================
    ws = hojas["Réplicas"]
    ws.write(0, 1, "Resultado de cada réplica (lapso completo)", F.titulo)
    ws.write(1, 1, "Cada réplica es una versión posible del periodo, generada con números aleatorios distintos.", F.subtitulo)
    rep = pd.DataFrame({"Réplica": np.arange(1, R + 1), "Ingreso": r["ingreso_por_replica"], "Pérdida por cupo": r["perdida_por_replica"],
                        "Faltante vs meta": r["faltante_por_replica"], "Media acumulada": r["convergencia"],
                        "Vehículos que llegan": res.RD["llegadas"].sum(1)})
    _tabla(ws, 3, 1, rep, F, formatos={"Réplica": F.entero, "Vehículos que llegan": F.entero})
    ws.freeze_panes(4, 0)

    # ======================= Vehículos =======================
    ws = hojas["Vehículos"]
    ws.write(0, 1, "Cada vehículo simulado (réplica 1)", F.titulo)
    ws.write(1, 1, "Hora de llegada, de entrada (si encontró celda) y de salida. Usa los filtros del encabezado para buscar.", F.subtitulo)
    if len(res.registro):
        reg = res.registro.head(200_000)
        veh = pd.DataFrame({"Fecha": reg["fecha"], "N°": reg["vehiculo_id"], "Flujo": reg["flujo"], "Vehículo": reg["tipo_vehiculo"],
                            "Cliente": reg["tipo_cliente"], "Zona": reg["zona"], "Llegada": reg["llegada_h"] / 24,
                            "Entrada": reg["entrada_h"] / 24, "Salida": reg["salida_h"] / 24, "Permanencia (min)": reg["permanencia_min"],
                            "Espera (min)": reg["espera_min"], "Estado": reg["estado"], "Valor (COP)": reg["valor_cop"]})
        fin_v = _tabla(ws, 3, 1, veh, F, formatos={"N°": F.entero, "Llegada": F.hora, "Entrada": F.hora, "Salida": F.hora,
                                                     "Permanencia (min)": F.decimal, "Espera (min)": F.decimal}, anchos=False)
        for j, w in enumerate([11, 7, 12, 12, 11, 20, 9, 9, 9, 12, 10, 22, 13]):
            ws.set_column(1 + j, 1 + j, w)
        ws.conditional_format(4, 12, fin_v, 12, {"type": "text", "criteria": "containing", "value": "sin cupo", "format": F.mal})
        ws.conditional_format(4, 12, fin_v, 12, {"type": "text", "criteria": "containing", "value": "esperar", "format": wb.add_format({"bg_color": "#FBF0D9"})})
        ws.freeze_panes(4, 0)

    # ======================= Parámetros y guía =======================
    ws = hojas["Parámetros y guía"]
    ws.write(0, 1, "Cómo leer este libro y con qué supuestos se simuló", F.titulo)
    guia = [("Resumen", "Tablero con los indicadores clave, las recomendaciones y las gráficas principales."),
            ("Por día", "Una fila por día: vehículos (media, P5, P95), probabilidad de lleno, ocupación pico, ingreso y meta."),
            ("Por hora", "Entradas vs salidas por hora, carros dentro, horas pico/valle, tabla de Sturges y un día vehículo por vehículo."),
            ("Calor semana", "Mapas de calor día de la semana × hora (llegadas, entradas, salidas, ocupación, lleno, sin cupo)."),
            ("Calor fechas", "Los mismos mapas para cada fecha simulada."),
            ("Riesgo", "Ingreso esperado, intervalo de confianza, probabilidad de no llegar a la meta, VaR 95 % e histogramas."),
            ("Externo", "Beneficio de abrir un parqueadero externo para los conductores que no encuentran cupo."),
            ("Calendario", "Tipo de día, festivo, quincena, puente y factor de temporada de cada fecha, con su motivo."),
            ("Réplicas", "Ingreso, pérdida y faltante de cada réplica (los datos de los histogramas y de la convergencia)."),
            ("Vehículos", "Cada vehículo de la réplica 1: llegada, entrada, salida, permanencia, espera, estado y valor cobrado.")]
    ws.write(2, 1, "Hoja", F.header); ws.write(2, 2, "Qué contiene", F.header)
    for i, (h, t) in enumerate(guia):
        ws.write_url(3 + i, 1, f"internal:'{h}'!A1", string=h)
        ws.write(3 + i, 2, t, F.texto_wrap)
    ws.set_column(1, 1, 34); ws.set_column(2, 2, 100)

    cfg = res.cfg
    tar = cfg.tarifas or P.tarifas
    params = [("Periodo simulado", periodo), ("Días simulados", D), ("Réplicas por día", R), ("Jornadas simuladas", k["jornadas"]),
              ("Generador de números aleatorios", res.generador), ("Semilla", cfg.semilla),
              ("Crecimiento de la demanda frente a octubre", f"{cfg.crecimiento:+.0%}"),
              ("Celdas de carros (rotación / mensualidad)", f"{cap['A_rot']} / {cap['A_men']}"),
              ("Celdas de motos (rotación / mensualidad)", f"{cap['M_rot']} / {cap['M_men']}"), ("Muelle de carga", cap["C"]),
              ("Espera máxima de un conductor (min)", cfg.tolerancia_min), ("Espera máxima de un proveedor (min)", cfg.tolerancia_prov_min),
              ("Franja evaluada en el riesgo", r["franja"]),
              ("Meta", "Valor fijo" if cfg.meta_fija else ("Octubre ajustado por temporada" if cfg.meta_temporada else "Octubre sin ajustar")
               + f" × {cfg.meta_pct:.0%}"),
              ("Minutos de gracia", tar["gracia_min"]), ("Recargo por ticket extraviado (COP)", tar["recargo_extravio"]),
              ("Descuento a convenios", f"{tar['descuento']['Convenio']:.0%}")]
    params += [(f"Tarifa {v} (hora o fracción / tope 24 h)", f"$ {tar['tarifa_hora'][v]:,.0f} / $ {tar['tope_24h'][v]:,.0f}".replace(",", "."))
               for v in tar["tarifa_hora"]]
    params += [("Tiempo de cálculo (s)", round(res.segundos, 1)), ("Archivo generado", dt.datetime.now().strftime("%d/%m/%Y %H:%M"))]
    f0 = 5 + len(guia)
    ws.write(f0, 1, "Parámetros usados", F.seccion)
    for i, (n, v) in enumerate(params):
        ws.write(f0 + 2 + i, 1, n, F.etiqueta); ws.write(f0 + 2 + i, 2, _py(v), F.texto)
    f1 = f0 + 4 + len(params)
    ws.write(f1, 1, "Método", F.seccion)
    metodo = ("Montecarlo de entradas y salidas: en cada réplica y cada día se sortea un factor del día (Box–Muller), las llegadas de "
              "cada hora (Poisson con la tasa de octubre × temporada × quincena × crecimiento), el tipo de vehículo y cliente, y la "
              "permanencia (percentiles reales de octubre). Cada vehículo entra si hay celda libre; si no, espera hasta la tolerancia y, "
              "si nadie sale, se va sin parquear (ingreso perdido). La salida es la entrada más la permanencia. Repetir muchas réplicas "
              "da promedios, percentiles y probabilidades.")
    ws.merge_range(f1 + 1, 1, f1 + 5, 2, metodo, F.texto_wrap)

    # ======================= Resumen (tablero) =======================
    ws = hojas["Resumen"]
    ws.activate()
    ws.set_column(1, 12, 18)
    for c in (3, 6, 9):
        ws.set_column(c, c, 2.5)
    ws.set_row(0, 8)
    ws.merge_range(1, 1, 2, 11, "Simulación Montecarlo · Parqueadero C.C. Plaza El Mirador", F.banner)
    ws.set_row(1, 22); ws.set_row(2, 16)
    ws.merge_range(3, 1, 3, 11, f"Periodo {periodo}  ·  {D} días  ·  {R} réplicas por día  ·  {k['jornadas']:,} jornadas simuladas  ·  "
                                f"generado el {dt.datetime.now():%d/%m/%Y %H:%M}".replace(",", "."), F.banner_sub)
    ws.set_row(3, 20)

    tarjetas = [
        ("VEHÍCULOS ESPERADOS", k["llegadas_total"], "entero", f"≈ {k['llegadas_dia']:,.0f} por día".replace(",", "."), PRI),
        ("SE VAN SIN CUPO", k["sin_cupo_total"], "entero", "vehículos en todo el periodo", CORAL),
        ("PROB. DE LLENO (CARROS)", k["prob_carros_llenos"], "pct", "de las jornadas llega al 100 %", CORAL),
        ("OCUPACIÓN PICO MÁXIMA", k["ocupacion_pico"], "pct", f"día: {k['dia_ocupacion_pico']}", AMBAR),
        ("INGRESO ESPERADO", r["ingreso_media"], "cop", f"franja {r['franja']}", TEAL),
        ("PROB. DE QUEDAR BAJO LA META", r["prob_bajo_meta"], "pct", f"meta: $ {r['meta']:,.0f}".replace(",", "."), CORAL),
        ("PÉRDIDA POR FALTA DE CUPO", r["perdida_cupo_media"], "cop", f"riesgo {r['nivel_cupo'].lower()}", AMBAR),
        ("PARQUEADERO EXTERNO", e["decision"].capitalize(), "texto", f"{len(e['dias_rentables'])} días rentables", TEAL),
    ]
    cols_t = [1, 4, 7, 10]
    for n, (lab, val, tipo, nota, color) in enumerate(tarjetas):
        f = 5 + (n // 4) * 5
        c = cols_t[n % 4]
        ws.merge_range(f, c, f, c + 1, "", F.card_barra[color])
        ws.merge_range(f + 1, c, f + 1, c + 1, lab, F.card_lab)
        ws.merge_range(f + 2, c, f + 2, c + 1, _py(val), F.card_val[tipo])
        ws.merge_range(f + 3, c, f + 3, c + 1, nota, F.card_nota)
    for f in (5, 10):
        ws.set_row(f, 4); ws.set_row(f + 1, 18); ws.set_row(f + 2, 34); ws.set_row(f + 3, 18)

    fr = 15
    ws.merge_range(fr, 1, fr, 11, "Qué debe preparar el parqueadero", F.seccion)
    for i, t in enumerate(recomendaciones(S)):
        ws.merge_range(fr + 1 + i, 1, fr + 1 + i, 11, f"•  {t}", F.bullet)
        ws.set_row(fr + 1 + i, 17 * max(1, math.ceil(len(t) / 200)) + 5)
    fg = fr + 2 + len(recomendaciones(S)) + 1
    ws.merge_range(fg, 1, fg, 11, "Gráficas principales", F.seccion)
    tam = {"width": 560, "height": 320}
    ws.insert_chart(fg + 2, 1, graf_llegadas(tam), {"x_offset": 2})
    ws.insert_chart(fg + 2, 7, graf_hora(tam), {"x_offset": 2})
    ws.insert_chart(fg + 19, 1, graf_ingreso(tam), {"x_offset": 2})
    ws.insert_chart(fg + 19, 7, graf_lleno(tam), {"x_offset": 2})
    ws.merge_range(fg + 36, 1, fg + 36, 11, "Más detalle en las demás hojas; la hoja 'Parámetros y guía' explica qué contiene cada una.", F.nota)
    ws.set_landscape(); ws.fit_to_pages(1, 0)

    wb.close()
    return buf.getvalue()
