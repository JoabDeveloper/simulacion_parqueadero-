"""
Pruebas del modelo. Ejecutar desde la carpeta del proyecto con:   python -m pytest -q
"""
import datetime as dt
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parqueadero import calendario as cal  # noqa: E402
from parqueadero.estadisticas import resumen, validar  # noqa: E402
from parqueadero.generador import crear_generador, prueba_series, prueba_uniformidad  # noqa: E402
from parqueadero.motor import Config, atender, simular  # noqa: E402
from parqueadero.parametros import cargar_y_estimar  # noqa: E402

DATOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datos", "Registro_parqueadero_simulado_oct2026-2.xlsx")


@pytest.fixture(scope="module")
def P():
    return cargar_y_estimar(DATOS)[1]


# --- calendario -------------------------------------------------------------
def test_pascua():
    assert cal.pascua(2026) == dt.date(2026, 4, 5)
    assert cal.pascua(2027) == dt.date(2027, 3, 28)


def test_festivos_2026():
    f = cal.festivos(2026)
    esperadas = {dt.date(2026, 1, 1), dt.date(2026, 1, 12), dt.date(2026, 3, 23), dt.date(2026, 4, 2), dt.date(2026, 4, 3),
                 dt.date(2026, 5, 1), dt.date(2026, 5, 18), dt.date(2026, 6, 8), dt.date(2026, 6, 15), dt.date(2026, 6, 29),
                 dt.date(2026, 7, 20), dt.date(2026, 8, 7), dt.date(2026, 8, 17), dt.date(2026, 10, 12), dt.date(2026, 11, 2),
                 dt.date(2026, 11, 16), dt.date(2026, 12, 8), dt.date(2026, 12, 25)}
    assert esperadas <= set(f)
    assert all(d["motivo"] for d in f.values())          # cada festivo explica por qué lo es


def test_clasificacion():
    assert cal.tipo_dia(dt.date(2026, 10, 12)) == "DF"     # lunes festivo se comporta como domingo
    assert cal.es_quincena(dt.date(2026, 10, 30)) and cal.es_quincena(dt.date(2026, 10, 15))
    assert cal.clasificar(dt.date(2026, 12, 24)).temporada == "Alta"
    assert cal.clasificar(dt.date(2027, 1, 20)).temporada == "Baja"


# --- números aleatorios -----------------------------------------------------
def test_generador_reproducible_y_uniforme():
    a = crear_generador("congruencial", 12345).random(20000)
    b = crear_generador("congruencial", 12345).random(20000)
    assert np.array_equal(a, b)
    assert ((a > 0) & (a < 1)).all()
    assert prueba_uniformidad(a)["acepta"]
    assert prueba_series(a)["acepta"]


# --- entradas y salidas -----------------------------------------------------
def test_atender_respeta_capacidad():
    # 3 celdas, 5 carros que llegan a la vez y se quedan 1 hora: entran 3, se van 2 (tolerancia 0)
    e = atender(np.array([8.0, 8.0, 8.0, 8.0, 8.0]), np.ones(5), 3, 0.0)
    assert np.isnan(e).sum() == 2
    # con tolerancia de 1 hora los dos últimos esperan a que salgan los primeros
    e = atender(np.array([8.0, 8.0, 8.0, 8.0, 8.0]), np.ones(5), 3, 1.0)
    assert np.isnan(e).sum() == 0 and np.isclose(np.nanmax(e), 9.0)


# --- simulación completa ----------------------------------------------------
def test_simulacion_reproduce_octubre(P):
    v = validar(P, replicas=100)
    assert v["mape"] < 0.10                     # error medio por día menor a 10 %
    assert v["cobertura"] >= 0.80               # la mayoría de días reales caen en P5–P95


def test_mas_demanda_mas_riesgo(P):
    fechas = [dt.date(2026, 12, 19), dt.date(2026, 12, 20)]
    base = resumen(simular(P, fechas, Config(replicas=60, guardar_registro=False)), P)
    alta = resumen(simular(P, fechas, Config(replicas=60, crecimiento=0.6, guardar_registro=False)), P)
    assert alta["kpi"]["llegadas_total"] > base["kpi"]["llegadas_total"]
    assert alta["kpi"]["prob_carros_llenos"] >= base["kpi"]["prob_carros_llenos"]
    assert alta["riesgo"]["perdida_cupo_media"] >= base["riesgo"]["perdida_cupo_media"]


def test_ocupacion_nunca_supera_capacidad(P):
    res = simular(P, [dt.date(2026, 12, 19)], Config(replicas=30, crecimiento=0.8))
    assert res.RD["pico_carros"].max() <= res.capacidad["A_rot"]
    reg = res.registro
    dentro = reg[reg["estado"].str.startswith("Entró")]
    assert (dentro["salida_h"] > dentro["entrada_h"]).all()
    assert (dentro["entrada_h"] >= dentro["llegada_h"] - 1e-9).all()
