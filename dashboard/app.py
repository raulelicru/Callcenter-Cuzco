"""
Dashboard de Cobranza - Sistema Integral
streamlit run dashboard/app.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import joblib, io
from pathlib import Path
from datetime import datetime

from database import (
    init_db, get_clientes_by_ids, upsert_clientes_batch,
    log_carga, get_cargas_historico, get_metricas_globales, get_all_clientes_df,
)
from auth import authenticate, create_user, get_all_users, toggle_user_status, update_password

# ── Rutas absolutas ───────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
MODELS_DIR = BASE_DIR / "models"
DATA_DIR   = BASE_DIR / "data"

# ── Config de página ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Cobranza | Call Center Cuzco",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS Global ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Fondo general */
.stApp { background-color: #0f1117; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #161b27 0%, #1a2035 100%);
    border-right: 1px solid #2a3045;
}

/* Tarjeta métrica personalizada */
.metrica {
    background: #1e2535;
    border-radius: 10px;
    padding: 18px 20px;
    border-left: 4px solid;
    margin-bottom: 8px;
}
.metrica-valor { font-size: 2rem; font-weight: 700; color: #ffffff; margin: 0; }
.metrica-label { font-size: 0.78rem; color: #8899aa; margin: 0; text-transform: uppercase; letter-spacing: 0.05em; }
.metrica-delta { font-size: 0.85rem; margin-top: 4px; }

/* Badge de segmento */
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.05em;
}
.badge-alto  { background: #1a3a1a; color: #4ade80; border: 1px solid #27ae60; }
.badge-medio { background: #3a2a00; color: #fbbf24; border: 1px solid #f39c12; }
.badge-bajo  { background: #3a0f0f; color: #f87171; border: 1px solid #e74c3c; }

/* Card de estrategia */
.card-estrategia {
    background: #1e2535;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 16px;
}

/* Login card */
.login-card {
    background: #1e2535;
    border-radius: 16px;
    padding: 40px 36px;
    border: 1px solid #2a3045;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}
.login-title { font-size: 1.8rem; font-weight: 800; color: #fff; margin-bottom: 4px; }
.login-sub   { color: #6b7a99; font-size: 0.95rem; margin-bottom: 28px; }

/* Botones de navegacion */
[data-testid="stSidebar"] .stButton button {
    width: 100%;
    text-align: left;
    background: transparent;
    border: none;
    color: #8899aa;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 0.9rem;
    margin-bottom: 2px;
    transition: all 0.15s;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: #2a3045;
    color: #ffffff;
}

/* Divider */
hr { border-color: #2a3045; }

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid #2a3045; border-radius: 8px; }

/* KPI highlight bar */
.kpi-bar {
    display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px;
}
.kpi-item {
    flex: 1; min-width: 140px;
    background: #1e2535;
    border-radius: 10px;
    padding: 16px;
    border-top: 3px solid;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

# ── Colores por segmento ──────────────────────────────────────────────────────
COLORES = {"ALTO": "#27ae60", "MEDIO": "#f39c12", "BAJO": "#e74c3c"}

# ── Estrategias ───────────────────────────────────────────────────────────────
ESTRATEGIAS = {
    "ALTO": {
        "canal":      "WhatsApp Business / SMS / Email / IVR Autopago",
        "accion":     "Recordatorio digital automatico con link de pago",
        "oferta":     "2 cuotas sin interes adicional / Autopago inmediato",
        "frecuencia": "Max. 2 contactos digitales por semana",
        "escalacion": "Sin pago en 7 dias -> Escalar a MEDIO",
        "script":     "Hola [Nombre], tienes un saldo de S/[monto]. Pagalo hoy aqui: [link]. Tu historial crediticio te lo agradecera.",
        "kpis":       "Conversion >= 20% | Costo S/ 0.10-0.30 | ROI >= 400%",
        "referencia": "Hoist Finance / Interbank Peru - Digital First Collection",
    },
    "MEDIO": {
        "canal":      "Marcador Predictivo + Agente Humano (AMD activado)",
        "accion":     "Negociacion activa con script ACED + registro de Promesa de Pago",
        "oferta":     "Plan 3-6 cuotas / Condonacion intereses moratorios",
        "frecuencia": "Max. 3 intentos/dia | Mejor hora: 9-11am y 6-8pm L-V",
        "escalacion": "2 PTPs rotas -> Escalar a BAJO",
        "script":     "ACED: Acknowledge -> Create urgency -> Empathize -> Deal. Oferta: Puedo condonar los intereses si paga el capital hoy.",
        "kpis":       "RPC >= 45% | PTP >= 30% | Kept PTP >= 65% | Costo S/ 2-3.50",
        "referencia": "FICO TRIAD / COFACE / Encore Capital - Human-Assisted Negotiation",
    },
    "BAJO": {
        "canal":      "Especialista Senior / Notaria / Agencia Externa / Pre-Legal",
        "accion":     "Skip Tracing + Carta Notarial + Oferta Settlement",
        "oferta":     "Score 20-33: Skip tracing | Score 10-19: Quita 20-40% | Score 1-9: Pre-legal",
        "frecuencia": "Gestion semanal especializada",
        "escalacion": "DPD > 180 -> Evaluar venta de cartera (5-15 ctvs/sol)",
        "script":     "Notificamos que de no regularizar su deuda de S/[monto] en 15 dias habiles, iniciaremos proceso judicial y registro en centrales de riesgo SBS/Equifax.",
        "kpis":       "Skip tracing >= 25% | Settlement >= 15% | Recovery >= 8%",
        "referencia": "Intrum / Portfolio Recovery Associates - Intensive & Legal",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def load_model():
    p = MODELS_DIR / "pipeline_random_forest.pkl"
    return joblib.load(p) if p.exists() else None


def score_df(df_raw, pipeline):
    from model import score_portfolio
    df_s = score_portfolio(df_raw, pipeline)
    for k in ["canal", "accion", "oferta", "frecuencia"]:
        df_s[f"estrategia_{k}"] = df_s["segmento"].map(
            lambda s, k=k: ESTRATEGIAS.get(s, {}).get(k, "")
        )
    return df_s


def process_upload(df_raw, pipeline, usuario, filename):
    if "cliente_id" not in df_raw.columns:
        posibles = [c for c in df_raw.columns if "id" in c.lower() or "cliente" in c.lower()]
        if posibles:
            df_raw = df_raw.rename(columns={posibles[0]: "cliente_id"})
        else:
            df_raw.insert(0, "cliente_id", [f"CLI-{i:06d}" for i in range(1, len(df_raw)+1)])

    ids = df_raw["cliente_id"].astype(str).tolist()
    df_ex = get_clientes_by_ids(ids)
    ids_conocidos = set(df_ex["cliente_id"].tolist()) if len(df_ex) > 0 else set()
    n_conocidos = sum(1 for i in ids if i in ids_conocidos)
    n_nuevos = len(ids) - n_conocidos

    df_scored = score_df(df_raw, pipeline)
    df_scored["es_nuevo"] = ~df_scored["cliente_id"].isin(ids_conocidos)
    df_scored["estado_carga"] = df_scored["es_nuevo"].map({True: "Nuevo", False: "Actualizado"})

    carga_id = log_carga(usuario, filename, len(df_scored), n_nuevos, n_conocidos)
    upsert_clientes_batch(df_scored, carga_id)
    return df_scored, {"total": len(df_scored), "nuevos": n_nuevos, "conocidos": n_conocidos}


def export_excel(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Cartera Completa")
        for seg in ["ALTO", "MEDIO", "BAJO"]:
            sub = df[df["segmento"] == seg]
            if len(sub) > 0:
                sub.to_excel(w, index=False, sheet_name=f"Segmento {seg}")
        resumen = (
            df.groupby("segmento")
            .agg(clientes=("cliente_id","count"), score_prom=("score_operativo","mean"),
                 prob_prom=("prob_pago","mean"), saldo=("saldo_total","sum"))
            .round(2)
        )
        resumen["pct_cartera"] = (resumen["clientes"] / len(df) * 100).round(1)
        resumen.to_excel(w, sheet_name="Resumen Ejecutivo")
        guia = pd.DataFrame([
            {"Segmento": s, "Canal": ESTRATEGIAS[s]["canal"],
             "Accion": ESTRATEGIAS[s]["accion"], "Oferta": ESTRATEGIAS[s]["oferta"],
             "KPIs": ESTRATEGIAS[s]["kpis"]}
            for s in ["ALTO", "MEDIO", "BAJO"]
        ])
        guia.to_excel(w, index=False, sheet_name="Guia Estrategias")
    return buf.getvalue()


def card_metrica(label, valor, delta=None, color="#3b82f6"):
    delta_html = f'<p class="metrica-delta" style="color:{color}">{delta}</p>' if delta else ""
    st.markdown(f"""
    <div class="metrica" style="border-left-color:{color}">
        <p class="metrica-label">{label}</p>
        <p class="metrica-valor">{valor}</p>
        {delta_html}
    </div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────

