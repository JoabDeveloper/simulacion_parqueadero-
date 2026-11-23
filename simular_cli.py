"""
Simulación por línea de comandos (sin interfaz gráfica).

Ejemplos:
    python simular_cli.py --desde 2026-12-01 --hasta 2026-12-31
    python simular_cli.py --desde 2026-12-18 --hasta 2026-12-24 --franja 12 18 --replicas 1000
    python simular_cli.py --desde 2026-12-01 --hasta 2026-12-31 --crecimiento 0.3 --salida resultados_dic
    python simular_cli.py --festivos 2027
    python simular_cli.py --validar
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from parqueadero import calendario as cal
from parqueadero import graficos as G
from parqueadero.estadisticas import resumen, validar
from parqueadero.motor import Config, simular
from parqueadero.parametros import cargar_y_estimar
from parqueadero.reporte import a_excel

DATOS = Path(__file__).parent / "datos" / "Registro_parqueadero_simulado_oct2026-2.xlsx"


def fecha(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def cop(v):
    return f"$ {v:,.0f}".replace(",", ".")


def main():
    ap = argparse.ArgumentParser(description="Simulación Montecarlo del parqueadero (entradas y salidas)")
    ap.add_argument("--datos", default=str(DATOS), help="Registro del parqueadero (.xlsx)")
    ap.add_argument("--desde", type=fecha, help="Primer día (AAAA-MM-DD)")
    ap.add_argument("--hasta", type=fecha, help="Último día (AAAA-MM-DD)")
    ap.add_argument("--dias-semana", default="", help="Filtrar días: p. ej. 5,6 = sábados y domingos (0 = lunes)")
    ap.add_argument("--replicas", type=int, default=300)
    ap.add_argument("--semilla", type=int, default=12345)
    ap.add_argument("--generador", choices=["congruencial", "numpy"], default="congruencial")
    ap.add_argument("--crecimiento", type=float, default=0.0, help="0.25 = 25 %% más demanda que octubre")
    ap.add_argument("--franja", type=int, nargs=2, default=[7, 22], metavar=("DESDE", "HASTA"), help="Franja horaria del riesgo")
    ap.add_argument("--meta-pct", type=float, default=1.0, help="Meta = %% del ingreso de un día igual de octubre (1.0 = 100 %%)")
    ap.add_argument("--meta-fija", type=float, default=None, help="Meta fija del lapso en COP")
    ap.add_argument("--meta-sin-temporada", action="store_true", help="No ajustar la meta por el factor de temporada")
    ap.add_argument("--salida", default="resultados", help="Carpeta para gráficos y Excel")
    ap.add_argument("--festivos", type=int, metavar="AÑO", help="Solo lista los festivos de ese año con su motivo")
    ap.add_argument("--validar", action="store_true", help="Compara el modelo con los 31 días reales de octubre")
    a = ap.parse_args()

    if a.festivos:
        print(f"Festivos de Colombia {a.festivos}:")
        for f, d in cal.festivos(a.festivos).items():
            extra = f" (se celebra el {d['fecha_original']:%d/%m}, Ley Emiliani)" if d["trasladado"] and d["fecha_original"] != f else ""
            print(f"  {f:%d/%m/%Y} {cal.DIA_SEMANA[f.weekday()]:<10} {d['nombre']}{extra}\n      → {d['motivo']}")
        return

    print("Leyendo datos y estimando parámetros…")
    df, P = cargar_y_estimar(a.datos)

    if a.validar:
        v = validar(P, replicas=a.replicas, semilla=a.semilla)
        print(f"MAPE vehículos/día: {v['mape']:.2%} · días reales dentro de P5–P95: {v['cobertura']:.0%} · "
              f"MAPE pico de carros: {v['mape_pico']:.2%} · total real {v['total_real']} vs simulado {v['total_sim']:.0f}")
        print(v["tabla"].round(1).to_string(index=False))
        return

    if not (a.desde and a.hasta):
        ap.error("indica --desde y --hasta (o usa --festivos / --validar)")
    fechas = [a.desde + dt.timedelta(days=i) for i in range((a.hasta - a.desde).days + 1)]
    if a.dias_semana:
        filtro = {int(x) for x in a.dias_semana.split(",")}
        fechas = [f for f in fechas if f.weekday() in filtro]

    cfg = Config(replicas=a.replicas, semilla=a.semilla, generador=a.generador, crecimiento=a.crecimiento,
                 franja=tuple(a.franja), meta_pct=a.meta_pct, meta_fija=a.meta_fija,
                 meta_temporada=not a.meta_sin_temporada)
    res = simular(P, fechas, cfg, progreso=lambda x: print(f"\r  simulando… {x:4.0%}", end=""))
    print()
    S = resumen(res, P)
    k, r, e = S["kpi"], S["riesgo"], S["externo"]

    print(f"\n{len(fechas)} días × {a.replicas} réplicas = {len(fechas) * a.replicas} jornadas en {res.segundos:.1f} s")
    print("\nFestivos del periodo:")
    for i in res.dias:
        if i.festivo:
            print(f"  {i.fecha:%d/%m/%Y} {i.festivo['nombre']}: {i.festivo['motivo']}")
    print("\nKPIs")
    print(f"  Vehículos esperados: {k['llegadas_total']:,.0f}  ({k['llegadas_dia']:,.0f} por día)")
    print(f"  Se van sin cupo: {k['sin_cupo_total']:,.0f} · Prob. carros llenos: {k['prob_carros_llenos']:.1%} · muelle lleno: {k['prob_muelle_lleno']:.1%}")
    print(f"  Ocupación pico máxima: {k['ocupacion_pico']:.0%} ({k['dia_ocupacion_pico']}) · espera prom.: {k['espera_prom']:.1f} min")
    print(f"\nRiesgo de ingresos (franja {r['franja']})")
    print(f"  Ingreso esperado: {cop(r['ingreso_media'])}  IC95 [{cop(r['ic95'][0])}, {cop(r['ic95'][1])}]")
    print(f"  Meta: {cop(r['meta'])} · P(ingreso < meta) = {r['prob_bajo_meta']:.1%} · VaR95 faltante: {cop(r['var95_faltante'])} ({r['nivel_meta']})")
    print(f"  Pérdida por falta de cupo: media {cop(r['perdida_cupo_media'])}, P95 {cop(r['perdida_cupo_p95'])} ({r['nivel_cupo']})")
    print(f"\nParqueadero externo: {e['decision']}" + (f" → días: {', '.join(e['dias_rentables'])}" if e["dias_rentables"] else ""))
    print("\nDías:")
    print(S["dias"][["Día", "Festivo", "Temporada", "Llegadas (media)", "Prob. carros llenos", "Ingreso (media)", "Nivel"]]
          .round(2).to_string(index=False))

    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    figs = {
        "01_llegadas_por_dia.png": G.barras_dias(S["dias"]),
        "02_calor_ocupacion_dia_hora.png": G.mapa_calor(S["mapas_fecha"]["Ocupación de carros (%)"], "Ocupación de carros (%) por día y hora", rojo=True, vmin=0, vmax=100, etiqueta="%"),
        "03_calor_entradas_dia_semana.png": G.mapa_calor(S["mapas_dsem"]["Entradas por hora"], "Entradas por hora (día de la semana)"),
        "04_calor_prob_lleno.png": G.mapa_calor(S["mapas_fecha"]["Probabilidad de carros llenos (%)"], "Probabilidad de carros llenos (%)", rojo=True, vmin=0, vmax=100, etiqueta="%"),
        "05_entradas_salidas_por_hora.png": G.perfil_entradas_salidas(S["perfil"], res.capacidad["A_rot"]),
        "07_riesgo_ingreso.png": G.histograma_sturges(r["ingreso_por_replica"], "Distribución del ingreso del lapso", r["meta"], "Meta"),
        "08_convergencia.png": G.convergencia(r["convergencia"]),
    }
    dia_pico = S["dias"].loc[S["dias"]["Llegadas (media)"].idxmax(), "Fecha"]
    figs["06_entradas_salidas_dia_pico.png"] = G.gantt_dia(res.registro[res.registro["fecha"] == dia_pico], res.capacidad["A_rot"])
    for (anio, mes) in sorted({(f.year, f.month) for f in fechas}):
        figs[f"09_calendario_{anio}_{mes:02d}.png"] = G.calendario_resultados(S["dias"], anio, mes, "Llegadas (media)")
    for nombre, fig in figs.items():
        fig.savefig(out / nombre, dpi=110, bbox_inches="tight")
    (out / "resultados.xlsx").write_bytes(a_excel(S, res, P))
    print(f"\nGráficos y Excel guardados en: {out.resolve()}")


if __name__ == "__main__":
    main()
