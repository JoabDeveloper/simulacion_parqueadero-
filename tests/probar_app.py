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
# en la MISMA ejecución del clic ya deben verse los resultados en las pestañas (sin «Todavía no hay resultados»)
assert "S" in at.session_state, "la simulación no guardó resultados"
vacios = [m.value for m in at.markdown if "Todavía no hay resultados" in m.value]
assert not vacios, f"hay pestañas sin resultados tras simular: {len(vacios)}"
print("resultados visibles en todas las pestañas: OK")

# el botón de descarga aparece de una vez y el Excel se arma en segundo plano
descargas = [e for e in at.get("download_button") if e.proto.label == "Descargar en Excel"]
assert descargas, "no aparece el botón «Descargar en Excel» tras simular"
t = time.time()
excel = at.session_state["excel_futuro"][0].result(timeout=300)
assert excel[:2] == b"PK", "el Excel no es un archivo .xlsx válido"
print(f"Excel en segundo plano: {len(excel)} bytes (listo {time.time() - t:.1f} s después de mostrar los resultados)")

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