def show_login():
    _, col, _ = st.columns([1, 1.1, 1])
    with col:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        st.markdown("""
        <div class="login-card">
            <p class="login-title">Call Center Cuzco</p>
            <p class="login-sub">Sistema Predictivo de Cobranza</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        with st.form("login_form"):
            usuario  = st.text_input("Usuario", placeholder="Ingresa tu usuario")
            password = st.text_input("Contrasena", type="password", placeholder="••••••••")
            ingresar = st.form_submit_button("Ingresar", use_container_width=True, type="primary")

        if ingresar:
            if not usuario or not password:
                st.error("Completa usuario y contrasena.")
            else:
                user = authenticate(usuario, password)
                if user:
                    st.session_state["user"] = user
                    st.session_state["page"] = "inicio"
                    st.rerun()
                else:
                    st.error("Usuario o contrasena incorrectos.")

        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("Acceso restringido. Contacta al Administrador si tienes problemas.")


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

def show_sidebar():
    user = st.session_state["user"]
    with st.sidebar:
        st.markdown(f"""
        <div style="padding: 16px 8px 8px;">
            <div style="font-size:1.1rem;font-weight:700;color:#fff">{user['nombre']}</div>
            <div style="font-size:0.8rem;color:#6b7a99;margin-top:2px">
                {'Administrador' if user['rol']=='admin' else 'Colaborador'}
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.divider()

        pages = {
            "inicio":      "  Inicio",
            "cargar":      "  Cargar Cartera",
            "analisis":    "  Analisis",
            "historial":   "  Historial",
            "estrategias": "  Estrategias",
        }
        if user["rol"] == "admin":
            pages["admin"] = "  Panel Admin"

        cur = st.session_state.get("page", "inicio")
        for key, label in pages.items():
            is_active = cur == key
            btn_style = "primary" if is_active else "secondary"
            if st.button(label, use_container_width=True, type=btn_style, key=f"nav_{key}"):
                st.session_state["page"] = key
                st.rerun()

        st.divider()
        if st.button("Cerrar Sesion", use_container_width=True, key="logout"):
            st.session_state.clear()
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("v2.0 — Call Center Cuzco")


# ─────────────────────────────────────────────────────────────────────────────
# PAGINA: INICIO
# ─────────────────────────────────────────────────────────────────────────────

def page_inicio():
    st.markdown("## Resumen General de la Cartera")
    st.markdown(f"*Actualizado: {datetime.now().strftime('%d/%m/%Y %H:%M')}*")
    st.divider()

    m = get_metricas_globales()
    total = m["total_clientes"]

    if total == 0:
        st.info("La base de datos esta vacia. Ve a **Cargar Cartera** para comenzar.")
        return

    seg   = m["por_segmento"]
    alto  = seg.get("ALTO",  {}).get("count", 0)
    medio = seg.get("MEDIO", {}).get("count", 0)
    bajo  = seg.get("BAJO",  {}).get("count", 0)

    # KPIs
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: card_metrica("Total en Base de Datos", f"{total:,}", color="#3b82f6")
    with c2: card_metrica("Score Promedio", f"{m['avg_score']}", color="#8b5cf6")
    with c3: card_metrica("Segmento ALTO", f"{alto:,}", f"{alto/total*100:.1f}% de la cartera", "#27ae60")
    with c4: card_metrica("Segmento MEDIO", f"{medio:,}", f"{medio/total*100:.1f}% de la cartera", "#f39c12")
    with c5: card_metrica("Segmento BAJO", f"{bajo:,}", f"{bajo/total*100:.1f}% de la cartera", "#e74c3c")

    st.markdown("<br>", unsafe_allow_html=True)

    df_db = get_all_clientes_df(limit=10000)
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("#### Composicion por Segmento")
        data_pie = {
            "Segmento": list(seg.keys()),
            "Clientes": [v["count"] for v in seg.values()],
        }
        fig = px.pie(data_pie, values="Clientes", names="Segmento",
                     color="Segmento", color_discrete_map=COLORES,
                     hole=0.5, template="plotly_dark")
        fig.update_layout(
            height=340,
            paper_bgcolor="#1e2535", plot_bgcolor="#1e2535",
            font_color="#aaa",
            legend=dict(orientation="h", y=-0.1),
            margin=dict(t=20, b=20),
        )
        fig.update_traces(textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown("#### Distribucion de Score (1-100)")
        if len(df_db) > 0:
            fig2 = px.histogram(
                df_db, x="score_operativo", nbins=40,
                color="segmento", color_discrete_map=COLORES,
                template="plotly_dark",
                labels={"score_operativo": "Score Operativo", "count": "Clientes"},
            )
            fig2.update_layout(
                height=340,
                paper_bgcolor="#1e2535", plot_bgcolor="#1e2535",
                font_color="#aaa", bargap=0.05,
                margin=dict(t=20, b=20),
                legend_title_text="Segmento",
            )
            st.plotly_chart(fig2, use_container_width=True)

    # Saldo por segmento
    st.markdown("#### Saldo Total por Segmento (S/)")
    saldo_data = [
        {"Segmento": k, "Saldo": round(v.get("saldo", 0), 0)}
        for k, v in seg.items()
    ]
    if saldo_data:
        fig3 = px.bar(
            pd.DataFrame(saldo_data), x="Segmento", y="Saldo",
            color="Segmento", color_discrete_map=COLORES,
            text_auto=".3s", template="plotly_dark",
        )
        fig3.update_layout(
            height=280, showlegend=False,
            paper_bgcolor="#1e2535", plot_bgcolor="#1e2535",
            font_color="#aaa", margin=dict(t=20, b=20),
        )
        st.plotly_chart(fig3, use_container_width=True)

    st.markdown("#### Ultimas Cargas")
    df_cargas = get_cargas_historico()
    if len(df_cargas) > 0:
        st.dataframe(df_cargas.head(6), hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# PAGINA: CARGAR CARTERA
# ─────────────────────────────────────────────────────────────────────────────

def page_cargar():
    st.markdown("## Cargar Cartera")
    st.markdown("*Sube el Excel del dia. El sistema detecta automaticamente clientes conocidos vs nuevos.*")
    st.divider()

    pipeline = load_model()
    if pipeline is None:
        st.error("Modelo no encontrado. Ejecuta primero: python src/main.py")
        return

    uploaded = st.file_uploader(
        "Selecciona el archivo de cartera",
        type=["xlsx", "xls", "csv"],
        help="Acepta Excel (.xlsx, .xls) y CSV",
    )

    if uploaded is None:
        with st.expander("Columnas esperadas en el archivo"):
            col_l, col_r = st.columns(2)
            with col_l:
                st.markdown("""
| Columna | Descripcion |
|---|---|
| `cliente_id` | Identificador unico |
| `dpd` | Dias en mora |
| `saldo_total` | Saldo vencido |
| `bucket_mora` | B1, B2, B3, B4 |
| `rpc_rate` | Tasa de contacto (0.0-1.0) |
| `promesas_cumplidas` | Promesas honradas |
                """)
            with col_r:
                st.markdown("""
| Columna | Descripcion |
|---|---|
| `promesas_rotas` | Promesas incumplidas |
| `dias_ultimo_contacto` | Dias desde ultimo RPC |
| `ultimo_estado_marcado` | RPC_PROMESA, NO_CONTESTA... |
| `estado_laboral` | Dependiente, Independiente... |
| `ingreso_mensual` | Ingreso declarado |
| `ratio_deuda_ingreso` | Deuda / (ingreso x 12) |
                """)
        return

    try:
        name = uploaded.name.lower()
        df_raw = pd.read_csv(uploaded) if name.endswith(".csv") else pd.read_excel(uploaded)
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        return

    st.success(f"Archivo cargado: **{uploaded.name}** — {len(df_raw):,} registros | {df_raw.shape[1]} columnas")

    with st.expander("Vista previa (5 primeros registros)"):
        st.dataframe(df_raw.head(5), use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("PROCESAR CARTERA Y CALCULAR SCORES", type="primary", use_container_width=True):
        usuario = st.session_state["user"]["username"]
        prog = st.progress(0, "Verificando en base de datos...")

        try:
            prog.progress(25, "Identificando clientes conocidos vs nuevos...")
            df_result, stats = process_upload(df_raw, pipeline, usuario, uploaded.name)
            prog.progress(90, "Guardando en base de datos...")
            prog.progress(100, "Completado.")
        except Exception as e:
            st.error(f"Error durante el procesamiento: {e}")
            import traceback
            st.code(traceback.format_exc())
            return

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### Resultado del Procesamiento")

        r1, r2, r3 = st.columns(3)
        with r1: card_metrica("Total Procesado", f"{stats['total']:,}", color="#3b82f6")
        with r2: card_metrica("Ya en BD (actualizados)", f"{stats['conocidos']:,}",
                               f"{stats['conocidos']/stats['total']*100:.1f}%", "#27ae60")
        with r3: card_metrica("Clientes Nuevos", f"{stats['nuevos']:,}",
                               f"{stats['nuevos']/stats['total']*100:.1f}%", "#8b5cf6")

        st.markdown("<br>", unsafe_allow_html=True)
        sc = df_result["segmento"].value_counts()
        s1, s2, s3 = st.columns(3)
        with s1: card_metrica("Segmento ALTO",  f"{sc.get('ALTO',0):,}", color="#27ae60")
        with s2: card_metrica("Segmento MEDIO", f"{sc.get('MEDIO',0):,}", color="#f39c12")
        with s3: card_metrica("Segmento BAJO",  f"{sc.get('BAJO',0):,}", color="#e74c3c")

        st.divider()
        st.markdown("### Cartera Segmentada")

        cols_show = [c for c in [
            "cliente_id", "score_operativo", "segmento", "prob_pago",
            "estrategia_canal", "estrategia_oferta", "dpd",
            "saldo_total", "bucket_mora", "estado_carga",
        ] if c in df_result.columns]

        st.dataframe(
            df_result[cols_show].sort_values("score_operativo", ascending=False).head(500),
            hide_index=True,
            use_container_width=True,
            column_config={
                "score_operativo": st.column_config.ProgressColumn(
                    "Score", min_value=1, max_value=100
                ),
                "prob_pago": st.column_config.NumberColumn("Prob. Pago", format="%.1%"),
                "saldo_total": st.column_config.NumberColumn("Saldo Total", format="S/ %.2f"),
            },
        )
        st.caption(f"Mostrando primeros 500 de {len(df_result):,} registros.")

        st.divider()
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "Descargar Excel Completo (4 hojas)",
                data=export_excel(df_result),
                file_name=f"cartera_{ts}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary", use_container_width=True,
            )
        with d2:
            buf = io.StringIO()
            df_result.to_csv(buf, index=False)
            st.download_button(
                "Descargar CSV para Dialer",
                data=buf.getvalue(),
                file_name=f"dialer_{ts}.csv",
                mime="text/csv",
                use_container_width=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# PAGINA: ANALISIS
# ─────────────────────────────────────────────────────────────────────────────

def page_analisis():
    st.markdown("## Analisis de Cartera")
    st.divider()

    df = get_all_clientes_df(limit=20000)
    if len(df) == 0:
        st.info("Carga tu primera cartera para ver el analisis.")
        return

    segs = st.multiselect(
        "Filtrar por segmento", ["ALTO", "MEDIO", "BAJO"],
        default=["ALTO", "MEDIO", "BAJO"]
    )
    df = df[df["segmento"].isin(segs)]
    st.caption(f"{len(df):,} clientes en la seleccion actual")

    tab1, tab2, tab3 = st.tabs(["Score y Mora", "Contactabilidad", "Saldo y Riesgo"])

    chart_layout = dict(
        paper_bgcolor="#1e2535", plot_bgcolor="#1e2535",
        font_color="#aaa", margin=dict(t=30, b=20),
    )

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Score vs Dias en Mora (DPD)")
            if "dpd" in df.columns:
                fig = px.scatter(
                    df.sample(min(2000, len(df))),
                    x="dpd", y="score_operativo",
                    color="segmento", color_discrete_map=COLORES,
                    opacity=0.55, template="plotly_dark",
                    labels={"dpd": "DPD", "score_operativo": "Score"},
                )
                fig.update_layout(**chart_layout, height=360)
                st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.markdown("##### Clientes por Bucket de Mora")
            if "bucket_mora" in df.columns:
                fig2 = px.histogram(
                    df, x="bucket_mora", color="segmento",
                    color_discrete_map=COLORES, barmode="group",
                    template="plotly_dark",
                    category_orders={"bucket_mora": ["B1","B2","B3","B4"]},
                )
                fig2.update_layout(**chart_layout, height=360)
                st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### RPC Rate por Segmento")
            if "rpc_rate" in df.columns:
                fig3 = px.box(
                    df, x="segmento", y="rpc_rate",
                    color="segmento", color_discrete_map=COLORES,
                    template="plotly_dark",
                    labels={"rpc_rate": "Tasa de Contacto Efectivo"},
                )
                fig3.update_layout(**chart_layout, height=360, showlegend=False)
                st.plotly_chart(fig3, use_container_width=True)
        with c2:
            st.markdown("##### Ultimo Estado de Marcado")
            if "ultimo_estado_marcado" in df.columns:
                cnt = df["ultimo_estado_marcado"].value_counts().head(7).reset_index()
                cnt.columns = ["Estado", "Clientes"]
                fig4 = px.bar(
                    cnt, x="Clientes", y="Estado",
                    orientation="h", template="plotly_dark",
                    color="Clientes", color_continuous_scale="Blues",
                )
                fig4.update_layout(
                    **chart_layout, height=360, showlegend=False,
                    yaxis={"categoryorder": "total ascending"},
                )
                st.plotly_chart(fig4, use_container_width=True)

    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Saldo Total por Segmento (S/)")
            if "saldo_total" in df.columns:
                s = df.groupby("segmento")["saldo_total"].sum().reset_index()
                fig5 = px.bar(
                    s, x="segmento", y="saldo_total",
                    color="segmento", color_discrete_map=COLORES,
                    text_auto=".3s", template="plotly_dark",
                )
                fig5.update_layout(**chart_layout, height=360, showlegend=False)
                st.plotly_chart(fig5, use_container_width=True)
        with c2:
            st.markdown("##### Probabilidad de Pago por Segmento")
            fig6 = px.box(
                df, x="segmento", y="prob_pago",
                color="segmento", color_discrete_map=COLORES,
                template="plotly_dark",
                labels={"prob_pago": "Probabilidad de Pago"},
            )
            fig6.update_layout(**chart_layout, height=360, showlegend=False)
            st.plotly_chart(fig6, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# PAGINA: HISTORIAL
# ─────────────────────────────────────────────────────────────────────────────

def page_historial():
    st.markdown("## Historial de Cargas")
    st.divider()

    df = get_cargas_historico()
    if len(df) == 0:
        st.info("No hay cargas registradas aun.")
        return

    c1, c2, c3 = st.columns(3)
    with c1: card_metrica("Total de Cargas", f"{len(df):,}", color="#3b82f6")
    with c2: card_metrica("Total Procesados", f"{df['total_registros'].sum():,}", color="#27ae60")
    with c3: card_metrica("Clientes Nuevos Registrados", f"{df['registros_nuevos'].sum():,}", color="#8b5cf6")

    st.markdown("<br>", unsafe_allow_html=True)
    st.dataframe(
        df, hide_index=True, use_container_width=True,
        column_config={
            "total_registros":        st.column_config.NumberColumn("Total"),
            "registros_nuevos":       st.column_config.NumberColumn("Nuevos"),
            "registros_actualizados": st.column_config.NumberColumn("Actualizados"),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# PAGINA: ESTRATEGIAS
# ─────────────────────────────────────────────────────────────────────────────

def page_estrategias():
    st.markdown("## Estrategias de Cobranza de Clase Mundial")
    st.markdown("*Basadas en metodologias de Hoist Finance, Encore Capital, FICO TRIAD, COFACE e Intrum.*")
    st.divider()

    score_rng = {"ALTO": "67 - 100", "MEDIO": "34 - 66", "BAJO": "1 - 33"}
    nombres   = {"ALTO": "ALTO", "MEDIO": "MEDIO", "BAJO": "BAJO"}

    for seg, color in [("ALTO", "#27ae60"), ("MEDIO", "#f39c12"), ("BAJO", "#e74c3c")]:
        e = ESTRATEGIAS[seg]
        st.markdown(f"""
        <div class="card-estrategia" style="border-left: 4px solid {color}">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:14px">
                <span style="font-size:1.2rem; font-weight:800; color:{color}">
                    Segmento {nombres[seg]}
                </span>
                <span style="font-size:0.8rem; color:#6b7a99; background:#0f1117;
                    padding:3px 10px; border-radius:20px; border:1px solid #2a3045">
                    Score {score_rng[seg]}
                </span>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px">
                <div>
                    <div style="color:#6b7a99; font-size:0.75rem; margin-bottom:2px">CANAL</div>
                    <div style="color:#e2e8f0; font-size:0.9rem">{e['canal']}</div>
                </div>
                <div>
                    <div style="color:#6b7a99; font-size:0.75rem; margin-bottom:2px">ACCION</div>
                    <div style="color:#e2e8f0; font-size:0.9rem">{e['accion']}</div>
                </div>
                <div>
                    <div style="color:#6b7a99; font-size:0.75rem; margin-bottom:2px">OFERTA</div>
                    <div style="color:#e2e8f0; font-size:0.9rem">{e['oferta']}</div>
                </div>
                <div>
                    <div style="color:#6b7a99; font-size:0.75rem; margin-bottom:2px">FRECUENCIA</div>
                    <div style="color:#e2e8f0; font-size:0.9rem">{e['frecuencia']}</div>
                </div>
                <div>
                    <div style="color:#6b7a99; font-size:0.75rem; margin-bottom:2px">KPIs OBJETIVO</div>
                    <div style="color:{color}; font-size:0.85rem; font-weight:600">{e['kpis']}</div>
                </div>
                <div>
                    <div style="color:#6b7a99; font-size:0.75rem; margin-bottom:2px">ESCALACION</div>
                    <div style="color:#e2e8f0; font-size:0.9rem">{e['escalacion']}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander(f"Script / Guion para agentes — Segmento {seg}"):
            st.info(e["script"])
            st.caption(f"Referencia: {e['referencia']}")

    st.divider()
    st.markdown("#### Comparacion Rapida")
    comp = pd.DataFrame([
        {"Metrica": "Costo por contacto",     "ALTO": "S/ 0.10-0.30",   "MEDIO": "S/ 2.00-3.50",   "BAJO": "S/ 10-25"},
        {"Metrica": "Conversion objetivo",    "ALTO": ">= 20%",         "MEDIO": "PTP >= 30%",     "BAJO": "Settlement >= 15%"},
        {"Metrica": "Canal principal",        "ALTO": "WhatsApp / SMS", "MEDIO": "Marcador+Agente","BAJO": "Especialista/Legal"},
        {"Metrica": "Frecuencia maxima",      "ALTO": "2/semana",       "MEDIO": "3/dia",          "BAJO": "1/semana"},
        {"Metrica": "ROI estimado",           "ALTO": "400-600%",       "MEDIO": "150-300%",       "BAJO": "50-150%"},
    ])
    st.dataframe(comp, hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# PAGINA: ADMIN
# ─────────────────────────────────────────────────────────────────────────────

def page_admin():
    if st.session_state["user"]["rol"] != "admin":
        st.error("Acceso denegado. Solo para Administradores.")
        return

    st.markdown("## Panel de Administracion")
    st.divider()

    tab1, tab2, tab3 = st.tabs(["Usuarios del Sistema", "Crear Usuario", "Cambiar Contrasena"])

    with tab1:
        st.markdown("#### Lista de Usuarios")
        df_u = get_all_users()
        st.dataframe(
            df_u, hide_index=True, use_container_width=True,
            column_config={
                "activo": st.column_config.CheckboxColumn("Activo"),
                "rol":    st.column_config.SelectboxColumn("Rol", options=["admin","colaborador"]),
            },
        )
        st.markdown("#### Activar / Desactivar Usuario")
        cur = st.session_state["user"]["username"]
        opciones = [u for u in df_u["username"].tolist() if u != cur]
        if opciones:
            sel = st.selectbox("Selecciona usuario", opciones)
            if st.button(f"Cambiar estado de '{sel}'", type="primary"):
                toggle_user_status(sel)
                st.success(f"Estado de '{sel}' actualizado.")
                st.rerun()

    with tab2:
        st.markdown("#### Nuevo Usuario")
        with st.form("crear_usuario"):
            c1, c2 = st.columns(2)
            nu = c1.text_input("Username")
            nn = c2.text_input("Nombre completo")
            ne = c1.text_input("Email")
            nr = c2.selectbox("Rol", ["colaborador", "admin"])
            np_ = st.text_input("Contrasena", type="password")
            nc  = st.text_input("Confirmar contrasena", type="password")
            if st.form_submit_button("Crear Usuario", type="primary"):
                if np_ != nc:
                    st.error("Las contrasenas no coinciden.")
                elif not nu or not nn:
                    st.error("Username y nombre son obligatorios.")
                else:
                    ok, msg = create_user(nu, np_, nn, ne, nr)
                    (st.success if ok else st.error)(msg)

    with tab3:
        st.markdown("#### Cambiar Contrasena")
        df_u2 = get_all_users()
        with st.form("cambiar_pass"):
            us = st.selectbox("Usuario", df_u2["username"].tolist())
            p1 = st.text_input("Nueva contrasena", type="password")
            p2 = st.text_input("Confirmar contrasena", type="password")
            if st.form_submit_button("Actualizar Contrasena", type="primary"):
                if p1 != p2:
                    st.error("Las contrasenas no coinciden.")
                else:
                    ok, msg = update_password(us, p1)
                    (st.success if ok else st.error)(msg)


# ─────────────────────────────────────────────────────────────────────────────
# ROUTER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def _bootstrap_users():
    """Crea usuarios por defecto si la tabla esta vacia (primera vez en Supabase)."""
    try:
        existing = get_all_users()
        if len(existing) == 0:
            defaults = [
                ("admin",       "Admin2024!",  "Administrador", "admin@callcenter.com",      "admin"),
                ("supervisor",  "Super2024!",  "Supervisor",    "supervisor@callcenter.com", "admin"),
                ("colaborador", "Colab2024!",  "Colaborador",   "colab@callcenter.com",      "colaborador"),
            ]
            for username, password, nombre, email, rol in defaults:
                create_user(username, password, nombre, email, rol)
    except Exception:
        pass


def main():
    init_db()
    _bootstrap_users()
    if "user" not in st.session_state:
        show_login()
        return

    show_sidebar()
    routes = {
        "inicio":      page_inicio,
        "cargar":      page_cargar,
        "analisis":    page_analisis,
        "historial":   page_historial,
        "estrategias": page_estrategias,
        "admin":       page_admin,
    }
    routes.get(st.session_state.get("page", "inicio"), page_inicio)()


if __name__ == "__main__":
    main()
