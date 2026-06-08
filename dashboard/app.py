"""
Reportes Diarios — Campana GRAL (VICIdial)
streamlit run dashboard/app.py

Login por empresa (Cuzco / Coquimbo).
Los tableros generados se guardan automaticamente por cuenta;
la proxima vez la app los carga sola como "tablero de ayer".
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import io
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from vicidial_reports import (
    generar_reportes_diarios, export_report_excel,
    jornada_label, read_tablero_anterior,
)

# ── Rutas ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── Cuentas (usuario: contrasena) ─────────────────────────────────────────────
ACCOUNTS = {
    "Cuzco":    "Cuzco2024!",
    "Coquimbo": "Coquimbo2024!",
}

# ── Config de pagina ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Reportes GRAL | Call Center",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.stApp { background-color: #0f1117; }
[data-testid="stDataFrame"] { border: 1px solid #2a3045; border-radius: 8px; }
hr { border-color: #2a3045; }
.login-card {
    background: #1e2535; border-radius: 16px; padding: 40px 36px;
    border: 1px solid #2a3045; box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# PERSISTENCIA LOCAL
# ─────────────────────────────────────────────────────────────────────────────

def cuenta_dir(cuenta: str) -> Path:
    d = DATA_DIR / cuenta
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hist_path(cuenta: str, nombre: str) -> Path:
    return cuenta_dir(cuenta) / f"historico_{nombre}.xlsx"


def cargar_tablero_guardado(cuenta: str, nombre: str) -> dict[str, pd.DataFrame]:
    p = _hist_path(cuenta, nombre)
    if not p.exists():
        return {}
    return pd.read_excel(p, sheet_name=None)


def guardar_tablero(cuenta: str, nombre: str, sheets: dict[str, pd.DataFrame]):
    p = _hist_path(cuenta, nombre)
    with pd.ExcelWriter(p, engine="openpyxl") as w:
        for sname, df in sheets.items():
            df.to_excel(w, index=False, sheet_name=str(sname)[:31])


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────

def show_login():
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        st.markdown("""
        <div class="login-card">
            <p style="font-size:1.6rem;font-weight:800;color:#fff;margin-bottom:4px">Call Center</p>
            <p style="color:#6b7a99;font-size:0.95rem;margin-bottom:28px">Reportes Diarios GRAL — VICIdial</p>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        with st.form("login"):
            cuenta = st.selectbox("Empresa", list(ACCOUNTS.keys()))
            pw = st.text_input("Contrasena", type="password", placeholder="••••••••")
            if st.form_submit_button("Ingresar", use_container_width=True, type="primary"):
                if pw == ACCOUNTS.get(cuenta):
                    st.session_state["cuenta"] = cuenta
                    st.rerun()
                else:
                    st.error("Contrasena incorrecta.")

        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("Acceso restringido. Contacta al Administrador si tienes problemas.")


