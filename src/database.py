"""
Base de Datos — Supabase via HTTPS (supabase-py)
Todas las operaciones filtran por empresa_id para soporte multi-empresa.
"""
from supabase import create_client
import pandas as pd
from datetime import datetime
import os


def get_client():
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
    client = get_client()
    try:
        client.table("usuarios").select("id").limit(1).execute()
    except Exception as e:
        raise RuntimeError(
            "Las tablas no están creadas en Supabase. "
            "Ve a supabase.com → tu proyecto → SQL Editor y ejecuta src/setup_supabase.sql. "
            f"Error: {e}"
        )


# ── Empresas ──────────────────────────────────────────────────────────────────

def get_all_empresas() -> pd.DataFrame:
    client = get_client()
    resp = client.table("empresas").select("*").order("nombre").execute()
    return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()


def create_empresa(nombre: str, slug: str):
    try:
        client = get_client()
        client.table("empresas").insert({"nombre": nombre, "slug": slug}).execute()
        return True, f"Empresa '{nombre}' creada."
    except Exception as e:
        return False, str(e)


def get_empresa_id_by_slug(slug: str) -> int:
    client = get_client()
    resp = client.table("empresas").select("id").eq("slug", slug).maybe_single().execute()
    return resp.data["id"] if resp.data else 1


# ── Clientes ──────────────────────────────────────────────────────────────────

def get_clientes_by_ids(ids: list, empresa_id: int = 1) -> pd.DataFrame:
    if not ids:
        return pd.DataFrame()
    client = get_client()
    all_rows = []
    for i in range(0, len(ids), 500):
        batch = ids[i:i+500]
        resp = (
            client.table("clientes")
            .select("cliente_id")
            .in_("cliente_id", batch)
            .eq("empresa_id", empresa_id)
            .execute()
        )
        if resp.data:
            all_rows.extend(resp.data)
    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()


def upsert_clientes_batch(df: pd.DataFrame, carga_id: int, empresa_id: int = 1):
    client = get_client()
    cols = [
        "cliente_id", "empresa_id", "score_operativo", "segmento", "prob_pago",
        "dpd", "bucket_mora", "saldo_total", "rpc_rate", "ultimo_estado_marcado",
        "estrategia_canal", "estrategia_accion", "estrategia_oferta",
        "fecha_primera_carga", "fecha_ultima_carga",
    ]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records = []
    for _, row in df.iterrows():
        r = {"empresa_id": empresa_id, "fecha_ultima_carga": now}
        for c in cols:
            if c in df.columns:
                v = row[c]
                r[c] = None if pd.isna(v) else v
        if "fecha_primera_carga" not in df.columns or pd.isna(row.get("fecha_primera_carga")):
            r["fecha_primera_carga"] = now
        records.append(r)

    BATCH = 200
    for i in range(0, len(records), BATCH):
        client.table("clientes").upsert(
            records[i:i+BATCH],
            on_conflict="cliente_id,empresa_id"
        ).execute()

    # Historial
    hist = []
    for _, row in df.iterrows():
        hist.append({
            "empresa_id":      empresa_id,
            "cliente_id":      str(row.get("cliente_id", "")),
            "score_operativo": int(row["score_operativo"]) if "score_operativo" in df.columns else None,
            "segmento":        row.get("segmento"),
            "prob_pago":       float(row["prob_pago"]) if "prob_pago" in df.columns else None,
            "dpd":             int(row["dpd"]) if "dpd" in df.columns and not pd.isna(row.get("dpd")) else None,
            "saldo_total":     float(row["saldo_total"]) if "saldo_total" in df.columns and not pd.isna(row.get("saldo_total")) else None,
            "fecha_score":     now,
            "carga_id":        carga_id,
        })
    for i in range(0, len(hist), BATCH):
        client.table("historial_scores").insert(hist[i:i+BATCH]).execute()


def log_carga(usuario: str, filename: str, total: int, nuevos: int,
              actualizados: int, empresa_id: int = 1) -> int:
    client = get_client()
    resp = client.table("cargas").insert({
        "empresa_id":             empresa_id,
        "usuario":                usuario,
        "filename":               filename,
        "total_registros":        total,
        "registros_nuevos":       nuevos,
        "registros_actualizados": actualizados,
        "fecha_carga":            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }).execute()
    return resp.data[0]["id"]


def get_cargas_historico(empresa_id: int = 1) -> pd.DataFrame:
    client = get_client()
    resp = (
        client.table("cargas")
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("fecha_carga", desc=True)
        .limit(100)
        .execute()
    )
    return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()


def get_metricas_globales(empresa_id: int = 1) -> dict:
    client = get_client()
    try:
        resp = client.rpc("get_metricas_globales", {"p_empresa_id": empresa_id}).execute()
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

    # Fallback directo desde tabla
    resp = (
        client.table("clientes")
        .select("segmento, score_operativo, prob_pago, saldo_total")
        .eq("empresa_id", empresa_id)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        return {"total_clientes": 0, "por_segmento": {}, "avg_score": 0.0,
                "avg_prob_pago": 0.0, "saldo_total": 0.0, "total_cargas": 0}

    df = pd.DataFrame(rows)
    por_segmento = {}
    for seg, grp in df.groupby("segmento"):
        por_segmento[seg] = {
            "count":     len(grp),
            "saldo":     float(grp["saldo_total"].fillna(0).sum()),
            "avg_score": float(grp["score_operativo"].fillna(0).mean()),
        }
    try:
        n_cargas = client.table("cargas").select("id", count="exact").eq("empresa_id", empresa_id).execute().count or 0
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


def get_all_clientes_df(limit: int = 10000, empresa_id: int = 1) -> pd.DataFrame:
    client = get_client()
    resp = (
        client.table("clientes")
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("score_operativo", desc=True)
        .limit(limit)
        .execute()
    )
    return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()
