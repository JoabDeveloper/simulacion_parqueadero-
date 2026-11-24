"""
Simulador Montecarlo del parqueadero – C.C. Plaza El Mirador
Interfaz en Streamlit (todo en Python). Ejecutar con:   streamlit run app.py

La lógica está en el paquete `parqueadero/`:
  calendario.py    festivos de Colombia (con su motivo), temporada alta/baja, quincena, puentes
  datos.py         lectura del registro de octubre, tarifas y tabla de Sturges
  parametros.py    estimación de los parámetros (llegadas por hora, mezcla, permanencias, capacidad)
  generador.py     números aleatorios (congruencial multiplicativo) y pruebas χ² de uniformidad y de series
  motor.py         simulación Montecarlo de ENTRADAS y SALIDAS vehículo por vehículo
  estadisticas.py  KPIs, mapas de calor por hora, picos/valles, riesgo de ingresos, validación, recomendaciones
  graficos_web.py  gráficos interactivos de la interfaz (Altair)
  graficos.py      gráficos estáticos con matplotlib (línea de comandos)
  vista.py         sistema visual: estilos, banners, paneles, tarjetas, insignias y calendario en HTML
  reporte.py       libro de Excel con tablas, mapas de calor y gráficas

Organización de la página: cada pestaña tiene un tono propio y abre con un banner; su contenido va en
paneles (contenedores con key «panel-<tono>-n») con cabecera de icono, título y descripción.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from parqueadero import calendario as cal
from parqueadero import graficos_web as W
from parqueadero import vista
from parqueadero.estadisticas import recomendaciones, resumen, validar
from parqueadero.generador import crear_generador, prueba_series, prueba_uniformidad
from parqueadero.motor import Config, simular
from parqueadero.parametros import FLUJO_NOMBRE, HORAS, cargar_y_estimar
from parqueadero.reporte import a_excel
from parqueadero.vista import kpi

RAIZ = Path(__file__).parent
DATOS = RAIZ / "datos" / "Registro_parqueadero_simulado_oct2026-2.xlsx"
PERIODO = lambda p: f"{p[0]:%d/%m/%Y} – {p[1]:%d/%m/%Y}"
NUM = W.n_es
COP = W.cop
PCT = lambda v: W.n_es(100 * v, 1) + " %"
DIA2 = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"]
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

st.set_page_config(page_title="Parqueadero Plaza El Mirador · Análisis", page_icon="🅿️", layout="wide",
                   initial_sidebar_state="auto")  # abierta en computador, recogida en celular
st.markdown(vista.ESTILOS, unsafe_allow_html=True)


def html_md(texto: str):
    st.markdown(texto, unsafe_allow_html=True)


def grafico(chart):
    """Muestra un gráfico interactivo de Altair con el estilo propio (sin el tema por defecto de Streamlit)."""
    st.altair_chart(chart, width="stretch", theme=None)


_num_panel = itertools.count()


@contextmanager
def panel(titulo: str, nota: str = "", icono: str = "dashboard", tono: str = "azul", accion=None):
    """Bloque de contenido con cabecera (icono + título + descripción) y franja superior del tono de la sección."""
    with st.container(key=f"panel-{tono}-{next(_num_panel)}"):
        if accion:
            a, b = st.columns([3.3, 1], vertical_alignment="center")
            with a:
                html_md(vista.panel_cabecera(titulo, nota, icono))
            with b:
                accion()
        else:
            html_md(vista.panel_cabecera(titulo, nota, icono))
        yield


# ---- semáforos: convierten un valor en una insignia de estado (icono + texto) ----
def estado_prob_lleno(p):
    return ("Holgado", "bien") if p < 0.05 else (("Vigilar", "atencion") if p < 0.25 else ("Crítico", "critico"))


def estado_sin_cupo(p):
    return ("Mínimo", "bien") if p < 0.005 else (("Moderado", "atencion") if p < 0.02 else ("Alto", "critico"))


def estado_ocupacion(p):
    return ("Holgada", "bien") if p < 0.85 else (("Ajustada", "atencion") if p < 0.97 else ("Al límite", "critico"))


def estado_espera(m):
    return ("Ágil", "bien") if m <= 5 else (("Moderada", "atencion") if m <= 10 else ("Lenta", "critico"))


def estado_nivel(n):
    return {"Bajo": ("Riesgo bajo", "bien"), "Medio": ("Riesgo medio", "atencion"), "Alto": ("Riesgo alto", "critico")}[n]


def estado_externo(decision):
    if decision.startswith("VIABLE SOLO") or decision.startswith("VIABLE TODO"):
        return ("Viable", "bien")
    return ("Con riesgo", "atencion") if "RIESGO" in decision else ("No viable", "neutro")


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Leyendo el registro de octubre y estimando los parámetros…")
def cargar(ruta: str):
    return cargar_y_estimar(ruta)


@st.cache_data(show_spinner="Validando el modelo contra octubre…")
def validar_cache(ruta: str, replicas: int):
    return validar(cargar(ruta)[1], replicas=replicas)


ss = st.session_state
ss.setdefault("sel", {dt.date(2026, 12, 1) + dt.timedelta(days=i) for i in range(31)})
ss.setdefault("anio", 2026)
ss.setdefault("mes", 12)


def restablecer_parametros():
    for k in [k for k in ss.keys() if str(k).startswith("p_")]:
        del ss[k]


def grupo_lateral(texto: str, icono: str, tono: str):
    html_md(f'<div class="lado-grupo tono-{tono}">{vista.icono(icono)}{texto}</div>')


# La barra lateral se arma en dos partes: arriba los parámetros y abajo el archivo de datos,
# pero el archivo se lee primero porque los valores por defecto salen de él.
lateral = st.sidebar.container()
with st.sidebar:
    grupo_lateral("Datos", "database", "pizarra")
    with st.expander("Datos de entrada", icon=":material/upload_file:"):
        subido = st.file_uploader("Registro del parqueadero (.xlsx)", type=["xlsx"],
                                  help="Si no subes nada se usa el registro de octubre de 2026 que viene con el programa.")
        st.caption("Opcional. Debe tener la hoja «Registro» con el mismo formato que el archivo de octubre.")
if subido is not None:
    contenido = subido.getvalue()
    ruta = Path(tempfile.gettempdir()) / f"registro_{hashlib.md5(contenido).hexdigest()}.xlsx"
    ruta.write_bytes(contenido)
    RUTA = str(ruta)
else:
    RUTA = str(DATOS)
df, P = cargar(RUTA)

# ---------------------------------------------------------------------------
# Barra lateral: parámetros
# ---------------------------------------------------------------------------
with lateral:
    html_md(f'<div class="lado-cab"><div class="ico">{vista.icono("tune")}</div><div><b>Parámetros</b>'
            '<small>Valores por defecto de octubre de 2026</small></div></div>')
    st.button("Restablecer valores de octubre", icon=":material/restart_alt:", on_click=restablecer_parametros,
              width="stretch", help="Devuelve todos los parámetros a los valores estimados de octubre de 2026.")

    grupo_lateral("Escenario", "tune", "azul")
    replicas = st.slider("Réplicas por día", 50, 2000, 300, 50, key="p_replicas",
                         help="Cada réplica es una jornada completa generada con números aleatorios distintos. Más réplicas = resultados más estables, pero tarda más.")
    crecimiento = st.slider("Crecimiento de la demanda", -30, 100, 0, 5, format="%d %%", key="p_crec",
                            help="Frente a octubre (ya ajustado por temporada). 20 % = un 20 % más de vehículos.") / 100
    st.caption("Los cambios se aplican al pulsar **Simular**.")

    grupo_lateral("Operación", "local_parking", "teal")
    with st.expander("Capacidad y espera", icon=":material/local_parking:"):
        c = P.capacidad
        cap = {
            "A_rot": st.number_input("Celdas de carros (rotación)", 10, 3000, c["A_rot"], 5, key="p_cap_a"),
            "A_men": st.number_input("Celdas de carros (mensualidad)", 0, 1000, c["A_men"], 5, key="p_cap_am"),
            "M_rot": st.number_input("Celdas de motos (rotación)", 0, 1000, c["M_rot"], 5, key="p_cap_m"),
            "M_men": st.number_input("Celdas de motos (mensualidad)", 0, 500, c["M_men"], 5, key="p_cap_mm"),
            "C": st.number_input("Muelle de carga (furgones)", 1, 50, c["C"], 1, key="p_cap_c"),
        }
        tol = st.number_input("Minutos que un conductor espera por una celda", 0, 60, 10, 1, key="p_tol")
        tolp = st.number_input("Minutos que un proveedor espera el muelle", 0, 120, 30, 5, key="p_tolp")

    with st.expander("Parqueadero externo", icon=":material/add_business:"):
        externo = dict(
            carros=st.number_input("Celdas externas para carros", 0, 1000, 60, 5, key="p_ext_c"),
            motos=st.number_input("Celdas externas para motos", 0, 500, 20, 5, key="p_ext_m"),
            aceptacion=st.slider("Conductores sin cupo que aceptan ir al externo", 0, 100, 60, 5, format="%d %%", key="p_ext_ac") / 100,
            factor_tarifa=st.number_input("Tarifa externa (× tarifa normal)", 0.1, 2.0, 1.0, 0.05, key="p_ext_ft"),
            costo_fijo=st.number_input("Costo fijo por día abierto (COP)", 0, 50_000_000, 450_000, 50_000, key="p_ext_cf"),
            costo_var=st.number_input("Costo por vehículo atendido (COP)", 0, 100_000, 1_500, 500, key="p_ext_cv"),
        )

    grupo_lateral("Dinero", "payments", "ambar")
    with st.expander("Tarifas", icon=":material/sell:"):
        t0 = P.tarifas
        tarifas = {"tarifa_hora": {}, "tope_24h": {}, "descuento": dict(t0["descuento"]),
                   "gracia_min": t0["gracia_min"], "recargo_extravio": t0["recargo_extravio"]}
        for v in ["Automóvil", "Camioneta", "Motocicleta", "Furgón"]:
            a, b = st.columns(2)
            tarifas["tarifa_hora"][v] = a.number_input(f"{v}: hora", 0, 100000, int(t0["tarifa_hora"][v]), 100, key=f"p_th_{v}")
            tarifas["tope_24h"][v] = b.number_input(f"{v}: tope 24 h", 0, 500000, int(t0["tope_24h"][v]), 1000, key=f"p_tt_{v}")
        tarifas["descuento"]["Convenio"] = st.slider("Descuento a convenios", 0, 100, int(100 * t0["descuento"]["Convenio"]), 5,
                                                     format="%d %%", key="p_desc") / 100
        tarifas["gracia_min"] = st.number_input("Minutos de gracia (no se cobra)", 0, 60, int(t0["gracia_min"]), 1, key="p_gracia")
        tarifas["recargo_extravio"] = st.number_input("Recargo por ticket extraviado", 0, 200000, int(t0["recargo_extravio"]), 1000, key="p_recargo")

    with st.expander("Meta de ingresos", icon=":material/flag:"):
        modo_meta = st.radio("¿Cómo se fija la meta?", ["Octubre ajustado por temporada", "Octubre sin ajustar", "Valor fijo para el lapso"],
                             key="p_modo_meta",
                             help="Octubre ajustado: la meta de cada día es lo que ingresó un día igual de octubre × el factor de temporada de ese día.")
        meta_temporada = modo_meta.startswith("Octubre ajustado")
        if modo_meta.startswith("Octubre"):
            meta_pct, meta_fija = st.slider("Meta = % de esa referencia", 50, 150, 100, 5, format="%d %%", key="p_meta_pct") / 100, None
        else:
            meta_pct, meta_fija = 1.0, float(st.number_input("Meta del lapso (COP)", 0, 10_000_000_000, 150_000_000, 1_000_000, key="p_meta_fija"))

    grupo_lateral("Demanda", "event", "violeta")
    with st.expander("Temporada alta / baja", icon=":material/sunny:"):
        st.caption("Octubre = 1,00. Edita los factores si tienes información más reciente.")
        tabla_mes = pd.DataFrame({"Mes": cal.MESES, "Factor": [cal.FACTOR_MES[m][0] for m in range(1, 13)]})
        tabla_mes = st.data_editor(tabla_mes, hide_index=True, disabled=["Mes"], key="p_ed_mes", width="stretch",
                                   column_config={"Factor": st.column_config.NumberColumn(min_value=0.3, max_value=3.0, step=0.01, format="%.2f")})
        factores_mes = {i + 1: float(f) for i, f in enumerate(tabla_mes["Factor"])}
        f_ev = {
            "black_viernes": st.number_input("Black Friday", 0.5, 3.0, 1.30, 0.05, key="p_ev_bf"),
            "black_finde": st.number_input("Sábado y domingo del Black Weekend", 0.5, 3.0, 1.15, 0.05, key="p_ev_bw"),
            "navidad_semana": st.number_input("Semana previa a Navidad (18–24 dic)", 0.5, 3.0, 1.10, 0.05, key="p_ev_nav"),
            "halloween": st.number_input("Halloween (31 oct)", 0.5, 3.0, 1.10, 0.05, key="p_ev_hw"),
            "madre": st.number_input("Día de la Madre", 0.5, 3.0, 1.20, 0.05, key="p_ev_ma"),
            "padre": st.number_input("Día del Padre", 0.5, 3.0, 1.15, 0.05, key="p_ev_pa"),
            "amor": st.number_input("Amor y Amistad", 0.5, 3.0, 1.10, 0.05, key="p_ev_am"),
        }
        f_puente = st.number_input("Factor de los días de puente festivo", 0.5, 1.5, 1.0, 0.05, key="p_puente",
                                   help="En octubre el puente de la Raza tuvo un fin de semana alto, por eso el valor por defecto es 1,00.")

    grupo_lateral("Aleatoriedad", "casino", "indigo")
    with st.expander("Generador y semilla", icon=":material/casino:"):
        semilla = st.number_input("Semilla", 1, 2_147_483_646, 12345, 1, key="p_semilla",
                                  help="Con la misma semilla se obtienen exactamente los mismos resultados.")
        gen_nombre = st.selectbox("Generador de números aleatorios", ["Congruencial multiplicativo (Park–Miller)", "NumPy PCG64"], key="p_gen")


def configuracion(franja) -> Config:
    return Config(replicas=int(replicas), semilla=int(semilla), generador="congruencial" if gen_nombre.startswith("Congr") else "numpy",
                  crecimiento=crecimiento, tolerancia_min=tol, tolerancia_prov_min=tolp, capacidad=cap, tarifas=tarifas,
                  meta_pct=meta_pct, meta_fija=meta_fija, meta_temporada=meta_temporada, franja=tuple(franja), factores_mes=factores_mes,
                  factores_eventos=f_ev, factor_puente=f_puente, externo=externo)


# ---------------------------------------------------------------------------
# Calendario: funciones que se ejecutan al hacer clic (antes de redibujar)
# ---------------------------------------------------------------------------
RAPIDAS = {"Todo el mes": "todo", "Lun–Jue": "lj", "Fines de semana y festivos": "finde", "Festivos": "festivos",
           "Quincenas": "quincena", "Temporada alta": "alta", "Quitar este mes": "limpiar_mes", "Quitar todo": "limpiar_todo"}


def mover_mes(delta: int):
    m, a = ss.mes + delta, ss.anio
    if m < 1:
        m, a = 12, a - 1
    if m > 12:
        m, a = 1, a + 1
    ss.mes, ss.anio = m, a


def dias_mes(anio, mes):
    return [f for sem in cal.semanas_del_mes(anio, mes) for f in sem if f.month == mes]


def seleccionar(regla: str):
    dias = dias_mes(ss.anio, ss.mes)
    reglas = {
        "todo": lambda f: True,
        "lj": lambda f: cal.tipo_dia(f) == "LJ",
        "finde": lambda f: cal.tipo_dia(f) in ("SA", "DF"),
        "festivos": lambda f: cal.festivo(f) is not None,
        "quincena": lambda f: cal.es_quincena(f),
        "alta": lambda f: cal.clasificar(f, factores_mes, f_ev, f_puente).temporada == "Alta",
    }
    if regla == "limpiar_mes":
        ss.sel.difference_update(dias)
    elif regla == "limpiar_todo":
        ss.sel.clear()
    else:
        ss.sel.update(f for f in dias if reglas[regla](f))


def aplicar_rapida():
    eleccion = ss.get("rapida")
    if eleccion:
        seleccionar(RAPIDAS[eleccion])
    ss.rapida = None


def cambiar_dias(anio, mes):
    elegidos = set(ss.get(f"dias_{anio}_{mes}") or [])
    ss.sel.difference_update(dias_mes(anio, mes))
    ss.sel.update(elegidos)


def agregar_rango():
    r = ss.get("rango")
    if isinstance(r, (list, tuple)) and len(r) == 2:
        a, b = r
        ss.sel.update(a + dt.timedelta(days=i) for i in range((b - a).days + 1))


def pedir_simulacion(fechas: tuple, franja: tuple):
    """Al pulsar Simular: se guarda el pedido y la simulación corre al inicio de la siguiente ejecución."""
    ss.pedido = (list(fechas), tuple(franja))


@st.cache_resource
def ejecutor_excel() -> ThreadPoolExecutor:
    """Hilos para armar el Excel en segundo plano mientras el usuario revisa los resultados."""
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="excel")


def preparar_excel():
    """Empieza a armar el Excel de la simulación actual en segundo plano (no bloquea la página)."""
    ss.excel_futuro = (ejecutor_excel().submit(a_excel, ss.S, ss.res, P), ss.res)


def boton_excel(clave: str, tipo="secondary"):
    """
    Botón de descarga directa (un solo clic). El Excel se empieza a armar en segundo plano apenas termina la
    simulación; al pulsar el botón se entrega ya listo o, si aún le faltan segundos, en cuanto termina.
    """
    if "res" not in ss:
        return
    if ss.get("excel_futuro") is None:
        preparar_excel()
    futuro, r = ss.excel_futuro
    if futuro.done() and futuro.exception():
        st.error(f"No se pudo preparar el Excel: {futuro.exception()}")
        st.button("Reintentar el Excel", key=f"reint_{clave}", on_click=preparar_excel, width="stretch")
        return
    st.download_button("Descargar en Excel", data=futuro.result, key=clave, type=tipo, icon=":material/download:",
                       file_name=f"simulacion_parqueadero_{r.dias[0].fecha:%Y%m%d}_{r.dias[-1].fecha:%Y%m%d}.xlsx",
                       mime=MIME_XLSX, width="stretch", on_click="ignore",
                       help="Libro con todas las tablas y gráficas de esta simulación.")


def sin_resultados(tono: str):
    html_md(vista.vacio("Todavía no hay resultados",
                        "Ve a la pestaña <b>Calendario</b>, elige los días y pulsa <b>Simular</b>.<br>Los resultados aparecerán aquí.",
                        "play_circle", tono))


def pills_periodo(res) -> list[str]:
    return [f"<b>{len(res.dias)}</b> días", f"{res.dias[0].fecha:%d/%m/%Y} – {res.dias[-1].fecha:%d/%m/%Y}",
            f"<b>{res.cfg.replicas}</b> réplicas por día"]


# ---------------------------------------------------------------------------
# Simulación pedida
# ---------------------------------------------------------------------------
# Corre ANTES de dibujar el encabezado y las pestañas: el progreso se ve en cualquier pestaña en la que esté
# el usuario y, al terminar, todas las pestañas se dibujan en esta misma ejecución ya con los resultados.
# El espacio del progreso se reserva SIEMPRE (aunque no se simule): si solo existiera al simular, las pestañas
# cambiarían de posición entre ejecuciones y Streamlit las reiniciaría, devolviendo al usuario a «Inicio».
zona = st.empty()
if ss.get("pedido"):
    fechas_p, franja_p = ss.pop("pedido")
    with zona.container(key="panel-azul-simulando"):
        html_md(vista.panel_cabecera(
            f"Simulando {len(fechas_p)} días × {int(replicas)} réplicas…",
            "Puedes quedarte en cualquier pestaña: los resultados aparecen solos al terminar.", "hourglass_top"))
        barra = st.progress(0.0, text="Preparando la simulación…")
        res = simular(P, fechas_p, configuracion(franja_p),
                      progreso=lambda x: barra.progress(min(0.95, 0.95 * x), text=f"Simulando… {x:.0%} de los días"))
        barra.progress(0.97, text="Calculando indicadores y riesgo…")
        S = resumen(res, P)
    zona.empty()
    ss.res, ss.S = res, S
    ss.sim = ss.get("sim", 0) + 1
    preparar_excel()   # el Excel se arma en segundo plano mientras el usuario revisa los resultados
    st.toast(f"Simulación lista: {len(res.dias)} días en {res.segundos:.1f} s", icon=":material/check_circle:")

# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
H = P.historico
chips = [("database", f"Datos base <b>{PERIODO(H['periodo'])}</b>"), ("directions_car", f"<b>{NUM(H['n'])}</b> vehículos registrados"),
         ("local_parking", f"<b>{P.capacidad['A_rot']}</b> celdas carros · <b>{P.capacidad['M_rot']}</b> motos · muelle <b>{P.capacidad['C']}</b>")]
if "res" in ss:
    estado = (f"Simulación lista · {len(ss.res.dias)} días × {ss.res.cfg.replicas} réplicas", True)
else:
    estado = ("Sin simular todavía", False)
html_md(vista.encabezado("Parqueadero Plaza El Mirador",
                         "Centro de análisis de ocupación, ingresos y riesgo · entradas y salidas vehículo por vehículo", chips, estado))

tabs = st.tabs([":material/home: Inicio", ":material/calendar_month: Calendario", ":material/insights: Resultados",
                ":material/schedule: Por hora", ":material/payments: Riesgo e ingresos", ":material/science: Modelo y datos"])

# ===========================================================================
# 0. INICIO  (tono índigo)
# ===========================================================================
with tabs[0]:
    html_md(vista.banner("Bienvenido al simulador",
                         "Simula, vehículo por vehículo, cómo se comporta el parqueadero en los días que elijas y mide el riesgo de "
                         "llenarse o de no llegar a la meta de ingresos.", "waving_hand", "indigo",
                         [f"<b>{NUM(H['n'])}</b> vehículos de base", "<b>6</b> secciones"]))

    with panel("Cómo usarlo", "Cuatro pasos. Los valores por defecto ya sirven, así que puedes simular de inmediato.", "route", "indigo"):
        html_md("""
