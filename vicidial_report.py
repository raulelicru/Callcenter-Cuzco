"""
Reporte de Eficiencia Vicidial
Sube tu archivo de llamadas y obtén el análisis en segundos.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
from datetime import datetime, timedelta

# ─── Configuración de página ────────────────────────────────────────────────
st.set_page_config(
    page_title="Reporte Vicidial | Call Center Cuzco",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Estilos ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] { background: #0f1117; }
  .kpi-card {
    background: #1e2130; border-radius: 12px; padding: 20px 24px;
    border-left: 4px solid #3b82f6; margin-bottom: 8px;
  }
  .kpi-card.red   { border-left-color: #ef4444; }
  .kpi-card.green { border-left-color: #22c55e; }
  .kpi-card.amber { border-left-color: #f59e0b; }
  .kpi-label { color: #9ca3af; font-size: 13px; margin-bottom: 4px; }
  .kpi-value { color: #f9fafb; font-size: 28px; font-weight: 700; }
  .kpi-delta { font-size: 12px; margin-top: 4px; }
  .alert-box {
    background: #1c1917; border: 1px solid #dc2626; border-radius: 10px;
    padding: 16px 20px; margin-bottom: 10px;
  }
  .alert-title { color: #ef4444; font-weight: 700; font-size: 15px; }
  .alert-body  { color: #d1d5db; font-size: 13px; margin-top: 4px; }
  .section-title { color: #e5e7eb; font-size: 20px; font-weight: 700; margin: 24px 0 12px; }
  div[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)


# ─── Columnas conocidas de Vicidial ──────────────────────────────────────────
VICIDIAL_STATUS_MAP = {
    # Contacto efectivo
    "SALE": "Venta", "CALLBK": "Callback", "DEC": "Rechazo",
    "NI": "No interesado", "PDROP": "Caída", "XFER": "Transferido",
    # No contacto
    "N": "No contesta", "NA": "No contesta", "NNA": "No contesta",
    "AA": "Contestador", "AM": "Contestador", "B": "Ocupado",
    "BUSY": "Ocupado", "DC": "Desconectado", "DROP": "Caída sistema",
    "LAMA": "Limit. contestador", "QUEUETIMEOUT": "Timeout cola",
    "INCALL": "En llamada", "CLOSER": "Cerrador", "REMA": "Remark",
    # Otros
    "DNCL": "No llamar", "RECYCLE": "Reciclar",
}

CONTACT_STATUSES = {"SALE", "CALLBK", "DEC", "NI", "XFER", "INCALL", "CLOSER"}
POSITIVE_STATUSES = {"SALE", "CALLBK", "XFER"}
MACHINE_STATUSES  = {"AA", "AM", "LAMA"}
NO_ANSWER         = {"N", "NA", "NNA", "B", "BUSY", "DC", "DROP", "QUEUETIMEOUT"}


# ─── Helpers ─────────────────────────────────────────────────────────────────
def kpi(label: str, value: str, delta: str = "", color: str = "blue") -> None:
    color_class = {"red": "red", "green": "green", "amber": "amber"}.get(color, "")
    delta_color = "#22c55e" if delta.startswith("▲") else "#ef4444" if delta.startswith("▼") else "#9ca3af"
    st.markdown(f"""
    <div class="kpi-card {color_class}">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      <div class="kpi-delta" style="color:{delta_color}">{delta}</div>
    </div>""", unsafe_allow_html=True)


def alert(title: str, body: str) -> None:
    st.markdown(f"""
    <div class="alert-box">
      <div class="alert-title">⚠ {title}</div>
      <div class="alert-body">{body}</div>
    </div>""", unsafe_allow_html=True)


def fmt_sec(seconds: float) -> str:
    if pd.isna(seconds):
        return "–"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def pct(num, den) -> str:
    if den == 0:
        return "0%"
    return f"{num/den*100:.1f}%"


# ─── Detección de columnas ───────────────────────────────────────────────────
def detect_columns(df: pd.DataFrame) -> dict:
    cols = {c.lower().strip(): c for c in df.columns}

    def find(*candidates):
        for c in candidates:
            if c in cols:
                return cols[c]
        return None

    return {
        "date":     find("call_date", "fecha", "date", "start_time", "calldate", "call_time", "fecha_llamada"),
        "agent":    find("user", "agent", "agente", "operator", "username", "agent_user"),
        "status":   find("status", "estado", "disposition", "call_status", "result"),
        "duration": find("length_in_sec", "duration", "duracion", "call_duration", "seconds", "length", "talk_time"),
        "campaign": find("campaign_id", "campaign", "campana", "lista", "list_id"),
        "phone":    find("phone_number", "phone", "telefono", "number", "called_number"),
        "queue":    find("queue_seconds", "wait_time", "queue_time", "hold_time"),
        "agent_talk": find("agent_talk_sec", "talk_sec", "talk_time"),
        "dead":     find("dead_seconds", "dead_time"),
    }


def load_file(uploaded) -> pd.DataFrame:
    name = uploaded.name.lower()
    if name.endswith(".csv"):
        # Intentar con varias codificaciones y separadores
        for enc in ["utf-8", "latin-1", "cp1252"]:
            for sep in [",", ";", "\t", "|"]:
                try:
                    df = pd.read_csv(uploaded, encoding=enc, sep=sep, low_memory=False)
                    if len(df.columns) > 1:
                        return df
                    uploaded.seek(0)
                except Exception:
                    uploaded.seek(0)
        return pd.read_csv(uploaded, encoding="latin-1", low_memory=False)
    elif name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded)
    elif name.endswith(".txt"):
        for sep in ["\t", "|", ",", ";"]:
            try:
                df = pd.read_csv(uploaded, sep=sep, encoding="latin-1", low_memory=False)
                if len(df.columns) > 1:
                    return df
                uploaded.seek(0)
            except Exception:
                uploaded.seek(0)
        return pd.read_csv(uploaded, encoding="latin-1", low_memory=False)
    else:
        raise ValueError("Formato no soportado. Usa CSV, Excel o TXT.")


def parse_date(df: pd.DataFrame, col: str) -> pd.Series:
    for fmt in [None, "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S",
                "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
        try:
            return pd.to_datetime(df[col], format=fmt, errors="coerce")
        except Exception:
            pass
    return pd.to_datetime(df[col], errors="coerce")


# ─── Análisis principal ──────────────────────────────────────────────────────
def analyze(df: pd.DataFrame, cols: dict) -> dict:
    r = {}
    total = len(df)
    r["total"] = total

    # Duración
    if cols["duration"]:
        df["_dur"] = pd.to_numeric(df[cols["duration"]], errors="coerce").fillna(0)
        r["avg_duration"]  = df["_dur"].mean()
        r["total_talk_min"] = df["_dur"].sum() / 60
    else:
        r["avg_duration"] = None
        r["total_talk_min"] = None

    # Status
    if cols["status"]:
        df["_status"] = df[cols["status"]].astype(str).str.upper().str.strip()
        vc = df["_status"].value_counts()
        r["status_counts"] = vc

        contacted   = df["_status"].isin(CONTACT_STATUSES).sum()
        positives   = df["_status"].isin(POSITIVE_STATUSES).sum()
        machines    = df["_status"].isin(MACHINE_STATUSES).sum()
        no_answer   = df["_status"].isin(NO_ANSWER).sum()

        r["contacted"]  = contacted
        r["positives"]  = positives
        r["machines"]   = machines
        r["no_answer"]  = no_answer
        r["contact_rate"]  = contacted  / total if total else 0
        r["positive_rate"] = positives  / total if total else 0
        r["machine_rate"]  = machines   / total if total else 0
        r["no_answer_rate"]= no_answer  / total if total else 0

        # Llamadas <5 seg (posibles drops)
        if cols["duration"]:
            r["short_calls"] = ((df["_dur"] < 5) & (df["_status"].isin(CONTACT_STATUSES))).sum()
        else:
            r["short_calls"] = None

    # Agente
    if cols["agent"]:
        ag = df.groupby(cols["agent"])
        ag_total = ag.size().rename("total")
        res = {"total": ag_total}
        if cols["status"]:
            res["contactadas"] = df[df["_status"].isin(CONTACT_STATUSES)].groupby(cols["agent"]).size()
            res["positivas"]   = df[df["_status"].isin(POSITIVE_STATUSES)].groupby(cols["agent"]).size()
        if cols["duration"]:
            res["avg_dur"] = ag["_dur"].mean()
        agent_df = pd.DataFrame(res).fillna(0)
        if "contactadas" in agent_df.columns:
            agent_df["tasa_contacto"] = (agent_df["contactadas"] / agent_df["total"] * 100).round(1)
        if "positivas" in agent_df.columns:
            agent_df["tasa_positiva"] = (agent_df["positivas"] / agent_df["total"] * 100).round(1)
        agent_df = agent_df.sort_values("total", ascending=False)
        r["agent_df"] = agent_df

    # Hora
    if cols["date"]:
        df["_dt"] = parse_date(df, cols["date"])
        df["_hour"] = df["_dt"].dt.hour
        r["hour_counts"] = df.groupby("_hour").size()
        if cols["status"]:
            r["hour_contact"] = df[df["_status"].isin(CONTACT_STATUSES)].groupby("_hour").size()
        if cols["duration"]:
            r["hour_duration"] = df.groupby("_hour")["_dur"].mean()
        # Día de semana
        r["dow_counts"] = df.groupby(df["_dt"].dt.day_name()).size()

    # Campaña
    if cols["campaign"]:
        camp = df.groupby(cols["campaign"])
        r["campaign_df"] = camp.size().rename("llamadas").reset_index()

    return r


def critical_points(r: dict) -> list:
    points = []

    cr = r.get("contact_rate", None)
    if cr is not None:
        if cr < 0.20:
            points.append(("CRÍTICO", "Tasa de contacto muy baja",
                           f"Solo {cr*100:.1f}% de llamadas contactan. Meta mínima: 20%. "
                           "Revisar base de datos, horarios de marcado y estrategia de números."))
        elif cr < 0.35:
            points.append(("ALERTA", "Tasa de contacto por debajo del objetivo",
                           f"{cr*100:.1f}% de contacto. Optimizar franjas horarias y depurar números inválidos."))

    mr = r.get("machine_rate", None)
    if mr is not None and mr > 0.30:
        points.append(("ALERTA", "Alto porcentaje de contestadores automáticos",
                       f"{mr*100:.1f}% de llamadas caen en contestador/AM. "
                       "Considerar activar AMD (Answering Machine Detection) o ajustar horarios."))

    if r.get("avg_duration") is not None:
        avg = r["avg_duration"]
        if avg < 30:
            points.append(("CRÍTICO", "Duración promedio de llamada muy corta",
                           f"Promedio de {avg:.0f}s. Indica llamadas incompletas o desconexiones tempranas. "
                           "Verificar conectividad y scripts de apertura."))
        elif avg > 600:
            points.append(("ALERTA", "Llamadas con duración excesiva",
                           f"Promedio de {avg/60:.1f} min. Puede indicar falta de manejo de objeciones o scripts largos."))

    sc = r.get("short_calls")
    total = r.get("total", 1)
    if sc is not None and sc / total > 0.15:
        points.append(("ALERTA", "Muchas llamadas cortas marcadas como contacto",
                       f"{sc} llamadas < 5s clasificadas como contacto ({sc/total*100:.1f}%). "
                       "Posible error de disposición o problema técnico."))

    if "agent_df" in r:
        adf = r["agent_df"]
        if "tasa_contacto" in adf.columns and len(adf) > 1:
            low_agents = adf[adf["tasa_contacto"] < 15]
            if len(low_agents) > 0:
                names = ", ".join(low_agents.index.astype(str).tolist()[:5])
                points.append(("ALERTA", f"Agentes con tasa de contacto < 15%",
                               f"Agentes: {names}. Requieren coaching o revisión de su base asignada."))

    if not points:
        points.append(("OK", "Sin puntos críticos detectados",
                       "El reporte no muestra alertas graves. Revisar tendencias históricas para mejora continua."))

    return points


PLOTLY_LAYOUT = dict(
    paper_bgcolor="#1e2130", plot_bgcolor="#1e2130",
    font=dict(color="#d1d5db", size=12),
    margin=dict(t=40, b=30, l=10, r=10),
)


# ─── App principal ────────────────────────────────────────────────────────────
def main():
    st.markdown("## 📞 Reporte de Eficiencia — Vicidial")
    st.markdown("Sube tu archivo de llamadas (CSV, Excel, TXT) y obtén el análisis en segundos.")

    uploaded = st.file_uploader(
        "Archivo de llamadas Vicidial",
        type=["csv", "xlsx", "xls", "txt"],
        help="Exporta el reporte de llamadas desde Vicidial Admin → Reports → Call Report",
    )

    if uploaded is None:
        st.info("👆 Sube tu archivo para comenzar el análisis.")
        with st.expander("¿Qué columnas necesita el archivo?"):
            st.markdown("""
