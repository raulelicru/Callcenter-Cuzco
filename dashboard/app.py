"""
Reportes Diarios — Campana GRAL (VICIdial)
streamlit run dashboard/app.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import io
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from vicidial_reports import (
    generar_reportes_diarios, export_report_excel,
    jornada_label, read_tablero_anterior,
)
import supabase_storage as sbs

# ── Rutas ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── Cuentas ───────────────────────────────────────────────────────────────────
ACCOUNTS = {
    "Cuzco":    "Cuzco2024!",
    "Coquimbo": "Coquimbo2024!",
}

# ── Config de pagina ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Reportes GRAL | Call Center",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Temas ─────────────────────────────────────────────────────────────────────
TEMAS = {
    "Dark": {
        "bg": "#0f1117", "bg2": "#1e2535", "border": "#2a3045",
        "text": "#e2e8f0", "subtext": "#6b7a99", "card_bg": "#1e2535",
        "plotly": "plotly_dark", "chart_bg": "#1e2535",
    },
    "Light": {
        "bg": "#f4f6fa", "bg2": "#ffffff", "border": "#d1d9e6",
        "text": "#1a1f2e", "subtext": "#5a6580", "card_bg": "#ffffff",
        "plotly": "plotly_white", "chart_bg": "#ffffff",
    },
}

def _t():
    return TEMAS[st.session_state.get("tema", "Dark")]

def aplicar_tema():
    t = _t()
    st.markdown(f"""
    <style>
    .stApp {{ background-color: {t['bg']}; color: {t['text']}; }}
    [data-testid="stSidebar"] {{ background-color: {t['bg2']}; border-right: 1px solid {t['border']}; }}
    [data-testid="stDataFrame"] {{ border: 1px solid {t['border']}; border-radius: 8px; }}
    hr {{ border-color: {t['border']}; }}
    .login-card {{
        background: {t['card_bg']}; border-radius: 16px; padding: 40px 36px;
        border: 1px solid {t['border']}; box-shadow: 0 8px 32px rgba(0,0,0,0.15);
    }}
    .kpi-card {{
        background: {t['card_bg']}; border-radius: 12px; padding: 20px 18px;
        border: 1px solid {t['border']}; margin-bottom: 8px;
    }}
    .kpi-val  {{ font-size: 2rem; font-weight: 800; margin: 0; }}
    .kpi-lbl  {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: .05em;
                 color: {t['subtext']}; margin: 0; }}
    .kpi-delta {{ font-size: 0.85rem; margin-top: 4px; }}
    h1,h2,h3,h4 {{ color: {t['text']} !important; }}
    </style>
    """, unsafe_allow_html=True)

def kpi_card(label, valor, delta=None, color="#3b82f6"):
    delta_html = f'<p class="kpi-delta" style="color:{color}">{delta}</p>' if delta else ""
    st.markdown(f"""
    <div class="kpi-card" style="border-left: 4px solid {color}">
        <p class="kpi-lbl">{label}</p>
        <p class="kpi-val" style="color:{color}">{valor}</p>
        {delta_html}
    </div>""", unsafe_allow_html=True)

def chart_layout(height=320):
    t = _t()
    return dict(
        template=t["plotly"], height=height,
        paper_bgcolor=t["chart_bg"], plot_bgcolor=t["chart_bg"],
        font_color=t["text"], margin=dict(t=30, b=20, l=10, r=10),
    )


# ─────────────────────────────────────────────────────────────────────────────
# PERSISTENCIA
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _supabase_ok() -> bool:
    return sbs.supabase_disponible()

def _hist_path(cuenta, nombre):
    d = DATA_DIR / cuenta
    d.mkdir(parents=True, exist_ok=True)
    return d / f"historico_{nombre}.xlsx"

def cargar_tablero_guardado(cuenta, nombre):
    if _supabase_ok():
        try:
            s = sbs.cargar_reporte(cuenta, nombre)
            if s: return s
        except Exception:
            pass
    p = _hist_path(cuenta, nombre)
    return pd.read_excel(p, sheet_name=None) if p.exists() else {}

def guardar_tablero(cuenta, nombre, sheets):
    if _supabase_ok():
        try: sbs.guardar_reporte(cuenta, nombre, sheets)
        except Exception: pass
    p = _hist_path(cuenta, nombre)
    with pd.ExcelWriter(p, engine="openpyxl") as w:
        for s, df in sheets.items():
            df.to_excel(w, index=False, sheet_name=str(s)[:31])


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────

def show_login():
    aplicar_tema()
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        tema_l = st.radio("Tema", ["Dark", "Light"], horizontal=True,
                          index=0 if st.session_state.get("tema","Dark")=="Dark" else 1,
                          key="tema_login")
        if tema_l != st.session_state.get("tema", "Dark"):
            st.session_state["tema"] = tema_l; st.rerun()
        st.markdown("""
        <div class="login-card">
            <p style="font-size:1.6rem;font-weight:800;margin-bottom:4px">Call Center</p>
            <p style="font-size:0.95rem;margin-bottom:4px">Reportes Diarios GRAL — VICIdial</p>
        </div>""", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("login"):
            cuenta = st.selectbox("Empresa", list(ACCOUNTS.keys()))
            pw = st.text_input("Contrasena", type="password", placeholder="••••••••")
            if st.form_submit_button("Ingresar", use_container_width=True, type="primary"):
                if pw == ACCOUNTS.get(cuenta):
                    st.session_state.update({"cuenta": cuenta, "page": "reportes"})
                    st.rerun()
                else:
                    st.error("Contrasena incorrecta.")
        st.caption("Acceso restringido.")


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

def show_sidebar():
    cuenta = st.session_state["cuenta"]
    with st.sidebar:
        st.markdown(f"""
        <div style="padding:16px 8px 8px">
            <div style="font-size:1.1rem;font-weight:700">{cuenta}</div>
            <div style="font-size:0.8rem;margin-top:2px">Campana GRAL</div>
        </div>""", unsafe_allow_html=True)
        st.divider()

        page = st.session_state.get("page", "reportes")
        pages = {"reportes": "Generar Reportes", "dashboard": "Dashboard KPIs"}
        for key, label in pages.items():
            tipo = "primary" if page == key else "secondary"
            if st.button(label, use_container_width=True, type=tipo, key=f"nav_{key}"):
                st.session_state["page"] = key; st.rerun()

        st.divider()
        tema_actual = st.session_state.get("tema", "Dark")
        nuevo_tema = st.radio("Tema", ["Dark", "Light"], horizontal=True,
                              index=0 if tema_actual == "Dark" else 1, key="tema_sidebar")
        if nuevo_tema != tema_actual:
            st.session_state["tema"] = nuevo_tema; st.rerun()

        st.divider()
        st.caption("Supabase conectado" if _supabase_ok() else "Sin Supabase — disco local")
        st.divider()
        if st.button("Cerrar Sesion", use_container_width=True):
            st.session_state.clear(); st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# PAGINA: GENERAR REPORTES
# ─────────────────────────────────────────────────────────────────────────────

def page_reportes():
    cuenta = st.session_state["cuenta"]
    st.markdown(f"## Generar Reportes Diarios — {cuenta}")
    st.markdown("Sube el **EXPORT_CALL_REPORT (Estados = ALL)** y presiona generar.")
    st.divider()

    fecha = st.date_input("Fecha del reporte", value=datetime.now().date(), format="DD/MM/YYYY")
    if fecha.weekday() == 5:
        st.info("Sabado — media jornada (8:00-12:00). Comparacion sabado vs sabado.")

    st.markdown("#### Archivos frescos de VICIdial")
    c1, c2, c3 = st.columns(3)
    with c1: f_amd  = st.file_uploader("AST_AMD_log_report", type=["csv","txt"], key="f_amd")
    with c2: f_vdad = st.file_uploader("AST_VDADstats",      type=["csv","txt"], key="f_vdad")
    with c3: f_export = st.file_uploader(
        "EXPORT_CALL_REPORT — Estados = ALL  ⭐", type=["txt","csv"], key="f_export")

    st.markdown("#### Tableros del dia anterior (se auto-cargan del historial; sube para sobreescribir)")
    c4, c5, c6 = st.columns(3)
    nombres = ["contactabilidad","recontacto","tipificacion"]
    labels  = ["Tablero_Contactabilidad","Control_Recontacto","Tipificacion_Gestion"]
    uploaders = {}
    for col, nom, lbl in zip([c4,c5,c6], nombres, labels):
        existe = _hist_path(cuenta, nom).exists() or bool(cargar_tablero_guardado(cuenta, nom))
        with col:
            uploaders[nom] = st.file_uploader(f"{lbl} (.xlsx)", type=["xlsx","xls"], key=f"f_{nom}_ayer",
                help="Historial guardado disponible." if existe else "Sin historial aun.")
            if existe and not uploaders[nom]:
                st.caption("Usando historial guardado automaticamente.")

    with st.expander("Reglas de negocio aplicadas"):
        st.markdown("""
