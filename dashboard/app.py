"""
Dashboard de Cobranza — Sistema Integral con Autenticación y Base de Datos
===========================================================================
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

# ── Configuración ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Score de Cobranza",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

MODELS_DIR = Path("models")
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

COLORES = {"ALTO": "#27ae60", "MEDIO": "#f39c12", "BAJO": "#e74c3c"}

# ── Estrategias Globales (Metodologías de los mejores call centers del mundo) ─
ESTRATEGIAS = {
    "ALTO": {
        "canal":      "WhatsApp Business / SMS / Email / IVR Autopago",
        "accion":     "Recordatorio digital automático con link de pago seguro",
        "oferta":     "Facilidad: 2 cuotas sin interés adicional / Autopago inmediato",
        "frecuencia": "Máx. 2 contactos digitales por semana (cumple normativa SBS)",
        "escalacion": "Sin pago en 7 días → Escalar a MEDIO",
        "script":     "Hola [Nombre], tienes un saldo pendiente de S/[monto]. Puedes pagarlo hoy aquí: [link]. Tu historial crediticio te lo agradecerá.",
        "kpis":       "Conversión digital ≥20% | Costo por contacto S/ 0.10-0.30 | ROI ≥400%",
        "referencia": "Metodología Hoist Finance / Interbank Perú — Digital First Collection",
    },
    "MEDIO": {
        "canal":      "Marcador Predictivo + Agente Humano (AMD activado)",
        "accion":     "Negociación activa con script ACED + registro de Promesa de Pago (PTP)",
        "oferta":     "Plan 3-6 cuotas / Condonación intereses moratorios / Refinanciamiento",
        "frecuencia": "Máx. 3 intentos/día | Best time: 9-11am y 6-8pm L-V / 9-12pm Sáb",
        "escalacion": "2 PTPs rotas → Escalar a BAJO | PTP honrada → Mantener MEDIO",
        "script":     "ACED: A-cknowledge (reconocer deuda) → C-reate urgency → E-mpathize → D-eal (comprometer fecha/monto). Oferta: 'Puedo condonarle los intereses si paga el capital hoy.'",
        "kpis":       "RPC ≥45% | PTP Rate ≥30% | Kept PTP ≥65% | Costo S/ 2-3.50",
        "referencia": "Metodología FICO TRIAD / COFACE / Encore Capital — Human-Assisted Negotiation",
    },
    "BAJO": {
        "canal":      "Especialista Senior / Notaría / Agencia Externa / Pre-Legal",
        "accion":     "Skip Tracing → Carta Notarial → Oferta Settlement → Derivación",
        "oferta":     "Score 20-33: Skip tracing | Score 10-19: Quita 20-40% | Score 1-9: Pre-legal / Venta",
        "frecuencia": "Gestión semanal especializada. Decisión por DPD y saldo.",
        "escalacion": "DPD>90 sin contacto: Agencia externa | DPD>180: Evaluar venta 5-15 ctvs/sol",
        "script":     "Carta notarial formal: 'Notificamos que de no regularizar su deuda de S/[monto] en 15 días hábiles, iniciaremos proceso judicial y registro en centrales de riesgo SBS/Equifax.'",
        "kpis":       "Skip tracing ≥25% | Settlement aceptado ≥15% | Recovery ≥8% | Costo S/ 10-25",
        "referencia": "Metodología Intrum / Portfolio Recovery Associates / COFACE — Intensive & Legal",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def load_model():
    path = MODELS_DIR / "pipeline_random_forest.pkl"
    return joblib.load(path) if path.exists() else None


def score_dataframe(df_raw: pd.DataFrame, pipeline) -> pd.DataFrame:
    """Aplica el modelo y enriquece con estrategia detallada."""
    from model import score_portfolio
    df_scored = score_portfolio(df_raw, pipeline)

    df_scored["estrategia_canal"]  = df_scored["segmento"].map(lambda s: ESTRATEGIAS.get(s, {}).get("canal", ""))
    df_scored["estrategia_accion"] = df_scored["segmento"].map(lambda s: ESTRATEGIAS.get(s, {}).get("accion", ""))
    df_scored["estrategia_oferta"] = df_scored["segmento"].map(lambda s: ESTRATEGIAS.get(s, {}).get("oferta", ""))
    df_scored["frecuencia_contacto"] = df_scored["segmento"].map(lambda s: ESTRATEGIAS.get(s, {}).get("frecuencia", ""))
    return df_scored


def process_upload(df_raw: pd.DataFrame, pipeline, usuario: str, filename: str):
    """
    Flujo principal de carga:
    1. Identifica clientes ya en DB vs nuevos
    2. Aplica modelo a todos con datos frescos
    3. Guarda en DB
    4. Retorna DataFrame completo + estadísticas
    """
    # Asegurar columna cliente_id
    if "cliente_id" not in df_raw.columns:
        posibles = [c for c in df_raw.columns if "id" in c.lower() or "cliente" in c.lower()]
        if posibles:
            df_raw = df_raw.rename(columns={posibles[0]: "cliente_id"})
        else:
            df_raw.insert(0, "cliente_id", [f"CLI-{i:06d}" for i in range(1, len(df_raw) + 1)])

    ids = df_raw["cliente_id"].astype(str).tolist()

    # Verificar en BD
    df_existentes = get_clientes_by_ids(ids)
    ids_conocidos = set(df_existentes["cliente_id"].tolist()) if len(df_existentes) > 0 else set()

    n_conocidos = sum(1 for i in ids if i in ids_conocidos)
    n_nuevos = len(ids) - n_conocidos

    # Score a TODOS con datos frescos (más preciso que usar score guardado)
    df_scored = score_dataframe(df_raw, pipeline)
    df_scored["es_nuevo"] = ~df_scored["cliente_id"].isin(ids_conocidos)
    df_scored["estado_carga"] = df_scored["es_nuevo"].map({True: "🆕 Nuevo", False: "✅ Actualizado"})

    # Persistir en BD
    carga_id = log_carga(usuario, filename, len(df_scored), n_nuevos, n_conocidos)
    upsert_clientes_batch(df_scored, carga_id)

    stats = {"total": len(df_scored), "nuevos": n_nuevos, "conocidos": n_conocidos, "carga_id": carga_id}
    return df_scored, stats


def export_excel(df: pd.DataFrame) -> bytes:
    """Genera Excel multi-hoja para el Dialer."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Hoja 1: Cartera completa
        df.to_excel(writer, index=False, sheet_name="Cartera Completa")

        # Hoja 2: Por segmento
        for seg in ["ALTO", "MEDIO", "BAJO"]:
            sub = df[df["segmento"] == seg]
            if len(sub) > 0:
                sub.to_excel(writer, index=False, sheet_name=f"Segmento {seg}")

        # Hoja 3: Resumen
        resumen = (
            df.groupby("segmento")
            .agg(clientes=("cliente_id", "count"),
                 score_promedio=("score_operativo", "mean"),
                 prob_pago_promedio=("prob_pago", "mean"),
                 saldo_total=("saldo_total", "sum"))
            .round(2)
        )
        resumen["pct_cartera"] = (resumen["clientes"] / len(df) * 100).round(1)
        resumen.to_excel(writer, sheet_name="Resumen Ejecutivo")

        # Hoja 4: Guía de estrategias
        guia = pd.DataFrame([
            {"Segmento": seg,
             "Canal": ESTRATEGIAS[seg]["canal"],
             "Acción": ESTRATEGIAS[seg]["accion"],
             "Oferta": ESTRATEGIAS[seg]["oferta"],
             "Frecuencia": ESTRATEGIAS[seg]["frecuencia"],
             "Escalación": ESTRATEGIAS[seg]["escalacion"],
             "KPIs Objetivo": ESTRATEGIAS[seg]["kpis"]}
            for seg in ["ALTO", "MEDIO", "BAJO"]
        ])
        guia.to_excel(writer, index=False, sheet_name="Guía Estrategias")

    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────