**Columnas que el sistema detecta automáticamente:**

| Columna | Descripción | Ejemplos de nombre |
|---------|-------------|-------------------|
| Fecha/hora | Momento de la llamada | `call_date`, `fecha`, `start_time` |
| Agente | Usuario que realizó la llamada | `user`, `agent`, `agente` |
| Estado | Resultado de la llamada | `status`, `disposition`, `estado` |
| Duración | Segundos de la llamada | `length_in_sec`, `duration`, `duracion` |
| Campaña | ID de campaña | `campaign_id`, `campaign` |
| Teléfono | Número marcado | `phone_number`, `phone` |

El sistema funciona con exportaciones estándar de Vicidial, Five9, Avaya, y otros sistemas de marcación.
            """)
        return

    with st.spinner("Procesando archivo..."):
        try:
            df = load_file(uploaded)
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")
            return

    if df is None or len(df) == 0:
        st.error("El archivo está vacío o no se pudo leer correctamente.")
        return

    cols = detect_columns(df)

    # Mostrar mapeo detectado
    with st.expander("🔍 Columnas detectadas", expanded=False):
        for k, v in cols.items():
            icon = "✅" if v else "⬜"
            st.write(f"{icon} **{k}**: `{v or 'No encontrada'}`")

        # Selección manual si faltan columnas clave
        missing_key = not cols["status"] and not cols["duration"]
        if missing_key:
            st.warning("No se detectaron columnas de estado o duración. Selecciónalas manualmente:")
            all_cols = [""] + list(df.columns)
            cols["status"]   = st.selectbox("Columna de Estado/Disposition", all_cols) or None
            cols["duration"] = st.selectbox("Columna de Duración (seg)", all_cols) or None
            cols["agent"]    = st.selectbox("Columna de Agente", all_cols) or None
            cols["date"]     = st.selectbox("Columna de Fecha", all_cols) or None

    r = analyze(df, cols)
    total = r["total"]

    # ── KPIs ──────────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Resumen General</div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        kpi("Total llamadas", f"{total:,}")
    with c2:
        cr = r.get("contact_rate")
        color = "green" if (cr or 0) >= 0.35 else "amber" if (cr or 0) >= 0.20 else "red"
        kpi("Tasa de contacto", pct(r.get("contacted", 0), total), color=color)
    with c3:
        pr = r.get("positive_rate")
        color = "green" if (pr or 0) >= 0.15 else "amber" if (pr or 0) >= 0.08 else "red"
        kpi("Tasa positiva", pct(r.get("positives", 0), total), color=color)
    with c4:
        avg = r.get("avg_duration")
        color = "green" if avg and 60 <= avg <= 300 else "amber" if avg else "red"
        kpi("Duración promedio", fmt_sec(avg) if avg else "–", color=color)
    with c5:
        tm = r.get("total_talk_min")
        kpi("Minutos totales", f"{tm:,.0f}" if tm else "–")

    if cols["status"]:
        c6, c7, c8, c9 = st.columns(4)
        with c6:
            mr = r.get("machine_rate", 0)
            kpi("Contestadores (AM)", pct(r.get("machines", 0), total),
                color="amber" if mr > 0.30 else "blue")
        with c7:
            kpi("No contesta", pct(r.get("no_answer", 0), total))
        with c8:
            kpi("Contactados", f"{r.get('contacted',0):,}")
        with c9:
            kpi("Positivos", f"{r.get('positives',0):,}", color="green")

    # ── Puntos Críticos ───────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Puntos Críticos</div>', unsafe_allow_html=True)
    points = critical_points(r)
    for severity, title, body in points:
        if severity == "OK":
            st.success(f"✅ **{title}** — {body}")
        else:
            alert(title, body)

    # ── Gráficos ──────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Análisis Visual</div>', unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Distribución de Llamadas", "⏰ Análisis por Hora",
                                       "👤 Por Agente", "📈 Tendencias"])

    with tab1:
        col_a, col_b = st.columns(2)

        with col_a:
            if cols["status"]:
                status_df = r["status_counts"].head(12).reset_index()
                status_df.columns = ["Status", "Llamadas"]
                status_df["Descripción"] = status_df["Status"].map(VICIDIAL_STATUS_MAP).fillna(status_df["Status"])
                status_df["Label"] = status_df["Descripción"] + " (" + status_df["Status"] + ")"
                fig = px.pie(status_df, values="Llamadas", names="Label",
                             title="Distribución por Estado", hole=0.4,
                             color_discrete_sequence=px.colors.qualitative.Set3)
                fig.update_layout(**PLOTLY_LAYOUT)
                st.plotly_chart(fig, use_container_width=True)

        with col_b:
            if cols["status"]:
                cats = {
                    "Contacto efectivo": r.get("contacted", 0),
                    "No contesta": r.get("no_answer", 0),
                    "Contestador AM": r.get("machines", 0),
                    "Otros": total - r.get("contacted",0) - r.get("no_answer",0) - r.get("machines",0),
                }
                cats = {k: max(v, 0) for k, v in cats.items()}
                fig2 = px.bar(x=list(cats.keys()), y=list(cats.values()),
                              title="Resultado de Llamadas",
                              color=list(cats.keys()),
                              color_discrete_map={
                                  "Contacto efectivo": "#22c55e",
                                  "No contesta": "#ef4444",
                                  "Contestador AM": "#f59e0b",
                                  "Otros": "#6b7280",
                              })
                fig2.update_layout(**PLOTLY_LAYOUT)
                fig2.update_xaxes(title="")
                fig2.update_yaxes(title="Llamadas")
                st.plotly_chart(fig2, use_container_width=True)

        if cols["duration"]:
            dur_data = df["_dur"][df["_dur"].between(1, 3600)]
            fig3 = px.histogram(dur_data, nbins=50, title="Distribución de Duración (seg)",
                                color_discrete_sequence=["#3b82f6"])
            fig3.add_vline(x=dur_data.mean(), line_dash="dash", line_color="#f59e0b",
                           annotation_text=f"Prom: {dur_data.mean():.0f}s")
            fig3.update_layout(**PLOTLY_LAYOUT)
            fig3.update_xaxes(title="Duración (segundos)")
            fig3.update_yaxes(title="Llamadas")
            st.plotly_chart(fig3, use_container_width=True)

    with tab2:
        if cols["date"] and "hour_counts" in r:
            hc = r["hour_counts"].reindex(range(0, 24), fill_value=0)

            fig_h = go.Figure()
            fig_h.add_trace(go.Bar(x=hc.index, y=hc.values, name="Total llamadas",
                                   marker_color="#3b82f6", opacity=0.7))

            if "hour_contact" in r:
                hcon = r["hour_contact"].reindex(range(0, 24), fill_value=0)
                fig_h.add_trace(go.Scatter(x=hcon.index, y=hcon.values, name="Contactos",
                                           line=dict(color="#22c55e", width=2), mode="lines+markers"))

            if "hour_duration" in r:
                hdur = r["hour_duration"].reindex(range(0, 24), fill_value=0)
                fig_h.add_trace(go.Scatter(x=hdur.index, y=hdur.values, name="Duración prom (seg)",
                                           line=dict(color="#f59e0b", width=2, dash="dot"),
                                           yaxis="y2", mode="lines"))
                fig_h.update_layout(yaxis2=dict(title="Duración (seg)", overlaying="y", side="right",
                                                color="#f59e0b"))

            fig_h.update_layout(**PLOTLY_LAYOUT, title="Llamadas por Hora del Día",
                                xaxis=dict(title="Hora", tickmode="linear", tick0=0, dtick=1),
                                yaxis=dict(title="Llamadas"), legend=dict(x=0, y=1.1, orientation="h"))
            st.plotly_chart(fig_h, use_container_width=True)

            # Mejor hora para contactar
            if "hour_contact" in r:
                best_hour = r["hour_contact"].idxmax() if len(r["hour_contact"]) > 0 else None
                if best_hour is not None:
                    st.info(f"🕐 **Mejor hora para contactar:** {best_hour}:00 – {best_hour+1}:00 "
                            f"({r['hour_contact'][best_hour]:,} contactos)")

            if "dow_counts" in r:
                dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                dow_es    = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
                dow = r["dow_counts"].reindex([d for d in dow_order if d in r["dow_counts"].index], fill_value=0)
                dow.index = [dow_es[dow_order.index(d)] for d in dow.index]
                fig_d = px.bar(x=dow.index, y=dow.values, title="Llamadas por Día de Semana",
                               color_discrete_sequence=["#8b5cf6"])
                fig_d.update_layout(**PLOTLY_LAYOUT)
                st.plotly_chart(fig_d, use_container_width=True)
        else:
            st.info("No se detectó columna de fecha para el análisis por hora.")

    with tab3:
        if "agent_df" in r:
            adf = r["agent_df"].reset_index()
            adf.columns = [str(c) for c in adf.columns]

            # Top agentes por total
            fig_a = px.bar(adf.head(20), x=adf.columns[0], y="total",
                           title="Top Agentes por Volumen de Llamadas",
                           color_discrete_sequence=["#3b82f6"])
            fig_a.update_layout(**PLOTLY_LAYOUT)
            fig_a.update_xaxes(title="Agente")
            fig_a.update_yaxes(title="Llamadas")
            st.plotly_chart(fig_a, use_container_width=True)

            if "tasa_contacto" in adf.columns:
                fig_ac = px.bar(adf.head(20).sort_values("tasa_contacto", ascending=False),
                                x=adf.columns[0], y="tasa_contacto",
                                title="Tasa de Contacto por Agente (%)",
                                color="tasa_contacto",
                                color_continuous_scale=["#ef4444", "#f59e0b", "#22c55e"],
                                range_color=[0, 60])
                fig_ac.update_layout(**PLOTLY_LAYOUT)
                fig_ac.add_hline(y=35, line_dash="dash", line_color="#22c55e",
                                 annotation_text="Meta 35%")
                st.plotly_chart(fig_ac, use_container_width=True)

            # Tabla de agentes
            st.dataframe(
                adf.head(30).style.format({
                    "tasa_contacto": "{:.1f}%",
                    "tasa_positiva": "{:.1f}%",
                    "avg_dur": "{:.0f}s",
                }),
                use_container_width=True,
            )
        else:
            st.info("No se detectó columna de agente para el análisis.")

    with tab4:
        if cols["date"] and "_dt" in df.columns:
            df2 = df.copy()
            df2["_date"] = df2["_dt"].dt.date
            daily = df2.groupby("_date").size().reset_index(name="llamadas")
            daily = daily.dropna()

            if len(daily) > 1:
                fig_t = go.Figure()
                fig_t.add_trace(go.Scatter(x=daily["_date"], y=daily["llamadas"],
                                           mode="lines+markers", name="Llamadas/día",
                                           line=dict(color="#3b82f6", width=2),
                                           fill="tozeroy", fillcolor="rgba(59,130,246,0.1)"))

                if cols["status"] and "hour_contact" in r:
                    daily_contact = df2[df2["_status"].isin(CONTACT_STATUSES)].groupby("_date").size().reset_index(name="contactos")
                    daily_merged = daily.merge(daily_contact, on="_date", how="left").fillna(0)
                    daily_merged["tasa"] = daily_merged["contactos"] / daily_merged["llamadas"] * 100
                    fig_t.add_trace(go.Scatter(x=daily_merged["_date"], y=daily_merged["tasa"],
                                               name="Tasa contacto %", yaxis="y2",
                                               line=dict(color="#22c55e", width=2, dash="dot")))
                    fig_t.update_layout(yaxis2=dict(title="Tasa contacto (%)", overlaying="y",
                                                    side="right", color="#22c55e"))

                fig_t.update_layout(**PLOTLY_LAYOUT, title="Volumen Diario de Llamadas",
                                    xaxis=dict(title="Fecha"),
                                    yaxis=dict(title="Llamadas"))
                st.plotly_chart(fig_t, use_container_width=True)
            else:
                st.info("Solo hay datos de un día. No se puede graficar tendencia.")
        else:
            st.info("No se detectó columna de fecha para tendencias.")

    # ── Exportar ──────────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Exportar Reporte</div>', unsafe_allow_html=True)
    col_e1, col_e2 = st.columns(2)

    with col_e1:
        # Resumen ejecutivo Excel
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            # Hoja resumen
            summary = {
                "Métrica": [
                    "Total llamadas", "Contactados", "Tasa de contacto",
                    "Positivos", "Tasa positiva", "Contestadores AM",
                    "No contesta", "Duración promedio", "Minutos totales"
                ],
                "Valor": [
                    total,
                    r.get("contacted", "N/A"),
                    f"{r.get('contact_rate',0)*100:.1f}%",
                    r.get("positives", "N/A"),
                    f"{r.get('positive_rate',0)*100:.1f}%",
                    r.get("machines", "N/A"),
                    r.get("no_answer", "N/A"),
                    fmt_sec(r.get("avg_duration")),
                    f"{r.get('total_talk_min', 0):.0f}",
                ]
            }
            pd.DataFrame(summary).to_excel(writer, sheet_name="Resumen", index=False)

            # Puntos críticos
            cp_df = pd.DataFrame([(s, t, b) for s, t, b in points],
                                 columns=["Severidad", "Título", "Descripción"])
            cp_df.to_excel(writer, sheet_name="Puntos Críticos", index=False)

            # Agentes
            if "agent_df" in r:
                r["agent_df"].reset_index().to_excel(writer, sheet_name="Por Agente", index=False)

            # Status
            if cols["status"]:
                r["status_counts"].reset_index().to_excel(writer, sheet_name="Por Estado", index=False)

        buf.seek(0)
        st.download_button(
            "⬇️ Descargar Reporte Excel",
            data=buf,
            file_name=f"reporte_vicidial_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col_e2:
        # CSV resumen agentes (para dialer o gestión)
        if "agent_df" in r:
            csv_data = r["agent_df"].reset_index().to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "⬇️ Exportar Agentes CSV",
                data=csv_data,
                file_name=f"agentes_vicidial_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )


if __name__ == "__main__":
    main()