<div class="pasos">
  <div class="paso tono-azul"><div class="cab"><div class="ico"><span class="mi">calendar_month</span></div><div class="num">01</div></div>
  <b>Elige los días</b><span>En <b>Calendario</b> marca los días a simular: un mes, solo fines de semana, una temporada o un rango de fechas.</span></div>
  <div class="paso tono-violeta"><div class="cab"><div class="ico"><span class="mi">tune</span></div><div class="num">02</div></div>
  <b>Ajusta si quieres</b><span>En la barra lateral cambias réplicas, capacidad, tarifas, la meta o la demanda. <b>Restablecer</b> vuelve a octubre.</span></div>
  <div class="paso tono-teal"><div class="cab"><div class="ico"><span class="mi">play_arrow</span></div><div class="num">03</div></div>
  <b>Pulsa Simular</b><span>Se generan cientos de jornadas posibles para cada día, vehículo por vehículo. Tarda unos segundos.</span></div>
  <div class="paso tono-ambar"><div class="cab"><div class="ico"><span class="mi">insights</span></div><div class="num">04</div></div>
  <b>Analiza y descarga</b><span>Revisa <b>Resultados</b>, <b>Por hora</b> y <b>Riesgo</b>. Los gráficos muestran el detalle al pasar el cursor.</span></div>