def show_login():
    init_db()
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("## 📊 Sistema de Cobranza")
        st.markdown("**Call Center Cuzco** — Score Predictivo")
        st.divider()

        with st.form("login_form"):
            username = st.text_input("Usuario", placeholder="Ingresa tu usuario")
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            submit = st.form_submit_button("Ingresar", use_container_width=True, type="primary")

        if submit:
            if not username or not password:
                st.error("Completa usuario y contraseña.")
            else:
                user = authenticate(username, password)
                if user:
                    st.session_state["user"] = user
                    st.session_state["page"] = "inicio"
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")

        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("¿Problemas de acceso? Contacta al Administrador.")


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

def show_sidebar():
    user = st.session_state["user"]
    rol = user["rol"]

    with st.sidebar:
        st.markdown(f"### 👤 {user['nombre']}")
        badge = "🔴 Admin" if rol == "admin" else "🟡 Colaborador"
        st.caption(badge)
        st.divider()

        st.subheader("Navegación")
        pages = {
            "inicio":      "🏠 Inicio",
            "cargar":      "📤 Cargar Cartera",
            "analisis":    "📊 Análisis",
            "historial":   "📋 Historial de Cargas",
            "estrategias": "🎯 Estrategias",
        }
        if rol == "admin":
            pages["admin"] = "⚙️ Panel Admin"

        current = st.session_state.get("page", "inicio")
        for key, label in pages.items():
            if st.button(label, use_container_width=True,
                         type="primary" if current == key else "secondary"):
                st.session_state["page"] = key
                st.rerun()

        st.divider()
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.clear()
            st.rerun()

        st.caption("v2.0 — Call Center Cuzco")


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: INICIO
# ─────────────────────────────────────────────────────────────────────────────

