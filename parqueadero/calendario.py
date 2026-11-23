"""
Calendario de la simulación: festivos de Colombia (con su motivo), fechas comerciales,
temporadas alta / media / baja y clasificación de cada día.

Por qué importa para la lógica
------------------------------
En el registro de octubre 2026 no todos los días se comportan igual:
  * Lun–Jue reciben ~600 vehículos, viernes ~870, sábado ~1.170 y domingo ~995.
  * El lunes festivo 12-oct recibió 985 vehículos: se comportó como un domingo, no como un lunes.
  * Los días de quincena (1, 15, 16 y los dos últimos del mes) traen entre 12 % y 34 % más carros.
Por eso cada día del calendario se clasifica antes de simular: tipo de día, festivo, quincena,
puente y temporada. Cada clasificación cambia la tasa de llegadas que usa el Montecarlo.
"""
from __future__ import annotations

import calendar as _cal
import datetime as dt
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 1. Festivos de Colombia
# ---------------------------------------------------------------------------
# Ley 51 de 1983 ("Ley Emiliani"): varios festivos se trasladan al lunes siguiente.
# Los festivos religiosos móviles dependen de la fecha de Pascua (Domingo de Resurrección).

FESTIVOS_FIJOS = {
    (1, 1): ("Año Nuevo", "Inicio del año civil. Festivo fijo: no se traslada."),
    (5, 1): ("Día del Trabajo", "Día Internacional de los Trabajadores, en memoria de las luchas obreras por la jornada de 8 horas. Festivo fijo."),
    (7, 20): ("Día de la Independencia", "Grito de Independencia del 20 de julio de 1810 en Santafé de Bogotá. Festivo fijo."),
    (8, 7): ("Batalla de Boyacá", "Victoria del 7 de agosto de 1819 que aseguró la independencia de la Nueva Granada. Festivo fijo."),
    (12, 8): ("Inmaculada Concepción", "Fiesta católica de la concepción de María sin pecado original (la víspera es la Noche de las Velitas). Festivo fijo."),
    (12, 25): ("Navidad", "Celebración del nacimiento de Jesús. Festivo fijo."),
}

FESTIVOS_TRASLADABLES = {
    (1, 6): ("Reyes Magos", "Epifanía: visita de los Reyes Magos al niño Jesús. Se traslada al lunes siguiente (Ley Emiliani)."),
    (3, 19): ("San José", "Honra a San José, esposo de María y padre adoptivo de Jesús. Se traslada al lunes siguiente (Ley Emiliani)."),
    (6, 29): ("San Pedro y San Pablo", "Fiesta de los apóstoles Pedro y Pablo. Se traslada al lunes siguiente (Ley Emiliani)."),
    (7, 9): ("Virgen de Chiquinquirá", "Patrona de Colombia. Festivo incorporado al calendario nacional desde 2026; se traslada al lunes."),
    (8, 15): ("Asunción de la Virgen", "Fiesta católica de la subida de María al cielo. Se traslada al lunes siguiente (Ley Emiliani)."),
    (10, 12): ("Día de la Raza", "Llegada de Cristóbal Colón a América en 1492 (encuentro de dos mundos). Se traslada al lunes siguiente (Ley Emiliani)."),
    (11, 1): ("Todos los Santos", "Fiesta católica en honor a todos los santos. Se traslada al lunes siguiente (Ley Emiliani)."),
    (11, 11): ("Independencia de Cartagena", "El 11 de noviembre de 1811 Cartagena declaró su independencia absoluta de España. Se traslada al lunes siguiente (Ley Emiliani)."),
}