</div>""")

    with panel("Qué hace el simulador, en palabras simples", "El método de Montecarlo aplicado al parqueadero.", "lightbulb", "teal"):
        html_md("""
<div class="flujo">
  <div class="f">Lee octubre de 2026<span>24.830 vehículos reales</span></div>
  <div class="f">Aprende los patrones<span>llegadas por hora, tipo de vehículo, permanencia</span></div>
  <div class="f">Ajusta cada día<span>festivo, quincena, temporada, eventos</span></div>
  <div class="f">Simula cada vehículo<span>llega, entra o espera, se queda, sale</span></div>
  <div class="f">Repite cientos de veces<span>y resume: promedios, rangos, probabilidades</span></div>
</div>""")
        st.markdown(
            "Nadie sabe exactamente cuántos carros llegarán el próximo sábado. Lo que sí se sabe, por los datos de octubre, es **cómo suelen "
            "comportarse**: a qué hora llegan, cuánto tiempo se quedan y cómo cambia eso entre un lunes y un sábado. El simulador usa esos "
            "patrones para **inventar jornadas posibles** con números aleatorios, como si lanzara dados. En cada jornada sigue a cada vehículo: "
            "si hay celda libre **entra**; si el parqueadero está lleno **espera** unos minutos y, si nadie sale, **se va** (ingreso perdido). "
            "Cuando termina su permanencia **sale** y libera la celda.\n\n"
            "Una sola jornada podría salir con mucha o poca suerte. Por eso se repite **cientos de veces** (las *réplicas*) y se mira el conjunto: "
            "cuántos vehículos se esperan en promedio, qué tan alto puede llegar en un día malo y con qué probabilidad se llena.")

    with panel("Cómo leer los indicadores", "Cada indicador lleva una insignia de estado con icono y texto: "
               + vista.badge("Holgado", "bien") + " " + vista.badge("Vigilar", "atencion") + " " + vista.badge("Crítico", "critico"),
               "menu_book", "violeta"):
        html_md("""