# ─────────────────────────────────────────────────────────────────────────────
# PANTALLA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def show_main():
    cuenta = st.session_state["cuenta"]

    # Sidebar: cuenta + cerrar sesion
    with st.sidebar:
        st.markdown(f"""
        <div style="padding:16px 8px 8px">
            <div style="font-size:1.1rem;font-weight:700;color:#fff">{cuenta}</div>
            <div style="font-size:0.8rem;color:#6b7a99;margin-top:2px">Reportes Diarios GRAL</div>
        </div>
        """, unsafe_allow_html=True)
        st.divider()
        if st.button("Cerrar Sesion", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # Encabezado
    st.markdown(f"# Reportes Diarios — Campana GRAL ({cuenta})")
    st.markdown(
        "Sube el **EXPORT_CALL_REPORT (Estados = ALL)** del dia (obligatorio). "
        "Los tableros anteriores se cargan **automaticamente** desde el historial guardado; "
        "puedes subir una version distinta para sobreescribirlos."
    )
    st.divider()

    # ── Fecha ──────────────────────────────────────────────────────────────────
    fecha = st.date_input("Fecha del reporte", value=datetime.now().date(), format="DD/MM/YYYY")
    if fecha.weekday() == 5:
        st.info("Es **sabado** — se aplica la regla de media jornada (8:00-12:00) y la comparacion sera sabado contra sabado.")

    # ── Archivos frescos ───────────────────────────────────────────────────────
    st.markdown("### 1. Archivos frescos de VICIdial (jornada del dia)")
    c1, c2, c3 = st.columns(3)
    with c1:
        f_amd   = st.file_uploader("AST_AMD_log_report (.csv)",              type=["csv","txt"], key="f_amd")
    with c2:
        f_vdad  = st.file_uploader("AST_VDADstats (.csv)",                   type=["csv","txt"], key="f_vdad")
    with c3:
        f_export = st.file_uploader(
            "EXPORT_CALL_REPORT — Estados = ALL (.txt/.csv)  ⭐ insumo principal",
            type=["txt","csv"], key="f_export",
        )

    # ── Tableros anteriores (auto + override) ──────────────────────────────────
    st.markdown("### 2. Tableros del dia anterior (auto-cargados; sube uno si quieres sobreescribir)")

    nombres = ["contactabilidad", "recontacto", "tipificacion"]
    labels  = ["Tablero_Contactabilidad_GRAL", "Control_Recontacto_GRAL", "Tipificacion_Gestion_GRAL"]
    c4, c5, c6 = st.columns(3)
    uploaders, auto_status = {}, {}
    for col, nom, lbl in zip([c4, c5, c6], nombres, labels):
        hist_path = _hist_path(cuenta, nom)
        existe = hist_path.exists()
        with col:
            uf = st.file_uploader(
                f"{lbl} (.xlsx)",
                type=["xlsx","xls"], key=f"f_{nom}_ayer",
                help=f"{'Historial guardado disponible — se usa automaticamente si no subes nada.' if existe else 'Sin historial guardado aun.'}"
            )
            uploaders[nom] = uf
            if existe and uf is None:
                st.caption(f"Usando historial guardado de {hist_path.stat().st_mtime and datetime.fromtimestamp(hist_path.stat().st_mtime).strftime('%d/%m %H:%M')}")
                auto_status[nom] = True
            else:
                auto_status[nom] = False

    with st.expander("Reglas aplicadas"):
        st.markdown("""
- **Promesa de pago** = status `04` + `21` (siempre se suman ambos).
- **Status `01`** = cuelga en saludo (rechazo temprano) — no cuenta como gestion.
- **Segmentacion de humanos** = status `01, 02, 04, 09, 14, 18, 19, 21`, con hoja **Por Entidad**.
- **Sabado** = media jornada (8 AM-12 PM); comparacion sabado contra sabado.
- El dia nuevo se **agrega al acumulado** leyendo el historial guardado o el tablero subido.
- **Monto comprometido** = campo `postal_code` del export; **estado del deudor** = campo `first_name`.
        """)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Generar ────────────────────────────────────────────────────────────────
    if st.button("GENERAR LOS 3 REPORTES", type="primary", use_container_width=True):
        if f_export is None:
            st.error("Falta el **EXPORT_CALL_REPORT (Estados = ALL)** — es el insumo principal y obligatorio.")
            return

        def _resolve_tablero(nom, uploaded_file):
            """Usa el archivo subido si existe, si no carga el historial guardado."""
            if uploaded_file is not None:
                return uploaded_file
            hist = cargar_tablero_guardado(cuenta, nom)
            if not hist:
                return None
            # Convertir dict de dataframes en un objeto similar a un uploaded file
            class _DictWrapper:
                def read(self):
                    return None
                name = "historico.xlsx"
            return hist  # se pasa directo a read_tablero_anterior que acepta None tambien

        try:
            tab_cont  = uploaders["contactabilidad"] or (cargar_tablero_guardado(cuenta, "contactabilidad") or None)
            tab_rec   = uploaders["recontacto"]      or (cargar_tablero_guardado(cuenta, "recontacto")      or None)
            tab_tipif = uploaders["tipificacion"]     or (cargar_tablero_guardado(cuenta, "tipificacion")    or None)

            # read_tablero_anterior acepta None; para dicts ya cargados lo adaptamos
            def _to_sheets(x):
                if x is None or isinstance(x, dict):
                    return x or {}
                return read_tablero_anterior(x)

            resultado = generar_reportes_diarios(
                export_call_report=f_export,
                fecha=fecha,
                amd_log=f_amd,
                vdad_stats=f_vdad,
                tablero_contactabilidad_ayer=None,
                control_recontacto_ayer=None,
                tipificacion_gestion_ayer=None,
                _tableros_precargados={
                    "contactabilidad": _to_sheets(tab_cont),
                    "recontacto":      _to_sheets(tab_rec),
                    "tipificacion":    _to_sheets(tab_tipif),
                },
            )
        except Exception as e:
            st.error(f"Error al generar los reportes: {e}")
            import traceback
            st.code(traceback.format_exc())
            return

        # Guardar automaticamente para la proxima vez
        guardar_tablero(cuenta, "contactabilidad", resultado["contactabilidad"])
        guardar_tablero(cuenta, "recontacto",      resultado["recontacto"])
        guardar_tablero(cuenta, "tipificacion",     resultado["tipificacion"])

        st.session_state["reportes_gral"] = resultado
        st.session_state["reportes_gral_fecha"] = fecha
        st.success(
            f"Reportes generados para el {fecha.strftime('%d/%m/%Y')} ({jornada_label(fecha)}).  "
            f"Historial guardado automaticamente para {cuenta}."
        )

    # ── Resultados ─────────────────────────────────────────────────────────────
    resultado = st.session_state.get("reportes_gral")
    if not resultado:
        st.info("Sube al menos el **EXPORT_CALL_REPORT (Estados = ALL)** y presiona **Generar los 3 reportes**.")
        return

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
            hoja = st.selectbox("Hoja", list(sheets.keys()), key=f"hoja_{key}")
            st.dataframe(sheets[hoja], use_container_width=True, hide_index=True)
            st.download_button(
                f"Descargar {fname}",
                data=export_report_excel(sheets),
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary", use_container_width=True, key=f"dl_{key}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if "cuenta" not in st.session_state:
        show_login()
    else:
        show_main()


if __name__ == "__main__":
    main()
