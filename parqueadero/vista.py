"""
Sistema visual de la interfaz: estilos, encabezado, banners de sección, paneles, tarjetas de indicadores,
insignias de estado, recomendaciones y el calendario del mes.

Criterios de diseño
-------------------
* Color con calma: cada pestaña tiene un tono propio (índigo, azul, verde azulado, violeta, ámbar, pizarra),
  todos de saturación media y con su versión «suave» para fondos y «oscura» para texto
  (contraste del texto ≥ 5,5:1, verificado). Nada de blanco ni negro puros.
* El tono identifica la sección; los colores de estado (bien / atención / crítico) se reservan para el
  estado y siempre van con icono + texto.
* Organización: cada pestaña abre con un banner y su contenido va en paneles con cabecera
  (icono + título + descripción). Los paneles son contenedores de Streamlit con key «panel-<tono>-…»,
  que el CSS reconoce por la clase st-key-panel-….
"""
from __future__ import annotations

import html

from . import calendario as cal

# tono: (principal, suave, oscuro)
TONOS_SECCION = {
    "indigo": ("#4F5FD0", "#ECEEFB", "#34409A"),
    "azul": ("#2F6DB5", "#E7EFF9", "#1D4E85"),
    "teal": ("#1E8C7E", "#E2F3F0", "#12625A"),
    "violeta": ("#7457C9", "#EFEAFA", "#4F3796"),
    "ambar": ("#C98213", "#FBF1DE", "#8A5605"),
    "coral": ("#C9573F", "#FBEAE5", "#94382A"),
    "pizarra": ("#52657E", "#EBEFF4", "#33445A"),
}

TONOS = {  # estados: fondo suave, texto, icono
    "bien": ("#E3F3E5", "#1B6B2A", "✓"),
    "atencion": ("#FBF0D6", "#7A5000", "!"),
    "critico": ("#FBE5E3", "#A12A2A", "✕"),
    "neutro": ("#ECEFF3", "#4A5565", "•"),
    "info": ("#E7EFF9", "#1D4E85", "i"),
}


def _vars_tono(nombre: str) -> str:
    p, s, o = TONOS_SECCION[nombre]
    return f"--t:{p};--t-suave:{s};--t-osc:{o};"


_CSS_TONOS = "\n".join(
    f'div[class*="st-key-panel-{n}"],.tono-{n}{{{_vars_tono(n)}}}' for n in TONOS_SECCION)

# color de cada pestaña en su orden: Inicio, Calendario, Resultados, Por hora, Riesgo, Modelo
_ORDEN_TABS = ["indigo", "azul", "teal", "violeta", "ambar", "pizarra"]
_CSS_TABS = "\n".join(
    f'[data-testid="stTab"]:nth-child({i + 1}){{{_vars_tono(n)}}}' for i, n in enumerate(_ORDEN_TABS))

