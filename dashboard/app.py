"""
Dashboard de Scoring de Cobranza — Streamlit
=============================================
Ejecutar: streamlit run dashboard/app.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import joblib
import io

# ── Configuración de página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Score de Cobranza — Call Center",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

MODELS_DIR = Path("models")
DATA_DIR = Path("data")

SEGMENT_COLORS = {
    "ALTO": "#2ecc71",
    "MEDIO": "#f39c12",
    "BAJO": "#e74c3c",
}

# ── Estilos CSS personalizados ────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px; padding: 20px; text-align: center;
        border-left: 4px solid;
    }
    .metric-value { font-size: 2.2rem; font-weight: 700; color: white; }
    .metric-label { font-size: 0.85rem; color: #aaa; margin-top: 4px; }
    .stAlert { border-radius: 8px; }
    h1, h2, h3 { color: #ecf0f1; }
</style>
""", unsafe_allow_html=True)


# ── Carga del modelo ──────────────────────────────────────────────────────────
@st.cache_resource
def load_model():
    model_path = MODELS_DIR / "pipeline_random_forest.pkl"
    if model_path.exists():
        return joblib.load(model_path)
    return None


@st.cache_data
def load_demo_data():
    demo_path = DATA_DIR / "cartera_scored.csv"
    if demo_path.exists():
        return pd.read_csv(demo_path)
    return None


def score_new_data(df_raw: pd.DataFrame, pipeline) -> pd.DataFrame:
    from model import score_portfolio
    return score_portfolio(df_raw, pipeline)


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/phone-call.png", width=60)
    st.title("Score de Cobranza")
    st.caption("Sistema Predictivo — Call Center")
    st.divider()

    st.subheader("Cargar Cartera")
    uploaded_file = st.file_uploader(
        "Sube tu archivo de cartera",
        type=["csv", "xlsx", "xls"],
        help="Acepta Excel (.xlsx, .xls) o CSV. Debe incluir las columnas de la tabla maestra.",
    )

    st.divider()
    st.subheader("Filtros")
    segmentos_sel = st.multiselect(
        "Segmentos",
        options=["ALTO", "MEDIO", "BAJO"],
        default=["ALTO", "MEDIO", "BAJO"],
    )
    score_range = st.slider("Rango de Score", 1, 100, (1, 100))
    st.divider()
    st.caption("v1.0 — MVP Call Center Cuzco")


# ── CUERPO PRINCIPAL ──────────────────────────────────────────────────────────
st.title("📊 Dashboard de Score Predictivo de Cobranza")
st.caption(f"Actualizado: {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')}")

pipeline = load_model()

# Determinar fuente de datos
if uploaded_file is not None and pipeline is not None:
    with st.spinner("Procesando cartera y calculando scores..."):
        name = uploaded_file.name.lower()
        if name.endswith(".csv"):
            df_raw = pd.read_csv(uploaded_file)
        else:
            df_raw = pd.read_excel(uploaded_file)
        df_scored = score_new_data(df_raw, pipeline)
    st.success(f"Cartera procesada: {len(df_scored):,} clientes")
else:
    df_scored = load_demo_data()
    if df_scored is None:
        st.warning("No se encontró modelo ni datos. Ejecuta `python src/main.py` primero.")
        st.stop()
    if pipeline is None:
        st.info("Mostrando datos de demo. Para procesar nueva cartera, entrena el modelo primero.")

# Aplicar filtros
df_filtered = df_scored[
    (df_scored["segmento"].isin(segmentos_sel)) &
    (df_scored["score_operativo"] >= score_range[0]) &
    (df_scored["score_operativo"] <= score_range[1])
].copy()

# ── KPIs PRINCIPALES ──────────────────────────────────────────────────────────
st.subheader("Resumen Ejecutivo de la Cartera")
col1, col2, col3, col4, col5 = st.columns(5)

total = len(df_filtered)
alto = (df_filtered["segmento"] == "ALTO").sum()
medio = (df_filtered["segmento"] == "MEDIO").sum()
bajo = (df_filtered["segmento"] == "BAJO").sum()
score_prom = df_filtered["score_operativo"].mean()

with col1:
    st.metric("Total Clientes", f"{total:,}", help="Cartera filtrada actual")
with col2:
    st.metric("Score Promedio", f"{score_prom:.1f}", help="Media del score operativo")
with col3:
    st.metric("🟢 Segmento ALTO", f"{alto:,}", f"{alto/total*100:.1f}%")
with col4:
    st.metric("🟡 Segmento MEDIO", f"{medio:,}", f"{medio/total*100:.1f}%")
with col5:
    st.metric("🔴 Segmento BAJO", f"{bajo:,}", f"{bajo/total*100:.1f}%")

st.divider()

# ── GRÁFICOS ──────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "📈 Distribución de Score",
    "🎯 Segmentación Operativa",
    "🔍 Análisis de Variables",
    "📋 Lista para Dialer",
])

with tab1:
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Histograma de Score Operativo")
        fig_hist = px.histogram(
            df_filtered,
            x="score_operativo",
            nbins=50,
            color="segmento",
            color_discrete_map=SEGMENT_COLORS,
            labels={"score_operativo": "Score (1-100)", "count": "Clientes"},
            template="plotly_dark",
        )
        fig_hist.update_layout(bargap=0.1, height=350)
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_r:
        st.subheader("Distribución de Probabilidad de Pago")
        fig_prob = px.box(
            df_filtered,
            x="segmento",
            y="prob_pago",
            color="segmento",
            color_discrete_map=SEGMENT_COLORS,
            labels={"prob_pago": "Probabilidad de Pago", "segmento": "Segmento"},
            template="plotly_dark",
        )
        fig_prob.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig_prob, use_container_width=True)