def page_inicio():
    st.title("🏠 Inicio — Resumen de la Base de Datos")
    st.caption(f"Actualizado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    metrics = get_metricas_globales()
    total = metrics["total_clientes"]

    if total == 0:
        st.info("La base de datos está vacía. Ve a **Cargar Cartera** para procesar tu primera cartera.")
        return

    seg = metrics["por_segmento"]
    alto  = seg.get("ALTO",  {}).get("count", 0)
    medio = seg.get("MEDIO", {}).get("count", 0)
    bajo  = seg.get("BAJO",  {}).get("count", 0)

    # KPIs
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total en BD", f"{total:,}")
    c2.metric("Score Promedio", f"{metrics['avg_score']}")
    c3.metric("🟢 ALTO", f"{alto:,}", f"{alto/total*100:.1f}%" if total else "")
    c4.metric("🟡 MEDIO", f"{medio:,}", f"{medio/total*100:.1f}%" if total else "")
    c5.metric("🔴 BAJO", f"{bajo:,}", f"{bajo/total*100:.1f}%" if total else "")
    c6.metric("Total Cargas", f"{metrics['total_cargas']}")

    st.divider()

    df_db = get_all_clientes_df(limit=10000)
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("Composición de la Cartera en BD")
        data_pie = {"Segmento": list(seg.keys()), "Clientes": [v["count"] for v in seg.values()]}
        fig = px.pie(data_pie, values="Clientes", names="Segmento",
                     color="Segmento", color_discrete_map=COLORES,
                     hole=0.45, template="plotly_dark")
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Distribución de Score en BD")
        if len(df_db) > 0:
            fig2 = px.histogram(df_db, x="score_operativo", nbins=40,
                                color="segmento", color_discrete_map=COLORES,
                                template="plotly_dark",
                                labels={"score_operativo": "Score (1-100)"})
            fig2.update_layout(height=350, bargap=0.05)
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Saldo de Cartera por Segmento")
    saldo_data = [{"Segmento": k, "Saldo Total (S/)": v["saldo"]} for k, v in seg.items()]
    if saldo_data:
        fig3 = px.bar(pd.DataFrame(saldo_data), x="Segmento", y="Saldo Total (S/)",
                      color="Segmento", color_discrete_map=COLORES,
                      text_auto=".3s", template="plotly_dark")
        fig3.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig3, use_container_width=True)

    st.subheader("Últimas Cargas")
    df_cargas = get_cargas_historico()
    if len(df_cargas) > 0:
        st.dataframe(df_cargas.head(8), hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: CARGAR CARTERA
# ─────────────────────────────────────────────────────────────────────────────

def page_cargar():
    st.title("📤 Cargar Cartera")
    st.caption("Sube tu Excel del día. El sistema identifica automáticamente clientes ya registrados.")

    pipeline = load_model()
    if pipeline is None:
        st.error("Modelo no encontrado. Ejecuta primero: `python src/main.py`")
        return

    uploaded = st.file_uploader(
        "Selecciona tu archivo de cartera",
        type=["xlsx", "xls", "csv"],
        help="Acepta Excel (.xlsx, .xls) y CSV. Columna requerida: cliente_id (o similar).",
    )

    if uploaded is None:
        st.info("Sube un archivo para comenzar. El proceso toma pocos segundos incluso con 30,000+ cuentas.")
        with st.expander("📋 Columnas esperadas en el archivo"):
            st.markdown("""
| Columna | Tipo | Descripción |
|---|---|---|
| `cliente_id` | Texto | Identificador único del cliente |
| `dpd` | Número | Días en mora |
| `saldo_total` | Número | Saldo vencido total |
| `bucket_mora` | Texto | B1, B2, B3, B4 |
| `rpc_rate` | Decimal | Tasa de contacto efectivo (0.0 a 1.0) |
| `promesas_cumplidas` | Número | Promesas de pago honradas |
| `promesas_rotas` | Número | Promesas incumplidas |
| `dias_ultimo_contacto` | Número | Días desde último contacto |
| `ultimo_estado_marcado` | Texto | RPC_PROMESA, NO_CONTESTA, etc. |
| `estado_laboral` | Texto | Dependiente, Independiente, etc. |
| `ingreso_mensual` | Número | Ingreso declarado |
| `ratio_deuda_ingreso` | Decimal | deuda / (ingreso × 12) |

*Columnas faltantes se imputan con medianas del modelo de entrenamiento.*
            """)
        return

    # Leer archivo
    try:
        name = uploaded.name.lower()
        if name.endswith(".csv"):
            df_raw = pd.read_csv(uploaded, low_memory=False)
        else:
            df_raw = pd.read_excel(uploaded)
    except Exception as e:
        st.error(f"Error al leer el archivo: {e}")
        return

    st.success(f"Archivo cargado: **{uploaded.name}** — {len(df_raw):,} registros · {df_raw.shape[1]} columnas")

    with st.expander("Vista previa (primeros 5 registros)"):
        st.dataframe(df_raw.head(5), use_container_width=True)

    if st.button("🚀 Procesar Cartera y Calcular Scores", type="primary", use_container_width=True):
        usuario = st.session_state["user"]["username"]

        with st.spinner(f"Procesando {len(df_raw):,} cuentas..."):
            progress = st.progress(0, text="Verificando en base de datos...")
            try:
                progress.progress(20, text="Identificando clientes conocidos vs nuevos...")
                df_result, stats = process_upload(df_raw, pipeline, usuario, uploaded.name)
                progress.progress(80, text="Guardando en base de datos...")
                progress.progress(100, text="¡Listo!")
            except Exception as e:
                st.error(f"Error durante el procesamiento: {e}")
                import traceback
                st.code(traceback.format_exc())
                return

        # Estadísticas del proceso
        st.divider()
        st.subheader("Resultado del Procesamiento")
        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("Total Procesado", f"{stats['total']:,}")
        rc2.metric("✅ Ya en BD (actualizados)", f"{stats['conocidos']:,}",
                   f"{stats['conocidos']/stats['total']*100:.1f}%" if stats['total'] else "")
        rc3.metric("🆕 Clientes Nuevos", f"{stats['nuevos']:,}",
                   f"{stats['nuevos']/stats['total']*100:.1f}%" if stats['total'] else "")

        # Distribución por segmento
        seg_counts = df_result["segmento"].value_counts()
        c1, c2, c3 = st.columns(3)
        for col, seg in zip([c1, c2, c3], ["ALTO", "MEDIO", "BAJO"]):
            n = seg_counts.get(seg, 0)
            col.metric(f"Segmento {seg}", f"{n:,}", f"{n/len(df_result)*100:.1f}%")

        st.divider()

        # Tabla de resultados
        st.subheader("Cartera Segmentada")
        cols_mostrar = [c for c in [
            "cliente_id", "score_operativo", "segmento", "prob_pago",
            "estrategia_canal", "estrategia_oferta", "dpd", "saldo_total",
            "bucket_mora", "rpc_rate", "estado_carga",
        ] if c in df_result.columns]

        st.dataframe(
            df_result[cols_mostrar].sort_values("score_operativo", ascending=False).head(500),
            use_container_width=True,
            hide_index=True,
            column_config={
                "score_operativo": st.column_config.ProgressColumn("Score", min_value=1, max_value=100),
                "prob_pago": st.column_config.NumberColumn("Prob. Pago", format="%.1%"),
            },
        )
        st.caption(f"Mostrando primeros 500 de {len(df_result):,} registros ordenados por score.")

        # Descarga
        st.divider()
        excel_bytes = export_excel(df_result)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")

        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "⬇️ Descargar Excel Completo (4 hojas)",
                data=excel_bytes,
                file_name=f"cartera_scored_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
        with dl2:
            csv_buf = io.StringIO()
            df_result.to_csv(csv_buf, index=False)
            st.download_button(
                "⬇️ Descargar CSV para Dialer",
                data=csv_buf.getvalue(),
                file_name=f"dialer_{timestamp}.csv",
                mime="text/csv",
                use_container_width=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: ANÁLISIS
# ─────────────────────────────────────────────────────────────────────────────

def page_analisis():
    st.title("📊 Análisis de Cartera")

    df = get_all_clientes_df(limit=30000)
    if len(df) == 0:
        st.info("Carga tu primera cartera para ver análisis.")
        return

    # Filtros
    with st.expander("Filtros", expanded=False):
        f1, f2 = st.columns(2)
        segs = f1.multiselect("Segmentos", ["ALTO", "MEDIO", "BAJO"], default=["ALTO", "MEDIO", "BAJO"])
        score_range = f2.slider("Rango de Score", 1, 100, (1, 100))

    df_f = df[df["segmento"].isin(segs) & df["score_operativo"].between(*score_range)]
    st.caption(f"{len(df_f):,} clientes en la selección")

    tab1, tab2, tab3 = st.tabs(["Score y Mora", "Contactabilidad", "Saldo y Riesgo"])

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Score vs DPD")
            fig = px.scatter(df_f.sample(min(2000, len(df_f))), x="dpd", y="score_operativo",
                             color="segmento", color_discrete_map=COLORES, opacity=0.6,
                             template="plotly_dark",
                             labels={"dpd": "Días en mora (DPD)", "score_operativo": "Score"})
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("Distribución por Bucket de Mora")
            if "bucket_mora" in df_f.columns:
                fig2 = px.histogram(df_f, x="bucket_mora", color="segmento",
                                    color_discrete_map=COLORES, barmode="group",
                                    template="plotly_dark",
                                    category_orders={"bucket_mora": ["B1", "B2", "B3", "B4"]})
                st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("RPC Rate por Segmento")
            if "rpc_rate" in df_f.columns:
                fig3 = px.box(df_f, x="segmento", y="rpc_rate", color="segmento",
                              color_discrete_map=COLORES, template="plotly_dark",
                              labels={"rpc_rate": "Tasa de Contacto Efectivo"})
                fig3.update_layout(showlegend=False)
                st.plotly_chart(fig3, use_container_width=True)
        with c2:
            st.subheader("Último Estado de Marcado")
            if "ultimo_estado_marcado" in df_f.columns:
                estado_cnt = df_f["ultimo_estado_marcado"].value_counts().head(8).reset_index()
                estado_cnt.columns = ["Estado", "Clientes"]
                fig4 = px.bar(estado_cnt, x="Clientes", y="Estado", orientation="h",
                              template="plotly_dark", color="Clientes",
                              color_continuous_scale="Blues")
                fig4.update_layout(showlegend=False, yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig4, use_container_width=True)

    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Saldo Total por Segmento")
            if "saldo_total" in df_f.columns:
                saldo = df_f.groupby("segmento")["saldo_total"].sum().reset_index()
                fig5 = px.bar(saldo, x="segmento", y="saldo_total", color="segmento",
                              color_discrete_map=COLORES, text_auto=".3s",
                              template="plotly_dark",
                              labels={"saldo_total": "Saldo Total (S/)"})
                fig5.update_layout(showlegend=False)
                st.plotly_chart(fig5, use_container_width=True)
        with c2:
            st.subheader("Probabilidad de Pago Promedio")
            fig6 = px.box(df_f, x="segmento", y="prob_pago", color="segmento",
                          color_discrete_map=COLORES, template="plotly_dark",
                          labels={"prob_pago": "Probabilidad de Pago"})
            fig6.update_layout(showlegend=False)
            st.plotly_chart(fig6, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: HISTORIAL
# ─────────────────────────────────────────────────────────────────────────────

def page_historial():
    st.title("📋 Historial de Cargas")

    df = get_cargas_historico()
    if len(df) == 0:
        st.info("Sin cargas registradas aún.")
        return

    total_procesado = df["total_registros"].sum()
    total_nuevos = df["registros_nuevos"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Cargas", f"{len(df):,}")
    c2.metric("Total Registros Procesados", f"{total_procesado:,}")
    c3.metric("Clientes Nuevos Registrados", f"{total_nuevos:,}")

    st.divider()
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "total_registros":        st.column_config.NumberColumn("Total"),
            "registros_nuevos":       st.column_config.NumberColumn("Nuevos"),
            "registros_actualizados": st.column_config.NumberColumn("Actualizados"),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: ESTRATEGIAS
# ─────────────────────────────────────────────────────────────────────────────

def page_estrategias():
    st.title("🎯 Estrategias de Cobranza de Clase Mundial")
    st.caption("Basadas en metodologías de Hoist Finance, Encore Capital, FICO TRIAD, COFACE e Intrum.")

    for seg, color_hex in [("ALTO", "#27ae60"), ("MEDIO", "#f39c12"), ("BAJO", "#e74c3c")]:
        e = ESTRATEGIAS[seg]
        score_rng = {"ALTO": "67–100", "MEDIO": "34–66", "BAJO": "1–33"}[seg]

        st.markdown(f"""
<div style="border-left: 5px solid {color_hex}; padding: 16px 20px; background: #1a1a2e;
     border-radius: 8px; margin-bottom: 20px;">
<h3 style="color:{color_hex}; margin:0">Segmento {seg} &nbsp;|&nbsp; Score {score_rng}</h3>
</div>
""", unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**📱 Canal:** {e['canal']}")
            st.markdown(f"**⚡ Acción:** {e['accion']}")
            st.markdown(f"**💰 Oferta:** {e['oferta']}")
            st.markdown(f"**📅 Frecuencia:** {e['frecuencia']}")
        with c2:
            st.markdown(f"**📈 KPIs Objetivo:** {e['kpis']}")
            st.markdown(f"**⬆️ Escalación:** {e['escalacion']}")
            st.markdown(f"**📚 Referencia:** {e['referencia']}")

        with st.expander(f"📝 Script / Guión para Segmento {seg}"):
            st.info(e["script"])

        st.divider()

    st.subheader("Tabla de Comparación Rápida")
    comp = pd.DataFrame([
        {"Métrica": "Costo por contacto",
         "ALTO": "S/ 0.10–0.30", "MEDIO": "S/ 2.00–3.50", "BAJO": "S/ 10–25"},
        {"Métrica": "Tasa de conversión objetivo",
         "ALTO": "≥ 20%", "MEDIO": "PTP ≥ 30%", "BAJO": "Settlement ≥ 15%"},
        {"Métrica": "Canal principal",
         "ALTO": "WhatsApp / SMS", "MEDIO": "Marcador + Agente", "BAJO": "Especialista / Legal"},
        {"Métrica": "Frecuencia máxima",
         "ALTO": "2/semana", "MEDIO": "3/día (máx)", "BAJO": "1/semana"},
        {"Métrica": "ROI estimado",
         "ALTO": "400–600%", "MEDIO": "150–300%", "BAJO": "50–150%"},
    ])
    st.dataframe(comp, hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA: ADMIN
# ─────────────────────────────────────────────────────────────────────────────

def page_admin():
    if st.session_state["user"]["rol"] != "admin":
        st.error("Acceso denegado. Solo para Administradores.")
        return

    st.title("⚙️ Panel de Administración")
    tab1, tab2, tab3 = st.tabs(["👥 Usuarios", "➕ Crear Usuario", "🔑 Cambiar Contraseña"])

    with tab1:
        st.subheader("Usuarios del Sistema")
        df_users = get_all_users()
        st.dataframe(
            df_users,
            hide_index=True,
            use_container_width=True,
            column_config={
                "activo": st.column_config.CheckboxColumn("Activo"),
                "rol": st.column_config.SelectboxColumn("Rol", options=["admin", "colaborador"]),
            },
        )

        st.subheader("Activar / Desactivar Usuario")
        usernames = df_users["username"].tolist()
        current_user = st.session_state["user"]["username"]
        opciones = [u for u in usernames if u != current_user]
        if opciones:
            sel = st.selectbox("Selecciona usuario", opciones)
            if st.button(f"Cambiar estado de '{sel}'"):
                toggle_user_status(sel)
                st.success(f"Estado de '{sel}' cambiado.")
                st.rerun()

    with tab2:
        st.subheader("Crear Nuevo Usuario")
        with st.form("crear_usuario"):
            col1, col2 = st.columns(2)
            nuevo_user = col1.text_input("Username")
            nuevo_nombre = col2.text_input("Nombre completo")
            nuevo_email = col1.text_input("Email")
            nuevo_rol = col2.selectbox("Rol", ["colaborador", "admin"])
            nueva_pass = st.text_input("Contraseña", type="password")
            confirmar_pass = st.text_input("Confirmar contraseña", type="password")
            crear = st.form_submit_button("Crear Usuario", type="primary")

        if crear:
            if nueva_pass != confirmar_pass:
                st.error("Las contraseñas no coinciden.")
            elif not nuevo_user or not nuevo_nombre:
                st.error("Username y nombre son obligatorios.")
            else:
                ok, msg = create_user(nuevo_user, nueva_pass, nuevo_nombre, nuevo_email, nuevo_rol)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

    with tab3:
        st.subheader("Cambiar Contraseña de Usuario")
        df_users = get_all_users()
        with st.form("cambiar_pass"):
            user_sel = st.selectbox("Usuario", df_users["username"].tolist())
            pass_nueva = st.text_input("Nueva contraseña", type="password")
            pass_conf = st.text_input("Confirmar contraseña", type="password")
            cambiar = st.form_submit_button("Actualizar Contraseña", type="primary")

        if cambiar:
            if pass_nueva != pass_conf:
                st.error("Las contraseñas no coinciden.")
            else:
                ok, msg = update_password(user_sel, pass_nueva)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ROUTER
# ─────────────────────────────────────────────────────────────────────────────

def main():
    init_db()

    if "user" not in st.session_state:
        show_login()
        return

    show_sidebar()

    page = st.session_state.get("page", "inicio")
    routes = {
        "inicio":      page_inicio,
        "cargar":      page_cargar,
        "analisis":    page_analisis,
        "historial":   page_historial,
        "estrategias": page_estrategias,
        "admin":       page_admin,
    }
    routes.get(page, page_inicio)()


if __name__ == "__main__":
    main()