FESTIVOS_PASCUA = [
    # (días desde Pascua, nombre, motivo)
    (-3, "Jueves Santo", "Semana Santa: conmemora la Última Cena. Depende de la fecha de Pascua; no se traslada."),
    (-2, "Viernes Santo", "Semana Santa: conmemora la crucifixión de Jesús. Depende de la fecha de Pascua; no se traslada."),
    (43, "Ascensión del Señor", "Subida de Jesús al cielo, 40 días después de Pascua. Se celebra el lunes siguiente (Pascua + 43 días)."),
    (64, "Corpus Christi", "Fiesta del cuerpo y la sangre de Cristo, 60 días después de Pascua. Se celebra el lunes siguiente (Pascua + 64 días)."),
    (71, "Sagrado Corazón", "Devoción al Sagrado Corazón de Jesús; Colombia fue consagrada a él en 1902. Se celebra el lunes siguiente (Pascua + 71 días)."),
]


def pascua(anio: int) -> dt.date:
    """Domingo de Pascua (algoritmo de Meeus/Jones/Butcher para el calendario gregoriano)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(anio, mes, dia)


def _siguiente_lunes(fecha: dt.date) -> dt.date:
    return fecha + dt.timedelta(days=(7 - fecha.weekday()) % 7)


def festivos(anio: int) -> dict[dt.date, dict]:
    """Devuelve {fecha: {'nombre', 'motivo', 'fecha_original', 'trasladado'}} para un año."""
    out: dict[dt.date, dict] = {}
    for (m, d), (nombre, motivo) in FESTIVOS_FIJOS.items():
        f = dt.date(anio, m, d)
        out[f] = dict(nombre=nombre, motivo=motivo, fecha_original=f, trasladado=False)
    for (m, d), (nombre, motivo) in FESTIVOS_TRASLADABLES.items():
        if (m, d) == (7, 9) and anio < 2026:
            continue
        orig = dt.date(anio, m, d)
        f = _siguiente_lunes(orig)
        out[f] = dict(nombre=nombre, motivo=motivo, fecha_original=orig, trasladado=f != orig)
    p = pascua(anio)
    for delta, nombre, motivo in FESTIVOS_PASCUA:
        f = p + dt.timedelta(days=delta)
        out[f] = dict(nombre=nombre, motivo=motivo, fecha_original=f, trasladado=delta > 0)
    return dict(sorted(out.items()))


_CACHE: dict[int, dict] = {}


def festivo(fecha: dt.date) -> dict | None:
    if fecha.year not in _CACHE:
        _CACHE[fecha.year] = festivos(fecha.year)
    return _CACHE[fecha.year].get(fecha)


# ---------------------------------------------------------------------------
# 2. Temporadas y fechas comerciales
# ---------------------------------------------------------------------------
# Los datos solo cubren octubre de 2026, así que la temporada se modela con factores
# relativos a octubre (octubre = 1,00). Son SUPUESTOS sustentados en reportes del sector
# (Acecolombia, Fenalco, Alcaldía de Bogotá) y se pueden editar desde la interfaz.

FACTOR_MES = {
    1: (0.90, "Baja", "Cuesta de enero: después de diciembre el comercio se desacelera (Fenalco), aunque hay temporada de rebajas y regreso a clases."),
    2: (0.92, "Baja", "Enero y febrero son los meses menos dinámicos del comercio; la temporada escolar sostiene algunas ventas."),
    3: (0.97, "Media", "Mes normal; si cae Semana Santa, muchas familias viajan fuera de la ciudad."),
    4: (0.97, "Media", "Mes normal; Semana Santa y puentes reducen la población que permanece en la ciudad."),
    5: (1.00, "Media", "Día de la Madre (segundo domingo de mayo) mueve el comercio."),
    6: (1.08, "Alta", "Prima de mitad de año (pago hasta el 30 de junio), vacaciones escolares y Día del Padre."),
    7: (1.03, "Media", "Primera mitad del mes aún en vacaciones de mitad de año."),
    8: (0.97, "Media", "Mes de regreso a la rutina después de vacaciones."),
    9: (1.00, "Media", "Amor y Amistad (tercer sábado) abre la temporada alta de fin de año."),
    10: (1.00, "Media", "Mes de los datos (base = 1,00): receso escolar y Halloween."),
    11: (1.05, "Media", "Black Friday y comienzo de las compras navideñas."),
    12: (1.20, "Alta", "Temporada navideña y prima de diciembre: el tráfico de los centros comerciales sube entre 20 % y 30 % (Acecolombia)."),
}

EVENTOS_FUENTES = {
    "navidad": "Acecolombia vía La República: el tráfico de visitantes crece 20–25 % en la temporada navideña y la semana previa a Navidad 20–30 %.",
    "black": "Fenalco Bogotá: en el Black Weekend los centros comerciales tuvieron ~30 % más flujo que otros fines de semana (el viernes fue el día más concurrido).",
    "halloween": "Acecolombia vía La República: Halloween registra un crecimiento cercano a 10 % frente a un día promedio.",
    "padre": "Centros comerciales de Bogotá proyectan entre 10 % y 45 % más tráfico el fin de semana del Día del Padre.",
    "madre": "Acecolombia: el Día de la Madre genera ventas adicionales de hasta 30 % frente a un mes normal.",
    "amor": "Fenalco/centros comerciales: Amor y Amistad inicia la temporada alta del segundo semestre.",
    "prima": "Artículo 306 del Código Sustantivo del Trabajo: prima hasta el 30 de junio y hasta el 20 de diciembre.",
    "puente": "Alcaldía de Bogotá: en cada puente festivo salen de la ciudad alrededor de un millón de vehículos.",
}


def _n_esimo_dia(anio, mes, weekday, n):
    """n-ésimo día de la semana (0 = lunes) del mes; n = -1 → último."""
    dias = [d for d in _cal.Calendar().itermonthdates(anio, mes) if d.month == mes and d.weekday() == weekday]
    return dias[n]


@dataclass
class Evento:
    inicio: dt.date
    fin: dt.date
    nombre: str
    factor: float
    motivo: str


def eventos_comerciales(anio: int, factores: dict | None = None) -> list[Evento]:
    """Fechas comerciales que suben o bajan la demanda de un día concreto."""
    f = dict(black_viernes=1.30, black_finde=1.15, navidad_semana=1.10, halloween=1.10, padre=1.15, madre=1.20, amor=1.10)
    if factores:
        f.update(factores)
    bf = _n_esimo_dia(anio, 11, 4, -1)
    # Día del Padre: tercer domingo de junio; en 2026 Fenalco lo adelantó al 14 de junio (Mundial y puente festivo).
    padre = dt.date(2026, 6, 14) if anio == 2026 else _n_esimo_dia(anio, 6, 6, 2)
    ev = [
        Evento(bf, bf, "Black Friday", f["black_viernes"], EVENTOS_FUENTES["black"]),
        Evento(bf + dt.timedelta(days=1), bf + dt.timedelta(days=2), "Black Weekend", f["black_finde"], EVENTOS_FUENTES["black"]),
        Evento(dt.date(anio, 12, 18), dt.date(anio, 12, 24), "Semana previa a Navidad", f["navidad_semana"], EVENTOS_FUENTES["navidad"]),
        Evento(dt.date(anio, 10, 31), dt.date(anio, 10, 31), "Halloween", f["halloween"], EVENTOS_FUENTES["halloween"]),
        Evento(padre, padre, "Día del Padre", f["padre"], EVENTOS_FUENTES["padre"]),
        Evento(_n_esimo_dia(anio, 5, 6, 1), _n_esimo_dia(anio, 5, 6, 1), "Día de la Madre", f["madre"], EVENTOS_FUENTES["madre"]),
        Evento(_n_esimo_dia(anio, 9, 5, 2), _n_esimo_dia(anio, 9, 5, 2), "Amor y Amistad", f["amor"], EVENTOS_FUENTES["amor"]),
    ]
    return ev


# ---------------------------------------------------------------------------
# 3. Clasificación de cada día
# ---------------------------------------------------------------------------
TIPOS = ["LJ", "VI", "SA", "DF"]
TIPO_NOMBRE = {"LJ": "Lun–Jue", "VI": "Viernes", "SA": "Sábado", "DF": "Domingo/festivo"}
DIA_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def es_quincena(fecha: dt.date) -> bool:
    """Días de pago de quincena y el día siguiente: 1, 15, 16 y los dos últimos del mes."""
    ultimo = _cal.monthrange(fecha.year, fecha.month)[1]
    return fecha.day in (1, 15, 16, ultimo - 1, ultimo)


def tipo_dia(fecha: dt.date) -> str:
    if festivo(fecha) or fecha.weekday() == 6:
        return "DF"
    return {4: "VI", 5: "SA"}.get(fecha.weekday(), "LJ")


def es_puente(fecha: dt.date) -> str | None:
    """Fin de semana largo: sábado-domingo + lunes festivo, viernes festivo + fin de semana, o Semana Santa."""
    p = pascua(fecha.year)
    if p - dt.timedelta(days=3) <= fecha <= p:
        return "Semana Santa"
    if fecha.weekday() in (5, 6, 0):                       # sábado, domingo o lunes
        lunes = fecha + dt.timedelta(days=(7 - fecha.weekday()) % 7)
        fe = festivo(lunes)
        if fe:
            return fe["nombre"]
    if fecha.weekday() in (4, 5, 6):                       # viernes festivo + fin de semana
        viernes = fecha - dt.timedelta(days=fecha.weekday() - 4)
        fe = festivo(viernes)
        if fe:
            return fe["nombre"]
    return None


@dataclass
class DiaInfo:
    fecha: dt.date
    tipo: str
    festivo: dict | None
    quincena: bool
    puente: str | None
    factor_mes: float
    eventos: list = field(default_factory=list)
    factor_eventos: float = 1.0
    factor_puente: float = 1.0
    motivo_temporada: str = ""

    @property
    def factor_temporada(self) -> float:
        return self.factor_mes * self.factor_eventos * self.factor_puente

    @property
    def temporada(self) -> str:
        f = self.factor_temporada
        return "Alta" if f >= 1.10 else ("Baja" if f <= 0.95 else "Media")

    @property
    def etiqueta(self) -> str:
        return f"{self.fecha.day:02d}-{MESES[self.fecha.month - 1][:3].lower()} {DIA_SEMANA[self.fecha.weekday()][:3].lower()}"


def clasificar(fecha: dt.date, factores_mes: dict | None = None, factores_eventos: dict | None = None, factor_puente: float = 1.0) -> DiaInfo:
    fm = (factores_mes or {}).get(fecha.month, FACTOR_MES[fecha.month][0])
    evs = [e for e in eventos_comerciales(fecha.year, factores_eventos) if e.inicio <= fecha <= e.fin]
    fe = 1.0
    for e in evs:
        fe *= e.factor
    pu = es_puente(fecha)
    motivo = FACTOR_MES[fecha.month][2]
    if evs:
        motivo += " Evento: " + ", ".join(e.nombre for e in evs) + "."
    if pu:
        motivo += f" Puente festivo ({pu}): parte de la población sale de la ciudad."
    return DiaInfo(fecha=fecha, tipo=tipo_dia(fecha), festivo=festivo(fecha), quincena=es_quincena(fecha), puente=pu,
                   factor_mes=fm, eventos=evs, factor_eventos=fe, factor_puente=(factor_puente if pu else 1.0), motivo_temporada=motivo)


def semanas_del_mes(anio: int, mes: int) -> list[list[dt.date]]:
    """Semanas (lunes a domingo) que cubren el mes, para dibujar el calendario."""
    return _cal.Calendar(firstweekday=0).monthdatescalendar(anio, mes)