<div class="glosario">
  <div><b>Réplica</b>Una jornada simulada completa. 300 réplicas = 300 versiones posibles de cada día.</div>
  <div><b>Media</b>El promedio de todas las réplicas. Es el valor «esperado».</div>
  <div><b>P5 y P95</b>Rango donde caen 90 % de las réplicas. P5 es un día flojo; P95 un día muy fuerte.</div>
  <div><b>Probabilidad de lleno</b>En qué porcentaje de las réplicas la zona de carros llegó al 100 % en algún momento.</div>
  <div><b>Ocupación pico</b>El máximo de carros dentro a la vez, como % de las celdas.</div>
  <div><b>Sin cupo</b>Conductores que llegaron, esperaron y se fueron porque no se liberó una celda.</div>
  <div><b>Meta</b>Ingreso de referencia (por defecto, lo que ingresó un día igual de octubre × la temporada).</div>
  <div><b>VaR 95 %</b>El faltante frente a la meta que no se supera en el 95 % de los escenarios.</div>
  <div><b>IC 95 %</b>Intervalo donde está el ingreso medio real con 95 % de confianza.</div>
  <div><b>Factor de temporada</b>Cuánto más (o menos) demanda tiene un día frente a octubre (octubre = 1,00).</div>
  <div><b>Quincena</b>Días de pago (1, 15, 16 y los dos últimos del mes): llegan más carros.</div>
  <div><b>Hora pico / valle</b>Horas con más (≥ 80 % del máximo) o menos (≤ 35 %) llegadas.</div>
</div>""")
        with st.expander("Qué encuentras en cada pestaña y en el Excel", icon=":material/menu_book:"):
            st.markdown("""
| Pestaña | Para qué sirve |
|---|---|
| **Calendario** | Ver festivos, quincenas y temporada de cada día, elegir los días y lanzar la simulación. |
| **Resultados** | Indicadores clave, recomendaciones, vehículos esperados por día, días pico y valle. |
| **Por hora** | Mapas de calor por hora, entradas contra salidas y un día simulado vehículo por vehículo. |
| **Riesgo e ingresos** | Ingreso esperado, probabilidad de no llegar a la meta, pérdidas por falta de cupo y si conviene un parqueadero externo. |
| **Modelo y datos** | Los datos reales de octubre, la validación del modelo, las ecuaciones y el generador de números aleatorios. |

