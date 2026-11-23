"""
Prueba de la interfaz completa con el probador oficial de Streamlit (sin abrir el navegador):
carga la app, simula diciembre, revisa que se arme el Excel y recorre las vistas.
Ejecutar desde la carpeta del proyecto:   python tests/probar_app.py
"""
import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def sin_errores(at, paso):
    errores = [e.value for e in at.exception]
    assert not errores, f"{paso}: {errores}"
    print(f"{paso}: OK")


at = AppTest.from_file(APP, default_timeout=600)
t = time.time()
at.run()
sin_errores(at, f"carga inicial ({time.time() - t:.1f} s)")

t = time.time()
next(b for b in at.button if b.label == "Simular").click().run()
sin_errores(at, f"simulación ({time.time() - t:.1f} s)")
assert at.session_state["excel"], "no se generó el Excel"
print("Excel:", len(at.session_state["excel"]), "bytes")

next(b for b in at.button if b.label == "Validar el modelo con octubre").click().run()
sin_errores(at, "validación")
for vista in ["Por qué Montecarlo", "Generador aleatorio", "Parámetros estimados"]:
    at.session_state["vista_modelo"] = vista
    at.run()
    sin_errores(at, vista)
at.session_state["vista_mapa"] = "Cada fecha × hora"
at.run()
sin_errores(at, "mapa por fecha")
next(b for b in at.button if b.label == "Siguiente").click().run()
sin_errores(at, f"mes siguiente ({at.session_state['mes']}/{at.session_state['anio']})")
print("TODO OK")
