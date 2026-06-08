"""
Persistencia de reportes en Supabase.

Guarda y carga los tableros Excel generados (contactabilidad, recontacto,
tipificacion) como texto base64 en la tabla `reporte_historico`, aislados
por cuenta (Cuzco / Coquimbo).

Credenciales esperadas en .streamlit/secrets.toml:
    [supabase]
    url = "https://<tu-proyecto>.supabase.co"
    key = "<anon-key>"
"""

from __future__ import annotations

import base64
import io
import os

import pandas as pd
from supabase import create_client, Client


def _client() -> Client:
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
            "Credenciales de Supabase no encontradas. "
            "Configura st.secrets['supabase']['url'] y ['key'] en Streamlit Cloud, "
            "o las variables de entorno SUPABASE_URL y SUPABASE_KEY."
        )


def guardar_reporte(cuenta: str, nombre: str, sheets: dict[str, pd.DataFrame]):
    """Convierte las hojas a Excel y lo guarda (upsert) en Supabase."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for sname, df in sheets.items():
            df.to_excel(w, index=False, sheet_name=str(sname)[:31])
    excel_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    client = _client()
    client.table("reporte_historico").upsert(
        {"cuenta": cuenta, "nombre": nombre, "excel_b64": excel_b64},
        on_conflict="cuenta,nombre",
    ).execute()


def cargar_reporte(cuenta: str, nombre: str) -> dict[str, pd.DataFrame]:
    """Descarga el ultimo tablero guardado y lo devuelve como dict de DataFrames."""
    client = _client()
    resp = (
        client.table("reporte_historico")
        .select("excel_b64")
        .eq("cuenta", cuenta)
        .eq("nombre", nombre)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return {}
    raw = base64.b64decode(resp.data[0]["excel_b64"])
    return pd.read_excel(io.BytesIO(raw), sheet_name=None)


def supabase_disponible() -> bool:
    """Devuelve True si las credenciales estan configuradas y la tabla es accesible."""
    try:
        client = _client()
        client.table("reporte_historico").select("id").limit(1).execute()
        return True
    except Exception:
        return False