El libro de Excel trae una hoja **Resumen** tipo tablero (indicadores, recomendaciones y gráficas), y hojas **Por día**, **Por hora**,
**Calor semana**, **Calor fechas**, **Riesgo**, **Externo**, **Calendario**, **Réplicas**, **Vehículos** (cada carro simulado con su hora de
entrada y salida) y **Parámetros y guía**. Todas las gráficas son de Excel, así que puedes editarlas.
""")

# ===========================================================================
# 1. CALENDARIO  (tono azul)
# ===========================================================================
with tabs[1]:
    seleccion = sorted(ss.sel)
    html_md(vista.banner("Calendario de simulación",
                         "Elige los días a simular. Cada día muestra si es festivo, quincena y su temporada frente a octubre.",
                         "calendar_month", "azul",
                         [f"<b>{len(seleccion)}</b> días seleccionados", f"{cal.MESES[int(ss.mes) - 1]} {int(ss.anio)}"]))
    izq, der = st.columns([2.15, 1], gap="medium")
    with izq:
        with panel("Calendario del mes", "Pasa el cursor sobre un día para ver su detalle.", "date_range", "azul"):
            barra_nav, barra_color = st.columns([1.25, 1], vertical_alignment="center")
            with barra_nav:
                # key «nav-cal»: el CSS mantiene esta fila horizontal también en celular
                with st.container(key="nav-cal"):
                    nav = st.columns([0.5, 1.5, 1.05, 0.5], vertical_alignment="center", gap="small")
                    nav[0].button("Anterior", icon=":material/chevron_left:", on_click=mover_mes, args=(-1,), width="stretch", help="Mes anterior")
                    nav[1].selectbox("Mes", range(1, 13), format_func=lambda m: cal.MESES[m - 1], key="mes", label_visibility="collapsed")
                    nav[2].number_input("Año", 2024, 2035, key="anio", step=1, label_visibility="collapsed")
                    nav[3].button("Siguiente", icon=":material/chevron_right:", on_click=mover_mes, args=(1,), width="stretch", help="Mes siguiente")
            anio, mes = int(ss.anio), int(ss.mes)

            valores, fmt, rojo = None, "{:.0f}", False
            if "S" in ss:
                opciones = {"Sin color": None, "Vehículos": ("Llegadas (media)", "{:.0f}", False),
                            "Prob. lleno": ("Prob. carros llenos", "{:.0%}", True),
                            "Ocupación pico": ("% ocupación pico", "{:.0%}", True),
                            "Ingreso (M)": ("Ingreso (media)", "{:.1f} M", False),
                            "Prob. bajo meta": ("Prob. ingreso < meta", "{:.0%}", True)}
                with barra_color:
                    elegido = st.selectbox("Colorear con el resultado", list(opciones), index=0, label_visibility="collapsed",
                                           help="Colorea cada día del calendario con un resultado de la última simulación.")
                if opciones[elegido]:
                    col, fmt, rojo = opciones[elegido]
                    d = ss.S["dias"]
                    escala = 1e6 if col == "Ingreso (media)" else 1
                    valores = {f: v / escala for f, v in zip(d["Fecha"], d[col]) if f.month == mes and f.year == anio}
            html_md(vista.calendario_html(anio, mes, ss.sel, factores_mes, f_ev, f_puente, valores, fmt, rojo))

    with der:
        with panel("Configura y ejecuta", "Tres pasos para lanzar la simulación.", "rocket_launch", "indigo"):
            html_md(vista.paso_ctrl(1, "Elige los días", "Selección rápida o día por día"))
            st.pills("Selección rápida", list(RAPIDAS), selection_mode="single", key="rapida", on_change=aplicar_rapida,
                     label_visibility="collapsed")
            dias = dias_mes(anio, mes)
            clave_mes = f"dias_{anio}_{mes}"
            ss[clave_mes] = [f for f in dias if f in ss.sel]
            st.pills(f"Días de {cal.MESES[mes - 1].lower()}", dias, selection_mode="multi", key=clave_mes,
                     format_func=lambda f: f"{DIA2[f.weekday()]} {f.day}" + (" ★" if cal.festivo(f) else ""),
                     on_change=cambiar_dias, args=(anio, mes), help="★ = festivo. Toca un día para agregarlo o quitarlo.")
            with st.expander("Agregar un rango de fechas", icon=":material/date_range:"):
                st.date_input("Rango (puede abarcar varios meses)", value=(), key="rango", format="DD/MM/YYYY")
                st.button("Agregar rango", on_click=agregar_rango, width="stretch")

            seleccion = sorted(ss.sel)
            if seleccion:
                tipos = pd.Series([cal.TIPO_NOMBRE[cal.tipo_dia(f)] for f in seleccion]).value_counts()
                meses_sel = sorted({(f.year, f.month) for f in seleccion})
                chips_sel = "".join(f'<span class="chip"><b>{n}</b> {t}</span>' for t, n in tipos.items())
                html_md(f'<div class="resumen-sel tono-azul"><div class="grande">{len(seleccion)}<small>días seleccionados</small></div>'
                        f'<div class="nota">{seleccion[0]:%d/%m/%Y} – {seleccion[-1]:%d/%m/%Y} · '
                        + ", ".join(f"{cal.MESES[m - 1]} {a}" for a, m in meses_sel) + f'</div><div class="chips">{chips_sel}</div></div>')
            else:
                html_md('<div class="resumen-sel tono-azul"><div class="grande">0<small>días seleccionados</small></div>'
                        '<div class="nota">Usa la selección rápida o toca los días del mes.</div></div>')

            html_md(vista.paso_ctrl(2, "Franja horaria", "Para medir el riesgo de ingresos"))
            franja = st.slider("Franja horaria para el riesgo de ingresos", 7, 22, (7, 22), 1, format="%d:00", label_visibility="collapsed",
                               help="El riesgo de ingresos se calcula con los vehículos que llegan dentro de esta franja.")

            html_md(vista.paso_ctrl(3, "Ejecuta", f"{len(seleccion)} días × {int(replicas)} réplicas = {NUM(len(seleccion) * int(replicas))} jornadas"
                                    if seleccion else "Elige al menos un día"))
            # El botón solo registra el pedido; la simulación corre arriba de las pestañas (ver «Simulación pedida»)
            st.button("Simular", type="primary", icon=":material/play_arrow:", disabled=not seleccion, width="stretch",
                      on_click=pedir_simulacion, args=(tuple(seleccion), tuple(franja)))
            if "res" in ss:
                r = ss.res
                html_md(f'<div class="listo">✓ Listo: {len(r.dias)} días × {r.cfg.replicas} réplicas = '
                        f'{NUM(len(r.dias) * r.cfg.replicas)} jornadas en {r.segundos:.1f} s. Mira las pestañas <b>Resultados</b>, '
                        f'<b>Por hora</b> y <b>Riesgo e ingresos</b>.</div>')
                boton_excel("dl_cal", "primary")

    with panel(f"{cal.MESES[mes - 1]} {anio} en detalle", "Festivos, temporada de cada día y de dónde salen los factores.", "info", "pizarra"):
        fest = [(f, d) for f, d in cal.festivos(anio).items() if f.month == mes]
        with st.expander(f"Festivos de {cal.MESES[mes - 1].lower()} y por qué ({len(fest)})", icon=":material/celebration:"):
            if fest:
                st.dataframe(pd.DataFrame([{
                    "Fecha": f.strftime("%d/%m/%Y"), "Día": cal.DIA_SEMANA[f.weekday()], "Festivo": d["nombre"], "Por qué es festivo": d["motivo"],
                    "Regla": (f"Ley Emiliani: se celebra el {d['fecha_original']:%d/%m} y se traslada al lunes" if d["trasladado"] and d["fecha_original"] != f
                              else ("Depende de la fecha de Pascua" if any(n == d["nombre"] for _, n, _ in cal.FESTIVOS_PASCUA) else "Fecha fija")),
                } for f, d in fest]), hide_index=True, width="stretch")
            else:
                st.caption("Este mes no tiene festivos.")
            if st.toggle(f"Ver todos los festivos de {anio}"):
                st.dataframe(pd.DataFrame([{"Fecha": f.strftime("%d/%m/%Y"), "Día": cal.DIA_SEMANA[f.weekday()], "Festivo": d["nombre"],
                                            "Por qué": d["motivo"]} for f, d in cal.festivos(anio).items()]), hide_index=True, width="stretch")

        fm, etiqueta, motivo = cal.FACTOR_MES[mes]
        with st.expander(f"Temporada de cada día · factor del mes {factores_mes[mes]:.2f} ({etiqueta.lower()})", icon=":material/sunny:"):
            st.caption(motivo)
            infos = [cal.clasificar(f, factores_mes, f_ev, f_puente) for f in dias_mes(anio, mes)]
            st.dataframe(pd.DataFrame([{
                "Fecha": i.fecha.strftime("%d/%m"), "Día": cal.DIA_SEMANA[i.fecha.weekday()], "Tipo de día": cal.TIPO_NOMBRE[i.tipo],
                "Festivo": i.festivo["nombre"] if i.festivo else "", "Quincena": "Sí" if i.quincena else "", "Puente": i.puente or "",
                "Eventos": ", ".join(e.nombre for e in i.eventos), "Factor": round(i.factor_temporada, 3), "Temporada": i.temporada,
                "Por qué": i.motivo_temporada} for i in infos]), hide_index=True, width="stretch", height=360)

        with st.expander("¿De dónde salen los factores de temporada?", icon=":material/help:"):
            st.markdown(
                "Los datos solo cubren **octubre de 2026**, así que el programa no puede *ver* diciembre o enero. Por eso usa factores "
                "relativos a octubre (octubre = 1,00) sustentados en reportes del sector y los aplica a la tasa de llegadas:\n\n"
                + "\n".join(f"- {t}" for t in cal.EVENTOS_FUENTES.values())
                + "\n\nTodos los factores se pueden cambiar en la barra lateral (*Temporada alta / baja*).")
            st.dataframe(pd.DataFrame([{"Mes": cal.MESES[m - 1], "Factor": cal.FACTOR_MES[m][0], "Temporada": cal.FACTOR_MES[m][1],
                                        "Motivo": cal.FACTOR_MES[m][2]} for m in range(1, 13)]), hide_index=True, width="stretch")

# ===========================================================================
# 2. RESULTADOS  (tono verde azulado)
# ===========================================================================
with tabs[2]:
    if "S" not in ss:
        html_md(vista.banner("Resultados", "Indicadores clave, recomendaciones y vehículos esperados por día.", "insights", "teal"))
        sin_resultados("teal")
    else:
        S, res = ss.S, ss.res
        k, r, e, d = S["kpi"], S["riesgo"], S["externo"], S["dias"]
        html_md(vista.banner(f"Resultados de {k['dias']} días simulados",
                             f"{NUM(k['jornadas'])} jornadas simuladas. Así se espera que se comporte el parqueadero.", "insights", "teal",
                             pills_periodo(res)))
        pct_sin = k["sin_cupo_total"] / max(1, k["llegadas_total"])
        with panel("Indicadores clave", "Promedio de todas las réplicas. La insignia indica si el valor es holgado, para vigilar o crítico.",
                   "monitoring", "teal", accion=lambda: boton_excel("dl_res")):
            html_md(vista.tarjetas([
                kpi("Vehículos esperados", NUM(k["llegadas_total"]), f"≈ {NUM(k['llegadas_dia'])} por día", None, "directions_car", "azul", True),
                kpi("Ingreso esperado", COP(r["ingreso_media"]), f"franja {r['franja']}", estado_nivel(r["nivel_meta"]), "payments", "teal", True),
                kpi("Prob. de lleno (carros)", PCT(k["prob_carros_llenos"]), "de las jornadas llega al 100 %",
                    estado_prob_lleno(k["prob_carros_llenos"]), "local_parking", "ambar"),
                kpi("Ocupación pico máxima", PCT(k["ocupacion_pico"]), f"día: {k['dia_ocupacion_pico']}", estado_ocupacion(k["ocupacion_pico"]),
                    "speed", "violeta"),
                kpi("Se van sin cupo", NUM(k["sin_cupo_total"]), f"{PCT(pct_sin)} de las llegadas", estado_sin_cupo(pct_sin), "block", "coral"),
                kpi("Espera promedio", W.n_es(k["espera_prom"], 1) + " min", "de quienes tuvieron que esperar", estado_espera(k["espera_prom"]),
                    "hourglass_top", "indigo"),
                kpi("Permanencia promedio", f"{k['permanencia_prom']:.0f} min", f"utilización de celdas {PCT(k['utilizacion'])}", None,
                    "schedule", "pizarra"),
                kpi("Parqueadero externo", e["decision"].capitalize(), f"{len(e['dias_rentables'])} días rentables", estado_externo(e["decision"]),
                    "add_business", "teal"),
            ]))

        with panel("Qué debe preparar el parqueadero", "Recomendaciones automáticas a partir de los resultados.", "task_alt", "ambar"):
            html_md(vista.recomendaciones(recomendaciones(S)))

        with panel("Vehículos por día", "Pasa el cursor sobre una barra para ver el detalle del día.", "bar_chart", "azul"):
            grafico(W.barras_dias(d))

        cfg_tabla = {"Llegadas (media)": st.column_config.NumberColumn("Vehículos", format="%d"),
                     "Prob. carros llenos": st.column_config.ProgressColumn("Prob. lleno", format="percent", min_value=0, max_value=1),
                     "Hora pico llegadas": st.column_config.TextColumn("Hora pico")}
        cols_pv = ["Día", "Festivo", "Temporada", "Llegadas (media)", "Prob. carros llenos", "Hora pico llegadas"]
        h = S["horas"]
        cp, cv = st.columns(2, gap="medium")
        with cp:
            with panel("Días pico", f"El 25 % con más vehículos · horas pico: {', '.join(h[h['Nivel'] == 'Pico']['Hora'])}", "trending_up", "coral"):
                st.dataframe(d[d["Nivel"] == "Pico"][cols_pv].sort_values("Llegadas (media)", ascending=False),
                             hide_index=True, width="stretch", column_config=cfg_tabla)
        with cv:
            with panel("Días valle", f"El 25 % con menos vehículos · horas valle: {', '.join(h[h['Nivel'] == 'Valle']['Hora'])}",
                       "trending_down", "violeta"):
                st.dataframe(d[d["Nivel"] == "Valle"][cols_pv].sort_values("Llegadas (media)"),
                             hide_index=True, width="stretch", column_config=cfg_tabla)

        with panel("Detalle por día", "Todas las métricas de cada día. Haz clic en un encabezado para ordenar.", "table_chart", "pizarra"):
            st.dataframe(d.drop(columns=["Fecha"]), hide_index=True, width="stretch", height=380, column_config={
                **{c: st.column_config.ProgressColumn(c, format="percent", min_value=0, max_value=1)
                   for c in ["Prob. carros llenos", "% ocupación pico", "Prob. ingreso < meta"]},
                **{c: st.column_config.NumberColumn(c, format="dollar") for c in d.columns if c.startswith(("Ingreso", "Meta", "Pérdida"))},
                **{c: st.column_config.NumberColumn(c, format="%.1f") for c in ["Llegadas (media)", "Llegadas P5", "Llegadas P95", "Entradas (media)",
                                                                              "Sin cupo (media)", "Pico carros (media)", "Espera prom. (min)"]},
            })

# ===========================================================================
# 3. POR HORA  (tono violeta)
# ===========================================================================
with tabs[3]:
    if "S" not in ss:
        html_md(vista.banner("Comportamiento por hora", "Mapas de calor, entradas contra salidas y un día vehículo por vehículo.",
                             "schedule", "violeta"))
        sin_resultados("violeta")
    else:
        S, res = ss.S, ss.res
        html_md(vista.banner("Comportamiento por hora",
                             "Las llegadas van de 07:00 a 21:59; salidas y ocupación se miden hasta las 23:59 porque los últimos vehículos "
                             "salen después del cierre de entradas.", "schedule", "violeta", pills_periodo(res)))
        with panel("Mapa de calor", "Más oscuro = más alto. Pasa el cursor sobre una celda para ver el valor.", "grid_on", "violeta"):
            c1, c2 = st.columns([1.3, 1], vertical_alignment="bottom")
            indicador = c1.selectbox("Indicador", list(S["mapas_fecha"]))
            opciones_vista = ["Día de la semana × hora", "Cada fecha × hora"]
            tipo = c2.segmented_control("Vista", opciones_vista, default=opciones_vista[0], key="vista_mapa") or opciones_vista[0]
            porcentaje = "%" in indicador
            m = S["mapas_dsem"][indicador] if tipo == opciones_vista[0] else S["mapas_fecha"][indicador]
            grafico(W.mapa_calor(m, indicador, "%" if porcentaje else "vehículos", porcentaje))
            with st.expander("Ver la tabla del mapa", icon=":material/table:"):
                st.dataframe(m.round(1), width="stretch")

        with panel("Entradas contra salidas", "La ocupación no se supone: resulta de contar entradas menos salidas minuto a minuto.",
                   "swap_vert", "azul"):
            a, b = st.columns(2, gap="medium")
            with a:
                grafico(W.perfil_flujo(S["perfil"]))
            with b:
                grafico(W.perfil_ocupacion(S["perfil"], res.capacidad["A_rot"]))
            with st.expander("Entradas y salidas por tipo de día", icon=":material/table:"):
                for nombre, tabla in S["perfil_tipo"].items():
                    st.markdown(f"**{nombre}**")
                    st.dataframe(tabla.T.round(1), width="stretch")

        with panel("Patrón semanal", "Promedio por día de la semana y hora de los días simulados.", "view_week", "indigo"):
            a, b = st.columns(2, gap="medium")
            with a:
                grafico(W.mapa_calor(S["mapas_dsem"]["Entradas por hora"], "Entradas por hora", etiquetas=False))
            with b:
                grafico(W.mapa_calor(S["mapas_dsem"]["Salidas por hora"], "Salidas por hora", etiquetas=False))

        with panel("Un día simulado, vehículo por vehículo",
                   "Réplica 1 del día elegido. Haz clic en un estado de la leyenda para resaltarlo; usa la rueda del ratón para acercar.",
                   "directions_car", "teal"):
            etiquetas = {i.etiqueta: i.fecha for i in res.dias}
            dia_elegido = st.selectbox("Día", list(etiquetas), index=int(np.argmax(S["dias"]["Llegadas (media)"].values)))
            reg = res.registro[res.registro["fecha"] == etiquetas[dia_elegido]] if len(res.registro) else res.registro
            if len(reg):
                cuenta = reg["estado"].value_counts()
                estilos = {"Entró": ("login", "azul", ("Directo", "info")), "Entró tras esperar": ("hourglass_top", "ambar", ("Esperó", "atencion")),
                           "Al parqueadero externo": ("add_business", "violeta", ("Externo", "neutro")),
                           "Se fue sin cupo": ("block", "coral", ("Perdido", "critico"))}
                html_md(vista.tarjetas([kpi(est, NUM(cuenta.get(est, 0)), PCT(cuenta.get(est, 0) / len(reg)) + " de los vehículos", st_, ic, tono)
                                        for est, (ic, tono, st_) in estilos.items()]))
                grafico(W.gantt_dia(reg))
                grafico(W.ocupacion_dia(reg, res.capacidad["A_rot"]))
                with st.expander("Tabla de vehículos de este día", icon=":material/table:"):
                    st.dataframe(reg.assign(llegada=reg["llegada_h"].map(W.hhmm), entrada=reg["entrada_h"].map(W.hhmm), salida=reg["salida_h"].map(W.hhmm))
                                 [["vehiculo_id", "llegada", "entrada", "salida", "tipo_vehiculo", "tipo_cliente", "zona", "permanencia_min", "espera_min",
                                   "estado", "valor_cop"]].rename(columns={"vehiculo_id": "N°", "tipo_vehiculo": "Vehículo", "tipo_cliente": "Cliente",
                                                                            "zona": "Zona", "permanencia_min": "Permanencia (min)", "espera_min": "Espera (min)",
                                                                            "estado": "Estado", "valor_cop": "Valor", "llegada": "Llegada",
                                                                            "entrada": "Entrada", "salida": "Salida"}).round(1),
                                 hide_index=True, width="stretch", height=360, column_config={"Valor": st.column_config.NumberColumn(format="dollar")})

# ===========================================================================
# 4. RIESGO E INGRESOS  (tono ámbar)
# ===========================================================================
with tabs[4]:
    if "S" not in ss:
        html_md(vista.banner("Riesgo e ingresos", "Ingreso esperado, probabilidad de no llegar a la meta y pérdidas por falta de cupo.",
                             "payments", "ambar"))
        sin_resultados("ambar")
    else:
        S, res = ss.S, ss.res
        r, e = S["riesgo"], S["externo"]
        html_md(vista.banner("Riesgo de ingresos",
                             f"Lapso evaluado: {r['dias']} días seleccionados, vehículos que llegan entre <b>{r['franja']}</b>.",
                             "payments", "ambar",
                             [vista.badge(f"Frente a la meta: riesgo {r['nivel_meta'].lower()}", estado_nivel(r["nivel_meta"])[1]),
                              vista.badge(f"Por falta de cupo: riesgo {r['nivel_cupo'].lower()}", estado_nivel(r["nivel_cupo"])[1])]))
        with panel("Indicadores de riesgo", "Cuánto se espera ingresar, qué tan lejos puede quedar de la meta y cuánto se pierde por cupo.",
                   "shield", "ambar", accion=lambda: boton_excel("dl_riesgo")):
            html_md(vista.tarjetas([
                kpi("Ingreso esperado", COP(r["ingreso_media"]), f"IC 95 %: {COP(r['ic95'][0])} – {COP(r['ic95'][1])}", None, "payments", "teal", True),
                kpi("Meta del lapso", COP(r["meta"]), "referencia para medir el riesgo", None, "flag", "azul", True),
                kpi("Prob. de quedar bajo la meta", PCT(r["prob_bajo_meta"]), f"faltante esperado {COP(r['faltante_esperado'])}",
                    estado_nivel(r["nivel_meta"]), "percent", "ambar"),
                kpi("VaR 95 % del faltante", COP(r["var95_faltante"]), "faltante máximo en el 95 % de los casos", None, "warning", "coral"),
                kpi("Escenario malo (P5)", COP(r["ingreso_p5"]), "solo 5 % de las réplicas ingresa menos", None, "south", "coral"),
                kpi("Escenario bueno (P95)", COP(r["ingreso_p95"]), "solo 5 % de las réplicas ingresa más", None, "north", "teal"),
                kpi("Pérdida por falta de cupo", COP(r["perdida_cupo_media"]), f"P95: {COP(r['perdida_cupo_p95'])}", estado_nivel(r["nivel_cupo"]),
                    "money_off", "violeta"),
                kpi("Prob. de perder por cupo", PCT(r["prob_perdida_cupo"]), "réplicas con al menos un vehículo sin cupo", None, "block", "pizarra"),
            ]))

        with panel("Distribución de los resultados", "Cada barra agrupa réplicas con un resultado parecido. Pasa el cursor para ver cuántas.",
                   "bar_chart", "azul"):
            a, b = st.columns(2, gap="medium")
            with a:
                grafico(W.histograma(r["ingreso_por_replica"], "Ingreso del lapso", r["meta"], "Meta"))
            with b:
                grafico(W.histograma(r["perdida_por_replica"], "Ingreso perdido por falta de cupo"))

        with panel("¿Son suficientes las réplicas?", "Si la curva ya quedó dentro de la franja sombreada, el resultado es estable.",
                   "timeline", "violeta"):
            grafico(W.convergencia(r["convergencia"]))
            c1, c2 = st.columns(2, gap="medium")
            with c1:
                with st.expander("Ecuaciones del riesgo", icon=":material/function:"):
                    st.latex(r"I_r=\sum_{d}\sum_{v\,\in\,\text{franja}}\mathbb{1}[\text{entra}_v]\cdot "
                             r"\min\!\Big(\big\lceil \tfrac{T_v}{60}\big\rceil t,\;\text{tope}\Big)(1-\delta)+R\cdot\mathbb{1}[\text{extravío}_v]")
                    st.latex(r"\text{Pérdida}_r=\sum_v \mathbb{1}[\text{sin cupo}_v]\cdot\text{valor}_v \qquad "
                             r"\text{Faltante}_r=\max(0,\;\text{Meta}-I_r)")
                    st.latex(r"\hat P(I<\text{Meta})=\frac{1}{R}\sum_{r=1}^{R}\mathbb{1}[I_r<\text{Meta}]\qquad "
                             r"\text{IC}_{95\%}=\bar I\pm1{,}96\,\frac{s}{\sqrt R}")
            with c2:
                with st.expander("Riesgo por día", icon=":material/table:"):
                    cols = ["Día", "Ingreso en la franja (media)", "Meta de la franja", "Prob. franja < meta", "Pérdida por cupo en la franja"]
                    st.dataframe(S["dias"][cols], hide_index=True, width="stretch", column_config={
                        "Prob. franja < meta": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
                        **{c: st.column_config.NumberColumn(format="dollar") for c in cols[1:3] + cols[4:]}})

        with panel("¿Conviene abrir un parqueadero externo?",
                   "Beneficio de un día = ingreso de los conductores sin cupo que aceptan ir al externo − costo por vehículo − costo fijo. "
                   "Es viable si gana en al menos 75 % de las réplicas.", "add_business", "teal"):
            html_md(vista.tarjetas([
                kpi("Decisión", e["decision"].capitalize(), ", ".join(e["dias_rentables"]) or "ningún día rentable", estado_externo(e["decision"]),
                    "gavel", "teal", True),
                kpi("Beneficio abriendo todos los días", COP(e["beneficio_todo"]), "promedio de las réplicas", None, "calendar_month", "azul"),
                kpi("Beneficio solo en días rentables", COP(e["beneficio_sel"]), "promedio de las réplicas", None, "event_available", "violeta"),
                kpi("Prob. de ganar en esos días", PCT(e["prob_ganar_sel"]), "réplicas con beneficio positivo", None, "percent", "ambar"),
            ]))
            ext = pd.DataFrame({"Día": [i.etiqueta for i in res.dias], "Vehículos captados (media)": res.RD["ext_captados"].mean(0),
                                "Ingreso externo (media)": res.RD["ext_ingreso"].mean(0),
                                "Beneficio del día (media)": (res.RD["ext_ingreso"] - res.cfg.externo["costo_var"] * res.RD["ext_captados"]
                                                              - res.cfg.externo["costo_fijo"]).mean(0)})
            with st.expander("Beneficio del externo por día", icon=":material/table:"):
                st.dataframe(ext, hide_index=True, width="stretch", column_config={
                    "Vehículos captados (media)": st.column_config.NumberColumn(format="%.1f"),
                    "Ingreso externo (media)": st.column_config.NumberColumn(format="dollar"),
                    "Beneficio del día (media)": st.column_config.NumberColumn(format="dollar")})

# ===========================================================================
# 5. MODELO Y DATOS  (tono pizarra)
# ===========================================================================
with tabs[5]:
    html_md(vista.banner("Modelo y datos", "De dónde salen los parámetros, cómo se valida el modelo y cómo funciona el generador aleatorio.",
                         "science", "pizarra", [f"<b>{NUM(H['n'])}</b> vehículos", PERIODO(H["periodo"])]))
    VISTAS = ["Datos de octubre", "Por qué Montecarlo", "Generador aleatorio", "Parámetros estimados"]
    vista_m = st.segmented_control("Ver", VISTAS, default=VISTAS[0], key="vista_modelo", label_visibility="collapsed") or VISTAS[0]

    if vista_m == "Datos de octubre":
        with panel("Datos reales de octubre", "De aquí salen todos los parámetros del modelo.", "database", "pizarra"):
            grafico(W.historico_diario(H["diario"]))
            a, b = st.columns(2, gap="medium")
            with a:
                grafico(W.mapa_calor(H["entradas_dsem_hora"], "Entradas promedio por hora", etiquetas=False))
            with b:
                grafico(W.mapa_calor(H["ocupacion_dsem_hora"], "Carros dentro (máximo de la hora)", "carros", etiquetas=False))
            with st.expander("Entradas por fecha y hora", icon=":material/grid_on:"):
                grafico(W.mapa_calor(H["entradas_fecha_hora"], "Octubre real: entradas por fecha y hora"))

        with panel("Tabla de frecuencias con la regla de Sturges", "Hora de entrada de los vehículos de octubre.", "functions", "indigo"):
            si = H["sturges_info"]
            st.latex(rf"k=1+3{{,}}322\,\log_{{10}}({si['n']})={si['k_real']:.2f}\approx{si['k']}\qquad "
                     rf"\text{{amplitud}}=\frac{{{si['maximo']:.2f}-{si['minimo']:.2f}}}{{{si['k']}}}={si['amplitud']:.3f}\text{{ h}}")
            a, b = st.columns([1.1, 1], gap="medium")
            a.dataframe(H["sturges"].round(4), hide_index=True, width="stretch", height=340)
            with b:
                grafico(W.barras_sturges(H["sturges"]))
            html_md(vista.subtitulo("Resumen por tipo de día"))
            st.dataframe(H["por_tipo"].round(1), width="stretch")

        with panel("Validación: ¿el modelo reproduce octubre?", "Simula los 31 días reales de octubre y compara lo simulado con lo que pasó.",
                   "verified", "teal"):
            if st.button("Validar el modelo con octubre", icon=":material/verified:"):
                ss.validacion = validar_cache(RUTA, 200)
            if "validacion" in ss:
                v = ss.validacion
                html_md(vista.tarjetas([
                    kpi("Error medio por día (MAPE)", PCT(v["mape"]), "vehículos simulados vs reales",
                        ("Bueno", "bien") if v["mape"] < 0.10 else ("Revisar", "atencion"), "target", "teal"),
                    kpi("Días dentro de P5–P95", PCT(v["cobertura"]), "días reales que cayeron en el rango simulado",
                        ("Bueno", "bien") if v["cobertura"] >= 0.80 else ("Revisar", "atencion"), "fact_check", "azul"),
                    kpi("Error del pico de carros", PCT(v["mape_pico"]), "máximo de carros dentro", None, "local_parking", "ambar"),
                    kpi("Total real / simulado", f"{NUM(v['total_real'])} / {NUM(v['total_sim'])}", "vehículos en el mes", None,
                        "compare_arrows", "violeta"),
                ]))
                grafico(W.validacion(v["tabla"]))
                with st.expander("Tabla de validación", icon=":material/table:"):
                    st.dataframe(v["tabla"].round(3), hide_index=True, width="stretch")

    elif vista_m == "Por qué Montecarlo":
        with panel("¿Por qué Montecarlo?", "La herramienta adecuada cuando la demanda es incierta y la capacidad es un límite.", "casino", "indigo"):
            st.markdown("""