ESTILOS = """
<style>
:root{
  --tinta:#1E2733;--tinta-2:#4A5565;--tinta-3:#6B7585;
  --sup:#FCFCFD;--fondo:#F2F4F7;--sup-2:#EEF1F5;--borde:#DFE4EB;--borde-2:#CDD5DF;
  --sombra:0 1px 2px rgba(30,39,51,.05),0 2px 10px rgba(30,39,51,.04);
  --sombra-2:0 4px 10px rgba(30,39,51,.07),0 14px 32px rgba(30,39,51,.08);
  --t:#2F6DB5;--t-suave:#E7EFF9;--t-osc:#1D4E85;
}
""" + _CSS_TONOS + "\n" + _CSS_TABS + """
html,body,[class*="st-"]{-webkit-font-smoothing:antialiased}
.block-container{padding-top:3.6rem;padding-bottom:4rem;max-width:1340px}
[data-testid="stHeader"]{background:rgba(242,244,247,.85);backdrop-filter:blur(8px)}
h1,h2,h3,h4{color:var(--tinta);letter-spacing:-.015em}
p,li{line-height:1.55}
.mi{font-family:"Material Symbols Rounded";font-weight:400;font-style:normal;font-size:20px;line-height:1;letter-spacing:normal;
  text-transform:none;display:inline-block;white-space:nowrap;direction:ltr;-webkit-font-feature-settings:"liga";
  font-feature-settings:"liga";-webkit-font-smoothing:antialiased;user-select:none}

/* ================= barra lateral ================= */
[data-testid="stSidebar"]{border-right:1px solid var(--borde);background:linear-gradient(180deg,#EEF2F8 0%,#F6F7FA 220px)}
[data-testid="stSidebar"] [data-testid="stSidebarContent"]{padding-top:.2rem}
[data-testid="stSidebar"] [data-testid="stExpander"] details{background:var(--sup);border-color:var(--borde)}
[data-testid="stSidebar"] [data-testid="stExpander"] summary p{font-weight:600;font-size:.9rem}
[data-testid="stSidebar"] [data-testid="stExpander"] summary span[data-testid="stIconMaterial"]{color:#2F6DB5}
.lado-cab{display:flex;align-items:center;gap:10px;margin:2px 0 6px}
.lado-cab .ico{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,#2F6DB5,#4F5FD0);color:#fff;
  display:flex;align-items:center;justify-content:center;box-shadow:0 3px 8px rgba(47,109,181,.28)}
.lado-cab .ico .mi{font-size:19px}
.lado-cab b{font-size:1.02rem;color:var(--tinta)}
.lado-cab small{display:block;color:var(--tinta-3);font-size:.76rem;font-weight:500}
.lado-grupo{display:flex;align-items:center;gap:7px;font-size:.7rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:var(--t-osc);margin:16px 0 6px}
.lado-grupo::after{content:"";flex:1;height:1px;background:var(--borde)}
.lado-grupo .mi{font-size:16px;color:var(--t)}

/* ================= encabezado ================= */
.hero{position:relative;overflow:hidden;border-radius:22px;padding:22px 26px 20px;margin-bottom:16px;color:#fff;
  background:linear-gradient(118deg,#1B3350 0%,#245A84 55%,#1E7B72 120%);box-shadow:0 10px 28px rgba(27,51,80,.20)}
.hero::before,.hero::after{content:"";position:absolute;border-radius:50%;pointer-events:none}
.hero::before{width:340px;height:340px;right:-90px;top:-170px;background:radial-gradient(circle,rgba(255,255,255,.13),rgba(255,255,255,0) 70%)}
.hero::after{width:260px;height:260px;right:220px;bottom:-190px;background:radial-gradient(circle,rgba(120,200,190,.22),rgba(255,255,255,0) 70%)}
.hero .fila{display:flex;align-items:center;gap:16px;position:relative;z-index:1}
.hero .logo{flex:0 0 auto;width:52px;height:52px;border-radius:15px;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.28);
  display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.55rem;color:#fff;backdrop-filter:blur(4px)}
.hero h1{color:#fff;font-size:1.42rem;margin:0;padding:0;font-weight:700;line-height:1.2}
.hero .sub{color:#CFDDEB;font-size:.9rem;margin-top:3px}
.hero .chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px;position:relative;z-index:1}
.hero .chip{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.20);
  color:#DCE7F3;border-radius:999px;padding:5px 12px;font-size:.8rem;white-space:nowrap}
.hero .chip b{color:#fff;font-weight:650}
.hero .chip .mi{font-size:16px;color:#9FC3E6}
.hero .estado-ok{background:rgba(120,214,160,.16);border-color:rgba(140,224,170,.45);color:#DFF7E8}
.hero .estado-ok .mi{color:#8EE0AE}

/* ================= pestañas (cada una con su tono) ================= */
[data-testid="stTabs"] [role="tablist"],.stTabs [data-baseweb="tab-list"]{gap:4px;background:var(--sup);padding:6px;border-radius:14px;
  border:1px solid var(--borde);overflow-x:auto;box-shadow:var(--sombra)}
[data-testid="stTabs"] [role="tablist"]::before,[data-testid="stTabs"] [role="tablist"]::after{display:none}
[data-testid="stTab"]{min-height:42px;padding:0 16px;border-radius:10px;color:var(--tinta-2);background:transparent;
  transition:background .15s,color .15s,box-shadow .15s;white-space:nowrap;display:flex;align-items:center;cursor:pointer;border:none;margin:0}
[data-testid="stTab"] p{font-weight:600;font-size:.92rem;margin:0}
[data-testid="stTab"] [role="img"]{color:var(--t);font-size:1.15rem!important;margin-right:2px}
[data-testid="stTab"]:hover{background:var(--t-suave)}
[data-testid="stTab"][aria-selected="true"]{background:var(--t-suave)!important;box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--t) 28%,transparent)}
[data-testid="stTab"][aria-selected="true"] p{color:var(--t-osc)}
[data-testid="stTabs"] .react-aria-SelectionIndicator,.stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none}
[data-testid="stTabs"] [role="tabpanel"]{padding-top:1rem}

/* ================= banner de cada pestaña ================= */
.banner{display:flex;align-items:center;gap:16px;border-radius:18px;padding:18px 22px;margin:2px 0 6px;
  background:linear-gradient(100deg,var(--t-suave) 0%,var(--sup) 78%);border:1px solid color-mix(in srgb,var(--t) 22%,var(--borde))}
.banner .ico{flex:0 0 auto;width:48px;height:48px;border-radius:14px;background:var(--t);color:#fff;display:flex;align-items:center;
  justify-content:center;box-shadow:0 6px 14px color-mix(in srgb,var(--t) 30%,transparent)}
.banner .ico .mi{font-size:26px}
.banner h2{font-size:1.3rem;margin:0;padding:0;font-weight:700;color:var(--tinta)}
.banner p{margin:2px 0 0;color:var(--tinta-2);font-size:.9rem;line-height:1.45}
.banner .extra{margin-left:auto;display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end}
.banner .pill{background:var(--sup);border:1px solid var(--borde);color:var(--tinta-2);border-radius:999px;padding:4px 11px;font-size:.78rem;white-space:nowrap}
.banner .pill b{color:var(--t-osc)}

/* ================= paneles ================= */
div[class*="st-key-panel-"]{background:var(--sup);border:1px solid var(--borde);border-radius:18px;padding:16px 20px 18px;
  box-shadow:var(--sombra);position:relative;overflow:hidden;margin-top:6px}
div[class*="st-key-panel-"]::before{content:"";position:absolute;left:0;top:0;right:0;height:4px;
  background:linear-gradient(90deg,var(--t),color-mix(in srgb,var(--t) 35%,transparent))}
.ph{display:flex;align-items:center;gap:12px;margin:2px 0 2px}
.ph .ico{flex:0 0 auto;width:38px;height:38px;border-radius:11px;background:var(--t-suave);color:var(--t-osc);display:flex;
  align-items:center;justify-content:center}
.ph .t{font-size:1.04rem;font-weight:700;color:var(--tinta);letter-spacing:-.01em;line-height:1.25}
.ph .n{font-size:.84rem;color:var(--tinta-3);line-height:1.45;margin-top:1px}
div[class*="st-key-panel-"] [data-testid="stVegaLiteChart"],div[class*="st-key-panel-"] [data-testid="stArrowVegaLiteChart"]{
  box-shadow:none;background:var(--sup);border:1px solid var(--sup-2)}
div[class*="st-key-panel-"] [data-testid="stExpander"] details{background:#F8F9FB}
.sub-t{font-size:.72rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--t-osc);margin:6px 0 4px;
  display:flex;align-items:center;gap:6px}
.sub-t::before{content:"";width:8px;height:8px;border-radius:3px;background:var(--t)}

/* ================= controles ================= */
.stButton button,.stDownloadButton button{border-radius:11px;font-weight:600;transition:transform .08s,box-shadow .15s}
.stButton button:active,.stDownloadButton button:active{transform:translateY(1px)}
.stButton button[kind="primary"],.stDownloadButton button[kind="primary"]{background:linear-gradient(135deg,#2F6DB5,#3F63C9);border:none;
  box-shadow:0 2px 4px rgba(47,109,181,.25),0 6px 16px rgba(47,109,181,.22)}
.stButton button[kind="primary"]:hover,.stDownloadButton button[kind="primary"]:hover{background:linear-gradient(135deg,#285F9F,#3656B3)}
[data-testid="stExpander"] details{border-radius:12px;border-color:var(--borde);background:var(--sup)}
[data-testid="stExpander"] summary:hover{color:var(--t-osc)}
[data-testid="stVegaLiteChart"],[data-testid="stArrowVegaLiteChart"]{background:var(--sup);border:1px solid var(--borde);
  border-radius:14px;box-shadow:var(--sombra);overflow:hidden}
[data-testid="stDataFrame"]{border-radius:12px;overflow:hidden}
[data-testid="stCaptionContainer"]{color:var(--tinta-3)}
.nota{color:var(--tinta-3);font-size:.86rem;line-height:1.5}
.nota b{color:var(--tinta-2)}

/* ================= insignias ================= */
.badge{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:2px 9px 2px 6px;font-size:.74rem;font-weight:650;
  line-height:1.5;white-space:nowrap}
.badge i{font-style:normal;display:inline-flex;width:15px;height:15px;border-radius:50%;align-items:center;justify-content:center;
  font-size:.6rem;font-weight:800;background:currentColor}
.badge i span{color:#fff}

/* ================= tarjetas de indicadores ================= */
.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(238px,100%),1fr));gap:12px;margin:4px 0 2px}
.kpi{position:relative;background:var(--sup);border:1px solid var(--borde);border-radius:15px;padding:14px 15px 13px;
  display:flex;flex-direction:column;gap:6px;transition:box-shadow .18s,transform .18s,border-color .18s;min-width:0;overflow:hidden}
.kpi::after{content:"";position:absolute;inset:auto 0 0 0;height:3px;background:var(--t);opacity:.55}
.kpi:hover{box-shadow:var(--sombra-2);transform:translateY(-2px);border-color:color-mix(in srgb,var(--t) 35%,var(--borde))}
.kpi-top{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:2px}
.kpi-ico{flex:0 0 auto;width:32px;height:32px;border-radius:10px;background:var(--t-suave);color:var(--t-osc);display:flex;align-items:center;justify-content:center}
.kpi-ico .mi{font-size:18px}
.kpi-l{font-size:.8rem;font-weight:600;color:var(--tinta-2);line-height:1.3}
.kpi-v{font-size:1.58rem;font-weight:700;color:var(--tinta);line-height:1.15;letter-spacing:-.02em;overflow-wrap:anywhere}
.kpi-v.txt{font-size:1.12rem;line-height:1.3}
.kpi-n{font-size:.78rem;color:var(--tinta-3);line-height:1.4}
.kpi.destacado{background:linear-gradient(160deg,var(--t-suave) 0%,var(--sup) 65%);border-color:color-mix(in srgb,var(--t) 30%,var(--borde))}
.kpi.destacado::after{opacity:1}

/* ================= recomendaciones ================= */
.recs{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(310px,100%),1fr));gap:10px}
.rec{display:flex;gap:12px;align-items:flex-start;background:var(--t-suave);border:1px solid color-mix(in srgb,var(--t) 20%,transparent);
  border-radius:13px;padding:12px 14px;font-size:.89rem;line-height:1.5;color:var(--tinta)}
.rec .n{flex:0 0 auto;width:28px;height:28px;border-radius:9px;background:var(--sup);color:var(--t-osc);display:flex;align-items:center;
  justify-content:center;box-shadow:0 1px 2px rgba(30,39,51,.08)}
.rec .n .mi{font-size:17px}

/* ================= inicio ================= */
.pasos{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr));gap:12px;margin-top:4px}
.paso{background:linear-gradient(170deg,var(--t-suave) 0%,var(--sup) 60%);border:1px solid color-mix(in srgb,var(--t) 22%,var(--borde));
  border-radius:16px;padding:16px 18px;position:relative}
.paso .cab{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.paso .ico{width:40px;height:40px;border-radius:12px;background:var(--t);color:#fff;display:flex;align-items:center;justify-content:center}
.paso .num{font-size:1.9rem;font-weight:800;color:color-mix(in srgb,var(--t) 22%,transparent);line-height:1}
.paso > b{display:block;margin-bottom:4px;color:var(--tinta);font-size:.98rem}
.paso > span{display:block;color:var(--tinta-2);font-size:.87rem;line-height:1.5}
.paso > span b{color:var(--tinta);font-weight:600}
.flujo{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(170px,100%),1fr));gap:10px;margin:4px 0 10px;counter-reset:f}
.flujo .f{background:var(--sup);border:1px solid var(--borde);border-left:4px solid var(--t);border-radius:12px;padding:11px 13px;
  font-size:.89rem;color:var(--tinta);font-weight:600}
.flujo .f::before{counter-increment:f;content:"PASO " counter(f);display:block;font-size:.66rem;font-weight:700;color:var(--t-osc);
  letter-spacing:.08em;margin-bottom:3px}
.flujo .f span{display:block;color:var(--tinta-3);font-size:.8rem;margin-top:3px;line-height:1.4;font-weight:400}
.glosario{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(290px,100%),1fr));gap:8px}
.glosario div{background:#F8F9FB;border:1px solid var(--borde);border-radius:12px;padding:10px 14px;font-size:.86rem;line-height:1.5;color:var(--tinta-2)}
.glosario b{color:var(--t-osc);display:block;font-size:.88rem;margin-bottom:1px}

/* ================= estado vacío ================= */
.vacio{background:var(--sup);border:1.5px dashed var(--borde-2);border-radius:20px;padding:46px 24px;text-align:center;color:var(--tinta-3)}
.vacio .ico{width:60px;height:60px;margin:0 auto 14px;border-radius:18px;background:var(--t-suave);color:var(--t-osc);display:flex;
  align-items:center;justify-content:center}
.vacio .ico .mi{font-size:30px}
.vacio b{color:var(--tinta);font-size:1.1rem;display:block;margin-bottom:6px}

/* ================= panel de control del calendario ================= */
.paso-ctrl{display:flex;align-items:center;gap:10px;margin:4px 0 6px}
.paso-ctrl .n{flex:0 0 auto;width:26px;height:26px;border-radius:50%;background:var(--t);color:#fff;font-weight:700;font-size:.8rem;
  display:flex;align-items:center;justify-content:center}
.paso-ctrl b{font-size:.92rem;color:var(--tinta)}
.paso-ctrl small{display:block;color:var(--tinta-3);font-size:.76rem}
.resumen-sel{background:linear-gradient(135deg,var(--t-suave),#F6F8FB);border:1px solid color-mix(in srgb,var(--t) 22%,var(--borde));
  border-radius:13px;padding:11px 13px;margin:2px 0 4px}
.resumen-sel .grande{font-size:1.6rem;font-weight:750;color:var(--t-osc);letter-spacing:-.02em;line-height:1.1}
.resumen-sel .grande small{font-size:.85rem;font-weight:600;color:var(--tinta-2);margin-left:5px;letter-spacing:0}
.resumen-sel .chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.resumen-sel .chip{background:var(--sup);border:1px solid var(--borde);border-radius:999px;padding:2px 9px;font-size:.75rem;color:var(--tinta-2)}
.resumen-sel .chip b{color:var(--tinta)}
.listo{display:block;line-height:1.5;font-size:.84rem;color:#1B6B2A;background:#E3F3E5;border:1px solid #C5E6CB;border-radius:11px;padding:9px 12px;margin:8px 0}

/* ================= calendario ================= */
.cal{border-collapse:separate;border-spacing:5px;width:100%;table-layout:fixed;font-family:inherit}
.cal th{font-size:.7rem;color:var(--tinta-3);font-weight:700;letter-spacing:.07em;text-transform:uppercase;padding:2px 0 4px}
.cal th.fs{color:#94382A}
.cal td{vertical-align:top;height:88px;border-radius:12px;padding:7px 8px;font-size:11px;border:1px solid var(--borde);
  background:var(--sup);position:relative;transition:box-shadow .15s,border-color .15s,transform .15s}
.cal td:not(.fuera):hover{border-color:#9DBBE0;box-shadow:var(--sombra-2);transform:translateY(-1px);z-index:2}
.cal td.fuera{background:transparent;border:1px dashed var(--borde)}
.cal td.finde:not(.sel):not(.fuera){background:#FAF7F5}
.cal td.sel{box-shadow:inset 0 0 0 1.5px #7FA6D8;background:#F1F6FC;border-color:transparent}
.cal td.sel .num::after{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;background:#2F6DB5;margin-left:6px;vertical-align:middle}
.cal .num{font-size:15px;font-weight:700;color:var(--tinta)}
.cal td.fuera .num{color:#BCC4CF;font-weight:500}
.cal .fest{color:#A12A2A;font-weight:600;font-size:10.5px;line-height:1.25;margin-top:3px;overflow:hidden;display:-webkit-box;
  -webkit-line-clamp:2;-webkit-box-orient:vertical}
.cal .evento{color:#7A5000}
.cal .chip-t{display:inline-block;border-radius:999px;padding:1px 7px;font-size:10px;font-weight:600;margin-top:4px}
.cal .Alta{background:#FBEAE5;color:#94382A}.cal .Media{background:#E7EFF9;color:#1D4E85}.cal .Baja{background:#EBEFF4;color:#33445A}
.cal .q{position:absolute;top:7px;right:8px;font-size:10px;font-weight:700;color:#7A5000;background:#FBF0D6;border-radius:6px;padding:0 5px}
.cal .val{font-size:13px;font-weight:700;margin-top:4px;color:var(--tinta)}
.leyenda{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.78rem;color:var(--tinta-3);margin:8px 6px 2px}
.leyenda i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.escala{display:flex;align-items:center;gap:8px;font-size:.76rem;color:var(--tinta-3);margin:4px 6px}
.escala .barra{flex:0 0 140px;height:8px;border-radius:99px}

/* ================= adaptación a pantallas ================= */
img,svg,canvas{max-width:100%}
.hero .chip,.banner .pill{white-space:normal}
[data-testid="stTabs"] [role="tablist"]{scrollbar-width:thin;-webkit-overflow-scrolling:touch}
/* fila de navegación del mes: siempre horizontal (Streamlit apila las columnas en pantallas angostas) */
.st-key-nav-cal [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:.4rem!important}
.st-key-nav-cal [data-testid="stColumn"]{min-width:0!important;width:auto!important}
.st-key-nav-cal [data-testid="stColumn"]:nth-child(1),.st-key-nav-cal [data-testid="stColumn"]:nth-child(4){flex:0 0 46px!important}
.st-key-nav-cal [data-testid="stColumn"]:nth-child(2){flex:1.5 1 0!important}
.st-key-nav-cal [data-testid="stColumn"]:nth-child(3){flex:1 1 0!important}
.st-key-nav-cal button{padding-left:0;padding-right:0}
.st-key-nav-cal button p{display:none}   /* solo la flecha; el nombre queda como ayuda */

/* portátil pequeño / tablet horizontal */
@media (max-width: 1100px){
  .block-container{padding-left:1.4rem;padding-right:1.4rem}
  .cal td{height:78px}
  .banner .extra{max-width:45%}
}
/* tablet vertical */
@media (max-width: 820px){
  .block-container{padding:3.4rem 1rem 3rem}
  .hero{padding:18px 18px 16px;border-radius:18px}
  .hero::after{display:none}
  .hero h1{font-size:1.2rem}
  .hero .logo{width:44px;height:44px;font-size:1.3rem;border-radius:13px}
  .banner{flex-wrap:wrap;padding:14px 16px;gap:12px}
  .banner .extra{margin-left:0;max-width:none;width:100%;justify-content:flex-start}
  .banner h2{font-size:1.12rem}
  div[class*="st-key-panel-"]{padding:14px 14px 16px;border-radius:16px}
  [data-testid="stTab"]{padding:0 12px;min-height:38px}
  [data-testid="stTab"] p{font-size:.86rem}
  .kpi-v{font-size:1.4rem}
  .cal{border-spacing:3px}
  .cal td{height:64px;padding:5px 6px;border-radius:9px}
  .cal .chip-t,.cal .fest{display:none}
  .cal .num{font-size:14px}
}
/* celular */
@media (max-width: 520px){
  .block-container{padding:3.2rem .7rem 2.5rem}
  .hero{padding:14px 14px 12px;margin-bottom:12px}
  .hero .fila{gap:12px}
  .hero h1{font-size:1.06rem}
  .hero .sub{font-size:.8rem}
  .hero .logo{width:38px;height:38px;font-size:1.1rem}
  .hero .chips{gap:6px;margin-top:12px}
  .hero .chip{font-size:.72rem;padding:4px 10px}
  .banner .ico{width:40px;height:40px;border-radius:12px}
  .banner .ico .mi{font-size:22px}
  .banner p{font-size:.84rem}
  div[class*="st-key-panel-"]{padding:12px 11px 14px}
  .ph .ico{width:32px;height:32px;border-radius:9px}
  .ph .t{font-size:.98rem}
  .kpi{padding:12px 13px}
  .kpi-v{font-size:1.3rem}
  .paso{padding:14px}
  .paso .num{font-size:1.4rem}
  .cal{border-spacing:2px}
  .cal th{font-size:.62rem;letter-spacing:.02em}
  .cal td{height:46px;padding:4px;border-radius:7px}
  .cal .num{font-size:12.5px}
  .cal td.sel .num::after{display:none}
  .cal .q{top:3px;right:3px;font-size:8.5px;padding:0 3px}
  .cal .val{font-size:10.5px;margin-top:2px}
  .leyenda{font-size:.72rem;gap:4px 10px;margin:6px 2px 2px}
  .leyenda span:last-child{display:none}
  .resumen-sel .grande{font-size:1.35rem}
}
</style>
"""


