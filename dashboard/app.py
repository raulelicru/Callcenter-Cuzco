"""
Reportes Diarios — Campana GRAL (VICIdial)
streamlit run dashboard/app.py

Sube los archivos del dia, la app guarda la informacion y genera:
  1. Tablero de Contactabilidad
  2. Control de Recontacto
  3. Tipificacion de Gestion
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datetime import datetime

import streamlit as st

from vicidial_reports import generar_reportes_diarios, export_report_excel, jornada_label

# ── Config de pagina ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Reportes GRAL | Call Center Cuzco",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.stApp { background-color: #0f1117; }
[data-testid="stDataFrame"] { border: 1px solid #2a3045; border-radius: 8px; }
hr { border-color: #2a3045; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# CABECERA
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("# Reportes Diarios — Campana GRAL")
st.markdown(
    "Sube los **6 archivos del dia** (3 frescos de VICIdial + 3 tableros de ayer) "
    "y genera el **Tablero de Contactabilidad**, **Control de Recontacto** y "
    "**Tipificacion de Gestion** con su resumen de tendencia y alertas."
)
st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# 1. FECHA Y ARCHIVOS FRESCOS DE VICIDIAL
# ─────────────────────────────────────────────────────────────────────────────

fecha = st.date_input("Fecha del reporte", value=datetime.now().date(), format="DD/MM/YYYY")
if fecha.weekday() == 5:
    st.info(
        "Es **sabado** — se aplica la regla de media jornada (8:00-12:00) "
        "y la comparacion sera sabado contra sabado."
    )

st.markdown("### 1. Archivos frescos de VICIdial (jornada del dia)")
c1, c2, c3 = st.columns(3)
with c1:
    f_amd = st.file_uploader("AST_AMD_log_report (.csv)", type=["csv", "txt"], key="f_amd")
with c2:
    f_vdad = st.file_uploader("AST_VDADstats (.csv)", type=["csv", "txt"], key="f_vdad")
with c3:
    f_export = st.file_uploader(
        "EXPORT_CALL_REPORT — Estados = ALL (.txt/.csv)  ⭐ insumo principal",
        type=["txt", "csv"], key="f_export",
    )

st.markdown("### 2. Tableros de salida del dia anterior (los que regresaste)")
c4, c5, c6 = st.columns(3)
with c4:
    f_tab_ayer = st.file_uploader("Tablero_Contactabilidad_GRAL (.xlsx)", type=["xlsx", "xls"], key="f_tab_ayer")
with c5:
    f_recon_ayer = st.file_uploader("Control_Recontacto_GRAL (.xlsx)", type=["xlsx", "xls"], key="f_recon_ayer")
with c6:
    f_tipif_ayer = st.file_uploader("Tipificacion_Gestion_GRAL (.xlsx)", type=["xlsx", "xls"], key="f_tipif_ayer")

with st.expander("Reglas que se aplican a estos reportes"):
    st.markdown("""
- **Promesa de pago** = status `04` + `21` (siempre se suman ambos).
- **Status `01`** = cuelga en saludo (rechazo temprano) — no cuenta como gestion.
- **Segmentacion de humanos** = status `01, 02, 04, 09, 14, 18, 19, 21`, con hoja **Por Entidad** (evasion y cuelgue por estado).
- **Sabado** = media jornada (8 AM-12 PM); se compara sabado contra sabado, no contra dia completo.
- El dia nuevo se **agrega al acumulado** de cada reporte leyendo el historico de los tableros del dia anterior.
- **Monto comprometido** sale del campo reutilizado `postal_code`; **estado del deudor** del campo reutilizado `first_name`.
    """)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# 3. GENERAR
# ─────────────────────────────────────────────────────────────────────────────

if st.button("GENERAR LOS 3 REPORTES", type="primary", use_container_width=True):
    if f_export is None:
        st.error("Falta el **EXPORT_CALL_REPORT (Estados = ALL)** — es el insumo principal y obligatorio.")
    else:
        try:
            resultado = generar_reportes_diarios(
                export_call_report=f_export,
                fecha=fecha,
                amd_log=f_amd,
                vdad_stats=f_vdad,
                tablero_contactabilidad_ayer=f_tab_ayer,
                control_recontacto_ayer=f_recon_ayer,
                tipificacion_gestion_ayer=f_tipif_ayer,
            )
        except Exception as e:
            st.error(f"Error al generar los reportes: {e}")
            import traceback
            st.code(traceback.format_exc())
        else:
            st.session_state["reportes_gral"] = resultado
            st.session_state["reportes_gral_fecha"] = fecha
            st.success(f"Reportes generados para el {fecha.strftime('%d/%m/%Y')} ({jornada_label(fecha)}).")

# ─────────────────────────────────────────────────────────────────────────────
# 4. RESULTADOS
# ─────────────────────────────────────────────────────────────────────────────

resultado = st.session_state.get("reportes_gral")
if resultado:
    fecha_gen = st.session_state.get("reportes_gral_fecha", fecha)
    sufijo = fecha_gen.strftime("%Y%m%d")

    st.divider()
    st.markdown("## Resumen de tendencia y alertas")
    st.markdown(resultado["resumen_md"])

    st.divider()
    st.markdown("## Reportes generados")

    tabs = st.tabs(["Tablero de Contactabilidad", "Control de Recontacto", "Tipificacion de Gestion"])
    specs = [
        ("contactabilidad", f"Tablero_Contactabilidad_GRAL_{sufijo}.xlsx"),
        ("recontacto",      f"Control_Recontacto_GRAL_{sufijo}.xlsx"),
        ("tipificacion",    f"Tipificacion_Gestion_GRAL_{sufijo}.xlsx"),
    ]
    for tab, (key, fname) in zip(tabs, specs):
        with tab:
            sheets = resultado[key]
            hoja_sel = st.selectbox("Hoja", list(sheets.keys()), key=f"hoja_{key}")
            st.dataframe(sheets[hoja_sel], use_container_width=True, hide_index=True)
            st.download_button(
                f"Descargar {fname}",
                data=export_report_excel(sheets),
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary", use_container_width=True, key=f"dl_{key}",
            )
else:
    st.info("Sube al menos el **EXPORT_CALL_REPORT (Estados = ALL)** y presiona **Generar los 3 reportes**.")
