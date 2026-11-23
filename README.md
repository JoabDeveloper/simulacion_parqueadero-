# Parqueadero Plaza El Mirador – Simulación Montecarlo

Programa en **Python** (interfaz y lógica) que simula, vehículo por vehículo, las **entradas y salidas** del
parqueadero para los días que se elijan en un **calendario**. Parte del registro real de octubre de 2026
(24.830 vehículos) y tiene en cuenta festivos de Colombia, quincenas, puentes, temporada alta/baja y fechas
comerciales. La interfaz es *responsive*: funciona en computador, tablet y celular.

---

## 0. Publicación en internet (Streamlit Community Cloud)

La app es de Streamlit y necesita un servidor de Python, por eso se publica en **Streamlit Community Cloud**
(gratis, conectado a este repositorio). GitHub Pages no sirve para esto porque solo aloja páginas estáticas.

1. Entra a **https://share.streamlit.io** e inicia sesión con la cuenta de GitHub dueña del repositorio.
2. **Create app → Deploy a public app from GitHub** y llena:
   - *Repository:* `JoabDeveloper/simulacion_parqueadero-` · *Branch:* `main` · *Main file path:* `app.py`
   - *App URL:* el nombre que quieras (p. ej. `parqueadero-plaza-el-mirador`).
   - *Advanced settings → Python version:* **3.13** (o 3.12).
3. **Deploy**. La primera vez tarda unos minutos mientras instala `requirements.txt`.

Cada `git push` a `main` actualiza la app publicada automáticamente. Si la app no recibe visitas en varios días,
Streamlit la pone en reposo; basta abrirla y pulsar el botón para despertarla.

---

## 1. Cómo ejecutarlo en tu computador