El método de Montecarlo repite muchas veces un experimento con números aleatorios para obtener **la distribución completa**
de los resultados, no un único número. Para este parqueadero es la herramienta adecuada porque:

1. **La demanda es incierta.** El mismo sábado puede traer 1.000 o 1.250 vehículos; una fórmula con promedios oculta esa variación.
2. **La tasa de llegadas cambia cada hora y cada tipo de día** (lunes–jueves, viernes, sábado, domingo/festivo, quincena, temporada).
   Las fórmulas de colas clásicas (M/M/c) suponen una tasa constante.
3. **Las permanencias no son exponenciales.** Se usan los percentiles reales de octubre (por tipo de cliente, vehículo, franja y tipo de día).
4. **La capacidad es un límite que no es lineal.** Con 360 celdas, 10 % más de demanda puede no causar nada o puede llenar el parqueadero
   toda la tarde; solo simulando se ve en qué días y horas ocurre.
5. **Se mide el riesgo, no solo el promedio:** probabilidad de lleno, probabilidad de no alcanzar la meta, VaR 95 %, intervalos de confianza.
6. **Permite preguntas "¿qué pasa si…?"**: diciembre, +30 % de demanda, menos celdas, otra tarifa, abrir un parqueadero externo.
""")
        with panel("¿Por qué simular entradas y salidas de cada vehículo?",
                   "El parqueadero se llena por los carros que todavía no han salido, no solo por los que llegan.", "route", "teal"):
            st.markdown("""