def _e(t) -> str:
    return html.escape(str(t))


def icono(nombre: str) -> str:
    """Icono de Material Symbols (la fuente ya la carga Streamlit)."""
    return f'<span class="mi">{nombre}</span>'


def badge(texto: str, tono: str = "neutro") -> str:
    """Insignia de estado: siempre icono + texto (el color nunca va solo)."""
    fondo, color, ico = TONOS.get(tono, TONOS["neutro"])
    return (f'<span class="badge" style="background:{fondo};color:{color}"><i><span>{ico}</span></i>'
            f'<span style="color:{color}">{_e(texto)}</span></span>')


def encabezado(titulo: str, subtitulo: str, chips: list[tuple[str, str]], estado: tuple[str, bool]) -> str:
    """chips: (icono, html); estado: (texto, listo)."""
    cs = "".join(f'<span class="chip">{icono(i)}{c}</span>' for i, c in chips)
    texto, listo = estado
    cs += (f'<span class="chip {"estado-ok" if listo else ""}">{icono("check_circle" if listo else "pending")}{_e(texto)}</span>')
    return (f'<div class="hero"><div class="fila"><div class="logo">P</div><div><h1>{_e(titulo)}</h1>'
            f'<div class="sub">{_e(subtitulo)}</div></div></div><div class="chips">{cs}</div></div>')