Requisitos: Python 3.10 o superior.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Se abre en el navegador (http://localhost:8501). Para cerrarlo, cierra la ventana negra de la consola. En Windows también puedes hacer doble clic en `iniciar_windows.bat`.

Sin interfaz (línea de comandos):

```bash
python simular_cli.py --desde 2026-12-01 --hasta 2026-12-31            # todo diciembre
python simular_cli.py --desde 2026-12-18 --hasta 2026-12-24 --franja 12 18 --replicas 1000
python simular_cli.py --desde 2027-01-01 --hasta 2027-03-31 --dias-semana 5,6   # solo sábados y domingos
python simular_cli.py --festivos 2027                                  # festivos y su motivo
python simular_cli.py --validar                                        # compara el modelo con octubre real
```

Pruebas automáticas: `python -m pytest -q` (modelo) y `python tests/probar_app.py` (interfaz completa).

---

## 2. Qué muestra la interfaz

| Pestaña | Contenido |
|---|---|
| **Inicio** | Cómo usar el simulador en 4 pasos, qué hace en palabras simples, glosario (réplica, P5/P95, VaR…) y qué trae el Excel. |
| **Calendario** | Calendario del mes (festivos, Q = quincena, temporada con su factor). A la derecha: selección rápida (todo el mes, Lun–Jue, fines de semana, festivos, quincenas, temporada alta), días del mes, rango de fechas, franja horaria y el botón **Simular**. Abajo, en desplegables: festivos y por qué, temporada de cada día y fuentes de los factores. |
| **Resultados** | Tarjetas con los indicadores clave, recomendaciones, vehículos esperados por día, días pico/valle, horas pico/valle y el detalle por día. |
| **Por hora** | Mapas de calor (día de la semana × hora o fecha × hora), entradas contra salidas, y un día simulado vehículo por vehículo. |
| **Riesgo e ingresos** | Ingreso esperado, meta, probabilidad de quedar bajo la meta, VaR 95 %, IC 95 %, pérdida por falta de cupo, histogramas (Sturges), convergencia y la decisión del parqueadero externo. |
| **Modelo y datos** | Datos reales de octubre, tabla de Sturges, validación del modelo, por qué Montecarlo, generador congruencial con sus pruebas χ² y parámetros estimados. |

### El Excel descargable

Al pulsar **Simular** el programa arma automáticamente un libro de Excel y muestra el botón **Descargar la simulación en Excel**
(en el Calendario y en Resultados). Hojas:

| Hoja | Contenido |
|---|---|
| Resumen | Tablero: tarjetas de indicadores, recomendaciones y 4 gráficas. |
| Por día | Una fila por día con formato condicional y gráficas de vehículos, ingreso vs meta y probabilidad de lleno. |
| Por hora | Entradas, salidas y carros dentro por hora, horas pico/valle, ocupación por tipo de día, Sturges y la imagen de un día vehículo por vehículo. |
| Calor semana / Calor fechas | Mapas de calor por hora con escala de colores de Excel. |
| Riesgo | Indicadores de riesgo, histogramas del ingreso y de la pérdida, convergencia y riesgo por día. |
| Externo | Decisión y beneficio por día del parqueadero externo. |
| Calendario | Tipo de día, festivo, quincena, puente, temporada y su motivo. |
| Réplicas | Ingreso, pérdida y faltante de cada réplica. |
| Vehículos | Cada vehículo simulado (réplica 1): llegada, entrada, salida, permanencia, espera, estado y valor. |
| Parámetros y guía | Qué contiene cada hoja y todos los supuestos usados. |

Las gráficas son nativas de Excel (se pueden editar). El mismo libro se genera desde la línea de comandos (`resultados.xlsx`).

---

## 3. ¿Por qué Montecarlo?

El método de Montecarlo repite un experimento muchas veces con números aleatorios para obtener la
**distribución** de los resultados (no un solo número). Aquí es la mejor opción porque:

1. **La demanda es incierta**: el mismo tipo de día puede traer cientos de vehículos más o menos.
2. **La tasa de llegadas cambia por hora, tipo de día, quincena y temporada**. Las fórmulas clásicas de colas
   (M/M/c) suponen una tasa constante y permanencias exponenciales.
3. **Las permanencias reales no son exponenciales**: se usan los percentiles observados en octubre.
4. **La capacidad crea efectos no lineales**: con 360 celdas, un 10 % más de demanda puede no causar nada o llenar
   el parqueadero toda la tarde. Solo simulando se ve cuándo ocurre.
5. **Mide riesgo**: probabilidad de lleno, de no alcanzar la meta, VaR 95 %, intervalos de confianza.
6. **Responde "¿qué pasa si…?"**: diciembre, +30 % de demanda, menos celdas, otra tarifa, un parqueadero externo.

## 4. ¿Por qué simular entradas **y salidas** de cada vehículo?

El parqueadero se llena por los carros que **todavía no han salido**. Si solo se cuentan llegadas, la ocupación
hay que suponerla (por ejemplo con la ley de Little, L = λ·W, que da un promedio). Siguiendo cada vehículo, la
ocupación, las esperas y los rechazos **salen del modelo** y se ven minuto a minuto y hora por hora.

Pasos de cada réplica (todos con la transformada inversa sobre U ~ Uniforme(0,1)):

| Paso | Qué se genera | Cómo |
|---|---|---|
| 1 | Factor del día Z | Box–Muller: Z = 1 + σ·√(−2 ln U₁)·cos(2πU₂) |
| 2 | Llegadas de cada hora N | Poisson(λ_hora · temporada · quincena · (1+g) · Z) con la acumulada |
| 3 | Minuto de llegada | h + U |
| 4 | Tipo de vehículo y cliente | Tabla acumulada de la mezcla observada en esa hora |
| 5 | Permanencia T | Percentiles empíricos de octubre interpolados (por cliente, vehículo, franja y tipo de día) |
| 6 | **Entrada** | Si hay celda libre entra; si no, espera hasta la tolerancia; si no se libera, se va (ingreso perdido) |
| 7 | **Salida** | Entrada + T; la celda queda libre |
| 8 | Cobro | Hora o fracción, tope 24 h, minutos de gracia, descuento por cliente, recargo por ticket extraviado |

Ecuaciones principales:

- λ(d,h) = λ_oct(tipo de día, h) · F_mes · F_evento · F_puente · F_quincena · (1 + g) · Z_d
- Ocupación(t) = número de vehículos con entrada ≤ t < salida;  lleno ⇔ Ocupación(t) ≥ capacidad
- Ingreso_r = Σ valor de los vehículos que entraron (en la franja);  Faltante_r = máx(0, Meta − Ingreso_r)
- P(Ingreso < Meta) ≈ (1/R)·Σ 1[Ingreso_r < Meta];  IC 95 % = media ± 1,96·s/√R

Los números aleatorios vienen de un **generador congruencial multiplicativo** (Park–Miller: Xᵢ₊₁ = 48 271·Xᵢ mod 2³¹−1),
validado con las pruebas χ² de uniformidad y de series (pestaña 📘).

---

## 5. Calendario, festivos y temporada

- **Festivos de Colombia** calculados para cualquier año: fijos, trasladables al lunes (Ley 51 de 1983, "Ley Emiliani")
  y los que dependen de la Pascua. Cada uno trae su motivo. Desde 2026 se incluye el día de la Virgen de Chiquinquirá.
- **Tipo de día**: Lun–Jue, Viernes, Sábado, Domingo/festivo. En octubre el lunes festivo 12 (985 vehículos) se comportó
  como un domingo (~995), no como un lunes normal (~604); por eso un festivo usa el patrón de domingo.
- **Quincena**: días 1, 15, 16 y los dos últimos del mes (se pagan salarios y sube la demanda).
- **Puentes**: sábado–domingo–lunes festivo y Semana Santa.
- **Temporada**: los datos solo cubren octubre, así que cada mes tiene un factor relativo a octubre (= 1,00) y
  algunas fechas un factor adicional. Son **supuestos editables** en la barra lateral:

| Mes | Factor | Temporada | Mes | Factor | Temporada |
|---|---|---|---|---|---|
| Enero | 0,90 | Baja | Julio | 1,03 | Media |
| Febrero | 0,92 | Baja | Agosto | 0,97 | Media |
| Marzo | 0,97 | Media | Septiembre | 1,00 | Media |
| Abril | 0,97 | Media | Octubre | 1,00 | Base |
| Mayo | 1,00 | Media | Noviembre | 1,05 | Media |
| Junio | 1,08 | Alta | Diciembre | 1,20 | Alta |

Fechas comerciales: Black Friday ×1,30 y su fin de semana ×1,15; semana previa a Navidad (18–24 dic) ×1,10;
Halloween ×1,10; Día de la Madre ×1,20; Día del Padre ×1,15 (en 2026 el comercio lo celebró el 14 de junio por la
segunda vuelta presidencial); Amor y Amistad ×1,10. Un día es de temporada **alta** si su factor total es ≥ 1,10 y
**baja** si es ≤ 0,95.

Fuentes de los supuestos:
- Acecolombia, tráfico de visitantes en temporada navideña +20–25 %: https://www.larepublica.co/especiales/centros-comerciales-y-navidad/flujo-de-visitantes-se-incrementa-25-durante-la-temporada-navidena-2573959
- Balance de Navidad 2023, +30 % de visitantes: https://www.larepublica.co/empresas/centros-comerciales-tuvieron-hasta-30-mas-de-visitantes-en-navidad-3774004
- Fenalco Bogotá, Black Weekend con ~30 % más flujo en centros comerciales: https://www.portafolio.co/negocios/comercio/comerciantes-de-bogota-reportaron-un-alza-de-hasta-el-70-en-ventas-por-black-friday-618976
- Día del Padre adelantado al 14 de junio de 2026: https://www.larepublica.co/empresas/comercio-adelanta-la-celebracion-del-dia-del-padre-por-segunda-vuelta-presidencial-4406163
- Puentes festivos: ~1 millón de vehículos salen de Bogotá: https://bogota.gov.co/mi-ciudad/movilidad/plan-exodo-retorno-y-movilidad-en-bogota-5-al-8-de-junio-de-2026
- Qué es la simulación de Montecarlo (AWS): https://aws.amazon.com/es/what-is/monte-carlo-simulation/

---

## 6. Validación

Simulando los 31 días reales de octubre con 200 réplicas:

- Error medio por día (MAPE) en vehículos ≈ **4,4 %**; total real 24.830 vs simulado ≈ 24.813.
- **94 %** de los días reales caen dentro del rango simulado P5–P95.
- Error medio del pico de carros dentro ≈ 8,5 %.

---

## 7. Supuestos y limitaciones

- Capacidad tomada de la numeración de celdas del registro (360 carros y 75 motos en rotación, 40 + 15 de mensualidad,
  6 en el muelle). Se puede cambiar.
- El archivo original no tenía la hoja de tarifas (sus fórmulas daban #REF!); se usan tarifas por defecto editables.
- La meta por defecto es el ingreso de un día igual de octubre × el factor de temporada del día (se puede usar sin ajuste
  o un valor fijo).
- Un conductor sin celda espera hasta 10 minutos (proveedores 30); si no se libera una celda, se va.
- Los factores de temporada son supuestos basados en reportes del sector: con datos de más meses se pueden estimar.

## 8. Estructura

```
app.py                 interfaz (Streamlit)
simular_cli.py         línea de comandos
parqueadero/
  calendario.py        festivos con motivo, temporada, quincena, puentes
  datos.py             lectura del Excel, tarifas, tabla de Sturges
  parametros.py        estimación de λ por hora, mezcla, permanencias, capacidad, ingreso de referencia
  generador.py         congruencial multiplicativo, pruebas χ² de uniformidad y de series
  motor.py             simulación Montecarlo de entradas y salidas
  estadisticas.py      KPIs, mapas de calor, picos/valles, riesgo, parqueadero externo, validación
  graficos.py          gráficos (matplotlib)
  vista.py             estilos, calendario y tarjetas en HTML
  reporte.py           libro de Excel con tablas, mapas de calor y gráficas
datos/                 registro de octubre de 2026
.streamlit/config.toml  colores de la interfaz
tests/                 pruebas (pytest) y prueba de la interfaz con el probador de Streamlit
```