| Paso | Qué se genera | Cómo (transformada inversa con U ~ Uniforme(0,1)) |
|---|---|---|
| 1 | Factor del día Z | Box–Muller: Z = 1 + σ·√(−2 ln U₁)·cos(2πU₂) |
| 2 | Llegadas de cada hora N | Poisson(λ_hora · temporada · quincena · Z), por la acumulada |
| 3 | Minuto de llegada | h + U |
| 4 | Tipo de vehículo y cliente | Tabla acumulada de la mezcla de esa hora |
| 5 | Permanencia T | Percentiles empíricos de octubre, interpolados |
| 6 | **Entrada** | Si hay celda libre entra; si no, espera hasta la tolerancia; si nadie sale, se va (ingreso perdido) |
| 7 | **Salida** | Entrada + T; libera la celda para el siguiente |
| 8 | Cobro | Hora o fracción, tope 24 h, gracia, descuento, recargo por extravío |

Así la ocupación, la espera y los rechazos **salen del modelo** (no son supuestos) y se pueden ver hora por hora.
""")
            st.latex(r"\lambda_{d,h}= \lambda^{\text{oct}}_{\text{tipo}(d),h}\cdot F_{\text{mes}}\cdot F_{\text{evento}}\cdot F_{\text{puente}}\cdot "
                     r"F_{\text{quincena}}\cdot(1+g)\cdot Z_d \qquad N_{d,h}\sim\text{Poisson}(\lambda_{d,h})")
            st.latex(r"\text{Ocupación}(t)=\#\{v:\ \text{entrada}_v\le t<\text{salida}_v\}\qquad \text{lleno}\iff \text{Ocupación}(t)\ge C")

    elif vista_m == "Generador aleatorio":
        g = crear_generador("congruencial" if gen_nombre.startswith("Congr") else "numpy", int(semilla))
        with panel("Generador de números aleatorios", "Todas las variables del modelo salen de estos números por transformada inversa.",
                   "casino", "indigo"):
            st.latex(r"X_{i+1}=a\,X_i \bmod m,\quad a=48\,271,\; m=2^{31}-1,\qquad U_i=X_i/m")
            n_prueba = st.select_slider("Cantidad de números para las pruebas", [1000, 5000, 10000, 50000, 100000], 10000)
            u = g.random(n_prueba)
            pu, ps = prueba_uniformidad(u), prueba_series(u)
            html_md(vista.tarjetas([
                kpi("Prueba χ² de uniformidad", f"χ² = {W.n_es(pu['chi2'], 2)}", f"crítico {W.n_es(pu['critico'], 2)} · gl = {pu['gl']} · α = 0,05",
                    ("Se acepta H₀", "bien") if pu["acepta"] else ("Se rechaza H₀", "critico"), "equalizer", "teal"),
                kpi("Prueba de series (independencia)", f"χ² = {W.n_es(ps['chi2'], 2)}", f"crítico {W.n_es(ps['critico'], 2)} · gl = {ps['gl']}",
                    ("Se acepta H₀", "bien") if ps["acepta"] else ("Se rechaza H₀", "critico"), "scatter_plot", "violeta"),
                kpi("Números generados", NUM(n_prueba), f"semilla {int(semilla)}", None, "tag", "azul"),
            ]))
        a, b = st.columns([1, 1.15], gap="medium")
        with a:
            with panel("Tablas de las pruebas", "Recurrencia, frecuencias observadas y esperadas.", "table_chart", "pizarra"):
                if hasattr(g, "primeros"):
                    html_md(vista.subtitulo("Primeros pasos de la recurrencia"))
                    st.dataframe(pd.DataFrame(crear_generador("congruencial", int(semilla)).primeros(10), columns=["i", "Xᵢ", "Uᵢ"]),
                                 hide_index=True, width="stretch")
                html_md(vista.subtitulo(f"Uniformidad (k = {pu['k']})"))
                st.dataframe(pd.DataFrame({"Intervalo": [f"[{i / 10:.1f}, {(i + 1) / 10:.1f})" for i in range(pu["k"])], "FO": pu["fo"],
                                           "FE": pu["fe"], "(FO−FE)²/FE": (pu["fo"] - pu["fe"]) ** 2 / pu["fe"]}).round(3),
                             hide_index=True, width="stretch")
        with b:
            with panel("Independencia", f"Rejilla {ps['m']}×{ps['m']} · frecuencia esperada por celda (n − 1)/m² = {W.n_es(ps['fe'], 1)}",
                       "scatter_plot", "violeta"):
                grafico(W.dispersion_u(u))
                st.dataframe(pd.DataFrame(ps["rejilla"], index=[f"Uᵢ∈{i + 1}" for i in range(ps["m"])],
                                          columns=[f"Uᵢ₊₁∈{j + 1}" for j in range(ps["m"])]), width="stretch")

    else:
        lam = pd.DataFrame({cal.TIPO_NOMBRE[t]: P.lam["ROT"][i] for i, t in enumerate(cal.TIPOS)}, index=[f"{h:02d}:00" for h in HORAS]).T
        with panel("Tasa de llegadas por hora", "Vehículos de rotación, sin quincena ni temporada.", "show_chart", "azul"):
            grafico(W.lambdas(lam))
            with st.expander("Tabla de λ por hora", icon=":material/table:"):
                st.dataframe(lam.round(1), width="stretch")
        with panel("Otros parámetros estimados", f"Flujos simulados: {', '.join(FLUJO_NOMBRE.values())}.", "tune", "pizarra"):
            tonos_q = ["azul", "teal", "violeta", "ambar"]
            html_md(vista.tarjetas(
                [kpi(f"Quincena · {cal.TIPO_NOMBRE[t]}", f"×{W.n_es(v, 2)}", "aumento de la demanda", None, "payments", tonos_q[i])
                 for i, (t, v) in enumerate(P.f_quincena.items())]
                + [kpi("Variación entre días (σ)", W.n_es(P.sigma_dia, 3), "desviación del factor diario Z", None, "ssid_chart", "indigo"),
                   kpi("Tickets extraviados", PCT(P.p_extraviado), "proporción observada", None, "confirmation_number", "coral")]))