def banner(titulo: str, texto: str, icono_: str, tono: str, pills: list[str] | None = None) -> str:
    extra = "".join(f'<span class="pill">{p}</span>' for p in (pills or []))
    return (f'<div class="banner tono-{tono}"><div class="ico">{icono(icono_)}</div><div><h2>{_e(titulo)}</h2><p>{texto}</p></div>'
            + (f'<div class="extra">{extra}</div>' if extra else "") + "</div>")


def panel_cabecera(titulo: str, nota: str = "", icono_: str = "dashboard") -> str:
    return (f'<div class="ph"><div class="ico">{icono(icono_)}</div><div><div class="t">{_e(titulo)}</div>'
            + (f'<div class="n">{nota}</div>' if nota else "") + "</div></div>")


def subtitulo(texto: str) -> str:
    return f'<div class="sub-t">{_e(texto)}</div>'


def kpi(etiqueta, valor, nota="", estado=None, icono_="insights", tono="azul", destacado=False) -> dict:
    return dict(etiqueta=etiqueta, valor=valor, nota=nota, estado=estado, icono=icono_, tono=tono, destacado=destacado)


def tarjetas(items: list[dict]) -> str:
    partes = []
    for k in items:
        clase_v = "kpi-v txt" if len(str(k["valor"])) > 15 else "kpi-v"
        b = badge(*k["estado"]) if k.get("estado") else ""
        partes.append(
            f'<div class="kpi tono-{k.get("tono", "azul")}{" destacado" if k.get("destacado") else ""}">'
            f'<div class="kpi-top"><div class="kpi-ico">{icono(k.get("icono", "insights"))}</div>{b}</div>'
            f'<span class="kpi-l">{_e(k["etiqueta"])}</span>'
            f'<div class="{clase_v}">{_e(k["valor"])}</div><div class="kpi-n">{_e(k.get("nota", ""))}</div></div>')
    return '<div class="kpis">' + "".join(partes) + "</div>"