- Promesa de pago = status `04` + `21` (siempre suma ambos).
- Status `01` = cuelga en saludo, no cuenta como gestion.
- Humanos = status `01,02,04,09,14,18,19,21` (hoja Por Entidad con evasion por estado).
- Sabado = media jornada; comparacion sabado vs sabado.
- Monto comprometido = `postal_code`; estado del deudor = `first_name`.
        """)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("GENERAR LOS 3 REPORTES", type="primary", use_container_width=True):
        if not f_export:
            st.error("Sube el EXPORT_CALL_REPORT (obligatorio)."); return
        try:
            def _sheets(nom, uf):
                if uf: return read_tablero_anterior(uf)
                return cargar_tablero_guardado(cuenta, nom) or {}

            resultado = generar_reportes_diarios(
                export_call_report=f_export, fecha=fecha,
                amd_log=f_amd, vdad_stats=f_vdad,
                _tableros_precargados={n: _sheets(n, uploaders[n]) for n in nombres},
            )
        except Exception as e:
            st.error(f"Error: {e}")
            import traceback; st.code(traceback.format_exc()); return

        for nom in nombres:
            guardar_tablero(cuenta, nom, resultado[nom])

        st.session_state["reportes_gral"]       = resultado
        st.session_state["reportes_gral_fecha"] = fecha
        st.success(f"Reportes del {fecha.strftime('%d/%m/%Y')} generados y guardados en historial.")

    resultado = st.session_state.get("reportes_gral")
    if not resultado:
        st.info("Sube el EXPORT_CALL_REPORT y presiona Generar."); return

    fecha_gen = st.session_state.get("reportes_gral_fecha", fecha)
    sufijo = fecha_gen.strftime("%Y%m%d")

    st.divider()
    st.markdown("### Resumen y alertas")
    st.markdown(resultado["resumen_md"])
    st.divider()
    st.markdown("### Reportes")

    tabs = st.tabs(["Contactabilidad","Recontacto","Tipificacion"])
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
            st.download_button(f"Descargar {fname}", data=export_report_excel(sheets),
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary", use_container_width=True, key=f"dl_{key}")


# ─────────────────────────────────────────────────────────────────────────────
# PAGINA: DASHBOARD KPIs
# ─────────────────────────────────────────────────────────────────────────────

def _load_acumulado(cuenta, nombre, hoja="Acumulado"):
    sheets = cargar_tablero_guardado(cuenta, nombre)
    df = sheets.get(hoja) or sheets.get("Resumen del Dia")
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df.columns = [str(c).strip().lower().replace(" ","_").replace("%","pct") for c in df.columns]
    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df = df.dropna(subset=["fecha"]).sort_values("fecha")
    return df.reset_index(drop=True)


def page_dashboard():
    cuenta = st.session_state["cuenta"]
    st.markdown(f"## Dashboard KPIs — {cuenta}")
    st.markdown("*Basado en el historial acumulado guardado.*")
    st.divider()

    df_c = _load_acumulado(cuenta, "contactabilidad")
    df_r = _load_acumulado(cuenta, "recontacto")
    df_t = _load_acumulado(cuenta, "tipificacion")

    if df_c.empty:
        st.info("Aun no hay historial acumulado. Genera al menos un reporte diario para ver los KPIs.")
        return

    # ── KPIs del ultimo dia ────────────────────────────────────────────────────
    last = df_c.iloc[-1]
    prev = df_c.iloc[-2] if len(df_c) > 1 else None

    def _delta(col, fmt=".1f", suffix=""):
        if prev is None or col not in last or col not in prev: return None
        try:
            d = float(last[col]) - float(prev[col])
            sign = "+" if d >= 0 else ""
            return f"{sign}{d:{fmt}}{suffix} vs dia anterior"
        except Exception: return None

    st.markdown("### KPIs del ultimo dia registrado")
    k1,k2,k3,k4,k5 = st.columns(5)
    with k1: kpi_card("Marcaciones totales",
        f"{int(last.get('total_marcaciones',0)):,}",
        _delta("total_marcaciones",",.0f"), "#3b82f6")
    with k2: kpi_card("Contactos humanos",
        f"{int(last.get('contactos_humanos',0)):,}",
        _delta("contactos_humanos",",.0f"), "#8b5cf6")
    with k3: kpi_card("Contactabilidad %",
        f"{float(last.get('tasa_contactabilidad_pct', last.get('tasa_contactabilidad_%',0))):.1f}%",
        _delta("tasa_contactabilidad_pct",".1f","%") or _delta("tasa_contactabilidad_%",".1f","%"),
        "#27ae60")
    with k4: kpi_card("Promesas de pago",
        f"{int(last.get('promesas_pago_(04+21)',0)):,}",
        _delta("promesas_pago_(04+21)",",.0f"), "#f39c12")
    with k5: kpi_card("Monto comprometido",
        f"S/ {float(last.get('monto_comprometido_total',0)):,.0f}",
        _delta("monto_comprometido_total",",.0f"), "#e74c3c")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Graficos de tendencia ──────────────────────────────────────────────────
    cl = chart_layout(320)
    t  = _t()

    st.markdown("### Tendencia diaria")
    col_l, col_r = st.columns(2)

    # 1) Tasa de contactabilidad
    with col_l:
        st.markdown("##### Contactabilidad % por dia")
        tasa_col = next((c for c in df_c.columns if "tasa_contactabilidad" in c), None)
        if tasa_col and "fecha" in df_c.columns:
            fig = px.line(df_c, x="fecha", y=tasa_col, markers=True,
                          labels={"fecha":"Fecha", tasa_col:"Contactabilidad %"},
                          template=t["plotly"])
            fig.update_traces(line_color="#27ae60", line_width=2)
            fig.update_layout(**cl)
            st.plotly_chart(fig, use_container_width=True)

    # 2) Evasion (cuelga en saludo)
    with col_r:
        st.markdown("##### Evasion % (status 01) por dia")
        eva_col = next((c for c in df_c.columns if "evasion" in c or "cuelga" in c), None)
        if eva_col and "fecha" in df_c.columns:
            fig2 = px.bar(df_c, x="fecha", y=eva_col,
                          labels={"fecha":"Fecha", eva_col:"Evasion %"},
                          template=t["plotly"])
            fig2.update_traces(marker_color="#e74c3c")
            fig2.update_layout(**cl)
            st.plotly_chart(fig2, use_container_width=True)

    col_l2, col_r2 = st.columns(2)

    # 3) Promesas de pago
    with col_l2:
        st.markdown("##### Promesas de pago diarias (04+21)")
        prom_col = next((c for c in df_c.columns if "promesas" in c and "pago" in c), None)
        if prom_col and "fecha" in df_c.columns:
            fig3 = px.bar(df_c, x="fecha", y=prom_col,
                          labels={"fecha":"Fecha", prom_col:"Promesas"},
                          template=t["plotly"])
            fig3.update_traces(marker_color="#f39c12")
            fig3.update_layout(**cl)
            st.plotly_chart(fig3, use_container_width=True)

    # 4) Monto comprometido
    with col_r2:
        st.markdown("##### Monto comprometido acumulado (S/)")
        monto_col = next((c for c in df_c.columns if "monto" in c), None)
        if monto_col and "fecha" in df_c.columns:
            fig4 = px.line(df_c, x="fecha", y=monto_col, markers=True,
                           labels={"fecha":"Fecha", monto_col:"Monto S/"},
                           template=t["plotly"])
            fig4.update_traces(line_color="#8b5cf6", line_width=2, fill="tozeroy")
            fig4.update_layout(**cl)
            st.plotly_chart(fig4, use_container_width=True)

    # ── Marcaciones vs Humanos ─────────────────────────────────────────────────
    st.markdown("##### Marcaciones totales vs Contactos humanos")
    marc_col = next((c for c in df_c.columns if "total_marcaciones" in c), None)
    hum_col  = next((c for c in df_c.columns if "contactos_humanos" in c), None)
    if marc_col and hum_col and "fecha" in df_c.columns:
        fig5 = go.Figure()
        fig5.add_trace(go.Bar(x=df_c["fecha"], y=df_c[marc_col], name="Marcaciones", marker_color="#3b82f6"))
        fig5.add_trace(go.Bar(x=df_c["fecha"], y=df_c[hum_col],  name="Contactos humanos", marker_color="#27ae60"))
        fig5.update_layout(barmode="group", **chart_layout(300))
        st.plotly_chart(fig5, use_container_width=True)

    # ── Recontacto ─────────────────────────────────────────────────────────────
    if not df_r.empty:
        st.divider()
        st.markdown("### Recontacto — Pendientes por dia")
        pend_col = next((c for c in df_r.columns if "pendiente" in c), None)
        if pend_col and "fecha" in df_r.columns:
            fig6 = px.bar(df_r, x="fecha", y=pend_col, template=t["plotly"],
                          labels={"fecha":"Fecha", pend_col:"Pendientes"})
            fig6.update_traces(marker_color="#e74c3c")
            fig6.update_layout(**chart_layout(280))
            st.plotly_chart(fig6, use_container_width=True)

    # ── Tipificacion acumulada ─────────────────────────────────────────────────
    if not df_t.empty:
        st.divider()
        st.markdown("### Tipificacion — distribucion del ultimo dia")
        tipif_sheets = cargar_tablero_guardado(cuenta, "tipificacion")
        tipif_df = tipif_sheets.get("Tipificacion")
        if tipif_df is not None and len(tipif_df) > 0:
            tipif_df.columns = [str(c).strip() for c in tipif_df.columns]
            caso_col = next((c for c in tipif_df.columns if "caso" in c.lower()), None)
            tip_col  = next((c for c in tipif_df.columns if "tipific" in c.lower() or "descrip" in c.lower()), None)
            if caso_col and tip_col:
                fig7 = px.pie(tipif_df, values=caso_col, names=tip_col,
                              template=t["plotly"], hole=0.45)
                fig7.update_layout(**chart_layout(350))
                st.plotly_chart(fig7, use_container_width=True)

    # ── Tabla historica completa ───────────────────────────────────────────────
    st.divider()
    with st.expander("Historial completo de Contactabilidad"):
        st.dataframe(df_c, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if "cuenta" not in st.session_state:
        show_login()
        return
    aplicar_tema()
    show_sidebar()
    page = st.session_state.get("page", "reportes")
    if page == "dashboard":
        page_dashboard()
    else:
        page_reportes()


if __name__ == "__main__":
    main()