with tab2:
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Composición de la Cartera")
        seg_counts = df_filtered["segmento"].value_counts().reset_index()
        seg_counts.columns = ["Segmento", "Clientes"]
        fig_pie = px.pie(
            seg_counts,
            values="Clientes",
            names="Segmento",
            color="Segmento",
            color_discrete_map=SEGMENT_COLORS,
            hole=0.45,
            template="plotly_dark",
        )
        fig_pie.update_layout(height=380)
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_r:
        st.subheader("Estrategia Operativa por Segmento")

        strategy_data = pd.DataFrame({
            "Segmento": ["🟢 ALTO", "🟡 MEDIO", "🔴 BAJO"],
            "Score": ["67 – 100", "34 – 66", "1 – 33"],
            "Estrategia": [
                "SMS / WhatsApp / Bot",
                "Agente + Marcador Predictivo",
                "Especialista / Pre-Legal",
            ],
            "Objetivo": [
                "Recuperación masiva low-cost",
                "Negociación activa y planes de pago",
                "Acuerdo final o derivación a agencia",
            ],
            "Clientes": [alto, medio, bajo],
        })

        st.dataframe(
            strategy_data,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Clientes": st.column_config.ProgressColumn(
                    "Clientes", min_value=0, max_value=total
                )
            },
        )

        if "saldo_total" in df_filtered.columns:
            st.subheader("Saldo Total por Segmento")
            saldo_seg = df_filtered.groupby("segmento")["saldo_total"].sum().reset_index()
            fig_bar = px.bar(
                saldo_seg,
                x="segmento",
                y="saldo_total",
                color="segmento",
                color_discrete_map=SEGMENT_COLORS,
                text_auto=".2s",
                template="plotly_dark",
                labels={"saldo_total": "Saldo Total (S/)", "segmento": "Segmento"},
            )
            fig_bar.update_layout(height=280, showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)


with tab3:
    col_l, col_r = st.columns(2)

    if "dpd" in df_filtered.columns:
        with col_l:
            st.subheader("Score vs DPD (días en mora)")
            fig_scatter = px.scatter(
                df_filtered.sample(min(1000, len(df_filtered))),
                x="dpd",
                y="score_operativo",
                color="segmento",
                color_discrete_map=SEGMENT_COLORS,
                opacity=0.6,
                template="plotly_dark",
                labels={"dpd": "DPD", "score_operativo": "Score Operativo"},
            )
            fig_scatter.update_layout(height=350)
            st.plotly_chart(fig_scatter, use_container_width=True)

    if "rpc_rate" in df_filtered.columns:
        with col_r:
            st.subheader("Score vs RPC Rate")
            fig_scatter2 = px.scatter(
                df_filtered.sample(min(1000, len(df_filtered))),
                x="rpc_rate",
                y="score_operativo",
                color="segmento",
                color_discrete_map=SEGMENT_COLORS,
                opacity=0.6,
                template="plotly_dark",
                labels={"rpc_rate": "Tasa de Contacto Efectivo", "score_operativo": "Score Operativo"},
            )
            fig_scatter2.update_layout(height=350)
            st.plotly_chart(fig_scatter2, use_container_width=True)


with tab4:
    st.subheader("Lista Segmentada para Exportar al Dialer")

    # Columnas clave para el marcador predictivo
    dialer_cols = [
        c for c in [
            "cliente_id", "score_operativo", "segmento", "estrategia",
            "prioridad_dialer", "prob_pago", "dpd", "saldo_total",
            "bucket_mora", "rpc_rate", "ultimo_estado_marcado",
        ]
        if c in df_filtered.columns
    ]

    df_dialer = df_filtered[dialer_cols].sort_values("score_operativo", ascending=False)

    # Resaltado por segmento
    def highlight_segment(row):
        colors = {"ALTO": "background-color: #1a3a1a", "MEDIO": "#3a2e00", "BAJO": "#3a0a0a"}
        return [colors.get(row.get("segmento", ""), "")] * len(row)

    st.dataframe(
        df_dialer.head(500),
        use_container_width=True,
        hide_index=True,
        column_config={
            "score_operativo": st.column_config.ProgressColumn(
                "Score", min_value=1, max_value=100
            ),
            "prob_pago": st.column_config.NumberColumn("Prob. Pago", format="%.2%"),
        },
    )

    st.caption(f"Mostrando primeros 500 de {len(df_dialer):,} registros ordenados por score.")

    # ── Exportación ────────────────────────────────────────────────────────────
    col_exp1, col_exp2 = st.columns(2)

    with col_exp1:
        csv_buffer = io.StringIO()
        df_dialer.to_csv(csv_buffer, index=False)
        st.download_button(
            label="⬇️ Descargar CSV para Dialer",
            data=csv_buffer.getvalue(),
            file_name=f"cartera_scored_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )

    with col_exp2:
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df_dialer.to_excel(writer, index=False, sheet_name="Cartera Scored")
            df_filtered.groupby("segmento").agg(
                clientes=("cliente_id", "count"),
                score_prom=("score_operativo", "mean"),
                prob_pago_prom=("prob_pago", "mean"),
            ).to_excel(writer, sheet_name="Resumen Segmentos")
        st.download_button(
            label="⬇️ Descargar Excel Completo",
            data=excel_buffer.getvalue(),
            file_name=f"reporte_cobranza_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