def recomendaciones(textos: list[str]) -> str:
    """Cada recomendación con un icono según su tema y el tono de su tema."""
    def tema(t: str):
        t = t.lower()
        if "externo" in t:
            return "add_business", "teal"
        if "muelle" in t:
            return "local_shipping", "violeta"
        if "espera" in t:
            return "hourglass_top", "coral"
        if "personal" in t or "horas pico" in t:
            return "groups", "azul"
        if "lleno" in t or "carros" in t:
            return "local_parking", "ambar"
        return "lightbulb", "ambar"
    partes = []
    for t in textos:
        ic, tono = tema(t)
        partes.append(f'<div class="rec tono-{tono}"><div class="n">{icono(ic)}</div><div>{_e(t)}</div></div>')
    return '<div class="recs">' + "".join(partes) + "</div>"


def vacio(titulo: str, texto: str, icono_: str = "play_circle", tono: str = "azul") -> str:
    return f'<div class="vacio tono-{tono}"><div class="ico">{icono(icono_)}</div><b>{_e(titulo)}</b>{texto}</div>'


def paso_ctrl(n: int, titulo: str, nota: str = "") -> str:
    return (f'<div class="paso-ctrl"><div class="n">{n}</div><div><b>{_e(titulo)}</b>'
            + (f"<small>{_e(nota)}</small>" if nota else "") + "</div></div>")


