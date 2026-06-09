"""
Base de Datos — Supabase via HTTPS (supabase-py)
Conecta por HTTP/HTTPS: sin problemas de IPv4/IPv6.
"""
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import os


def get_client() -> Client:
    try:
        import streamlit as st
        s = st.secrets["supabase"]
        return create_client(str(s["url"]), str(s["key"]))
    except Exception:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if url and key:
            return create_client(url, key)
        raise RuntimeError(
            "No se encontraron credenciales. "
            "Configura st.secrets['supabase']['url'] y ['key']."
        )


def init_db():
    """Crea las tablas si no existen y verifica la conexión."""
    client = get_client()

    # Crear tabla usuarios
    try:
        client.table("usuarios").select("id").limit(1).execute()
    except Exception:
        # Tabla no existe — crearla via RPC/SQL no es posible desde supabase-py
        # Mostrar instrucción clara al usuario
        raise RuntimeError(
            "Las tablas no están creadas en Supabase. "
            "Ve a supabase.com → tu proyecto → SQL Editor y ejecuta el archivo src/setup_supabase.sql"
        )


def get_clientes_by_ids(ids: list) -> pd.DataFrame:
    if not ids:
        return pd.DataFrame()
    client = get_client()
    all_rows = []
    for i in range(0, len(ids), 500):
        resp = client.table("clientes").select("*").in_("cliente_id", ids[i:i+500]).execute()
        all_rows.extend(resp.data or [])
    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()


def upsert_clientes_batch(df: pd.DataFrame, carga_id: int) -> dict:
    client = get_client()
    today = datetime.today().strftime("%Y-%m-%d")

    # Detectar nuevos vs existentes antes del upsert
    all_ids = df["cliente_id"].astype(str).tolist()
    df_ex = get_clientes_by_ids(all_ids)
    existing_ids = set(df_ex["cliente_id"].tolist()) if len(df_ex) > 0 else set()
    nuevos      = sum(1 for i in all_ids if i not in existing_ids)
    actualizados = len(all_ids) - nuevos

    records = [
        {
            "cliente_id":            str(row.get("cliente_id", "")),
            "score_operativo":       int(row.get("score_operativo", 0) or 0),
            "segmento":              str(row.get("segmento", "")),
            "prob_pago":             float(row.get("prob_pago", 0) or 0),
            "dpd":                   int(row.get("dpd", 0) or 0),
            "bucket_mora":           str(row.get("bucket_mora", "")),
            "saldo_total":           float(row.get("saldo_total", 0) or 0),
            "rpc_rate":              float(row.get("rpc_rate", 0) or 0),
            "ultimo_estado_marcado": str(row.get("ultimo_estado_marcado", "")),
            "estrategia_canal":      str(row.get("estrategia_canal", "")),
            "estrategia_accion":     str(row.get("estrategia_accion", "")),
            "estrategia_oferta":     str(row.get("estrategia_oferta", "")),
            "fecha_primera_carga":   today,
            "fecha_ultima_carga":    today,
        }
        for _, row in df.iterrows()
    ]

    # Upsert en lotes — el trigger protege fecha_primera_carga y veces_procesado
    CHUNK = 1000
    for i in range(0, len(records), CHUNK):
        client.table("clientes").upsert(
            records[i:i+CHUNK], on_conflict="cliente_id"
        ).execute()

    # Historial en lotes
    hist = [
        {
            "cliente_id":      str(row.get("cliente_id", "")),
            "score_operativo": int(row.get("score_operativo", 0) or 0),
            "segmento":        str(row.get("segmento", "")),
            "prob_pago":       float(row.get("prob_pago", 0) or 0),
            "dpd":             int(row.get("dpd", 0) or 0),
            "saldo_total":     float(row.get("saldo_total", 0) or 0),
            "fecha_score":     today,
            "carga_id":        carga_id,
        }
        for _, row in df.iterrows()
    ]
    for i in range(0, len(hist), CHUNK):
        client.table("historial_scores").insert(hist[i:i+CHUNK]).execute()

    return {"nuevos": nuevos, "actualizados": actualizados}


def log_carga(usuario: str, filename: str, total: int, nuevos: int, actualizados: int) -> int:
    client = get_client()
    resp = client.table("cargas").insert({
        "usuario":                usuario,
        "filename":               filename,
        "total_registros":        total,
        "registros_nuevos":       nuevos,
        "registros_actualizados": actualizados,
        "fecha_carga":            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }).execute()
    return resp.data[0]["id"]


def get_cargas_historico() -> pd.DataFrame:
    client = get_client()
    resp = client.table("cargas").select("*").order("fecha_carga", desc=True).limit(100).execute()
    return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()


def get_metricas_globales() -> dict:
    client = get_client()

    # Intentar con la función RPC; si falla, calcular directamente desde la tabla
    try:
        resp = client.rpc("get_metricas_globales").execute()
        data = resp.data or {}
        if data:
            return {
                "total_clientes": data.get("total_clientes", 0),
                "por_segmento":   data.get("por_segmento", {}),
                "avg_score":      float(data.get("avg_score", 0)),
                "avg_prob_pago":  float(data.get("avg_prob_pago", 0)),
                "saldo_total":    float(data.get("saldo_total", 0)),
                "total_cargas":   data.get("total_cargas", 0),
            }
    except Exception:
        pass

    # Fallback: calcular desde la tabla clientes directamente
    resp = client.table("clientes").select(
        "segmento, score_operativo, prob_pago, saldo_total"
    ).execute()
    rows = resp.data or []

    if not rows:
        return {
            "total_clientes": 0,
            "por_segmento":   {},
            "avg_score":      0.0,
            "avg_prob_pago":  0.0,
            "saldo_total":    0.0,
            "total_cargas":   0,
        }

    df = pd.DataFrame(rows)
    por_segmento = {}
    for seg, grp in df.groupby("segmento"):
        por_segmento[seg] = {
            "count": len(grp),
            "saldo": float(grp["saldo_total"].fillna(0).sum()),
            "avg_score": float(grp["score_operativo"].fillna(0).mean()),
        }

    try:
        n_cargas = client.table("cargas").select("id", count="exact").execute().count or 0
    except Exception:
        n_cargas = 0

    return {
        "total_clientes": len(df),
        "por_segmento":   por_segmento,
        "avg_score":      round(float(df["score_operativo"].fillna(0).mean()), 1),
        "avg_prob_pago":  round(float(df["prob_pago"].fillna(0).mean()), 3),
        "saldo_total":    float(df["saldo_total"].fillna(0).sum()),
        "total_cargas":   n_cargas,
    }


def get_all_clientes_df(limit: int = 10000) -> pd.DataFrame:
    client = get_client()
    resp = (
        client.table("clientes")
        .select("*")
        .order("score_operativo", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