def _mezcla(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    t = min(1.0, max(0.0, t))
    return "#" + "".join(f"{int(a[i] + (b[i] - a[i]) * t):02x}" for i in range(3))


# Escalas de un solo tono para colorear el calendario (claro → medio, el texto sigue legible encima)
CAL_AZUL, CAL_NARANJA = ("#FCFCFD", "#8DB9EE"), ("#FCFCFD", "#F2AE8C")


def calendario_html(anio: int, mes: int, seleccion: set, factores_mes=None, factores_eventos=None, factor_puente=1.0,
                    valores: dict | None = None, formato="{:.0f}", rojo=False) -> str:
    semanas = cal.semanas_del_mes(anio, mes)
    vmax = max(valores.values()) if valores else 0
    c0, c1 = CAL_NARANJA if rojo else CAL_AZUL
    filas = []
    for sem in semanas:
        celdas = []
        for f in sem:
            if f.month != mes:
                celdas.append(f'<td class="fuera"><div class="num">{f.day}</div></td>')
                continue
            info = cal.clasificar(f, factores_mes, factores_eventos, factor_puente)
            clases = []
            if f in seleccion:
                clases.append("sel")
            if f.weekday() >= 5:
                clases.append("finde")
            estilo = ""
            titulo = [f"{cal.DIA_SEMANA[f.weekday()]} {f:%d/%m/%Y}", cal.TIPO_NOMBRE[info.tipo]]
            contenido = [f'<div class="num">{f.day}</div>']
            if info.quincena:
                contenido.append('<span class="q">Q</span>')
                titulo.append("Quincena")
            if info.festivo:
                contenido.append(f'<div class="fest">{_e(info.festivo["nombre"])}</div>')
                titulo.append(f"Festivo: {info.festivo['nombre']}")
            elif info.eventos:
                contenido.append(f'<div class="fest evento">{_e(info.eventos[0].nombre)}</div>')
            if info.eventos:
                titulo.append("Evento: " + ", ".join(e.nombre for e in info.eventos))
            contenido.append(f'<span class="chip-t {info.temporada}">{info.temporada} ×{info.factor_temporada:.2f}</span>')
            titulo.append(f"Temporada {info.temporada.lower()} (factor {info.factor_temporada:.2f})")
            if valores is not None and f in valores:
                t = valores[f] / vmax if vmax else 0
                estilo = f' style="background:{_mezcla(c0, c1, t)}"'
                contenido.append(f'<div class="val">{formato.format(valores[f])}</div>')
                titulo.append(f"Resultado: {formato.format(valores[f])}")
            titulo.append("Seleccionado" if f in seleccion else "No seleccionado")
            celdas.append(f'<td class="{" ".join(clases)}"{estilo} title="{_e(" · ".join(titulo))}">{"".join(contenido)}</td>')
        filas.append("<tr>" + "".join(celdas) + "</tr>")
    cab = "".join(f'<th class="{"fs" if i >= 5 else ""}">{d}</th>' for i, d in enumerate(["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]))
    escala = ""
    if valores:
        escala = (f'<div class="escala">Menor<span class="barra" style="background:linear-gradient(90deg,{c0},{c1});'
                  f'border:1px solid var(--borde)"></span>Mayor</div>')
    return f'<table class="cal"><tr>{cab}</tr>{"".join(filas)}</table>{escala}{LEYENDA}'


LEYENDA = ('<div class="leyenda">'
           '<span><i style="background:#F1F6FC;box-shadow:inset 0 0 0 2px #7FA6D8"></i>Seleccionado</span>'
           '<span><i style="background:#A12A2A"></i>Festivo</span>'
           '<span><i style="background:#FBF0D6"></i>Q = quincena</span>'
           '<span><i style="background:#FBEAE5"></i>Temporada alta</span>'
           '<span><i style="background:#E7EFF9"></i>Media</span>'
           '<span><i style="background:#EBEFF4"></i>Baja</span>'
           '<span>Pasa el cursor sobre un día para ver su detalle</span></div>')
