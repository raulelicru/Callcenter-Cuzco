"""
Base de Datos PostgreSQL — Supabase
====================================
Usa st.secrets en Streamlit Cloud, variable de entorno DATABASE_URL en local.
"""

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import pandas as pd
from datetime import datetime
import os


def get_db_params() -> dict:
    """Obtiene credenciales desde Streamlit secrets o variables de entorno."""
    try:
        import streamlit as st
        s = st.secrets["database"]
        return dict(host=s["host"], port=int(s["port"]), dbname=s["dbname"],
                    user=s["user"], password=s["password"], sslmode="require")
    except Exception:
        url = os.environ.get("DATABASE_URL", "")
        if url:
            import urllib.parse as up
            r = up.urlparse(url)
            return dict(host=r.hostname, port=r.port or 5432, dbname=r.path.lstrip("/"),
                        user=r.username, password=r.password, sslmode="require")
        raise RuntimeError("No se encontraron credenciales de base de datos.")


def get_connection():
    return psycopg2.connect(**get_db_params(), cursor_factory=RealDictCursor)


def init_db():
    """Crea todas las tablas si no existen."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            cliente_id            TEXT PRIMARY KEY,
            score_operativo       INTEGER,
            segmento              TEXT,
            prob_pago             REAL,
            dpd                   INTEGER,
            bucket_mora           TEXT,
            saldo_total           REAL,
            rpc_rate              REAL,
            ultimo_estado_marcado TEXT,
            estrategia_canal      TEXT,
            estrategia_accion     TEXT,
            estrategia_oferta     TEXT,
            veces_procesado       INTEGER DEFAULT 1,
            fecha_primera_carga   TEXT,
            fecha_ultima_carga    TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS historial_scores (
            id              SERIAL PRIMARY KEY,
            cliente_id      TEXT,
            score_operativo INTEGER,
            segmento        TEXT,
            prob_pago       REAL,
            dpd             INTEGER,
            saldo_total     REAL,
            fecha_score     TEXT,
            carga_id        INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cargas (
            id                     SERIAL PRIMARY KEY,
            usuario                TEXT,
            filename               TEXT,
            total_registros        INTEGER,
            registros_nuevos       INTEGER,
            registros_actualizados INTEGER,
            fecha_carga            TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id             SERIAL PRIMARY KEY,
            username       TEXT UNIQUE NOT NULL,
            nombre         TEXT NOT NULL,
            email          TEXT,
            rol            TEXT NOT NULL,
            password_hash  TEXT NOT NULL,
            activo         INTEGER DEFAULT 1,
            fecha_creacion TEXT DEFAULT CURRENT_DATE::TEXT
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


def get_clientes_by_ids(ids: list) -> pd.DataFrame:
    """Usa ANY(%s) de PostgreSQL — sin límite de variables."""
    if not ids:
        return pd.DataFrame()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clientes WHERE cliente_id = ANY(%s)", (ids,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def upsert_clientes_batch(df: pd.DataFrame, carga_id: int) -> dict:
    """
    Upsert masivo con execute_values — optimizado para 350K+ registros.
    INSERT ... ON CONFLICT DO UPDATE garantiza atomicidad.
    """
    conn = get_connection()
    cur = conn.cursor()
    today = datetime.today().strftime("%Y-%m-%d")

    rows = []
    for _, row in df.iterrows():
        rows.append((
            str(row.get("cliente_id", "")),
            int(row.get("score_operativo", 0) or 0),
            str(row.get("segmento", "")),
            float(row.get("prob_pago", 0) or 0),
            int(row.get("dpd", 0) or 0),
            str(row.get("bucket_mora", "")),
            float(row.get("saldo_total", 0) or 0),
            float(row.get("rpc_rate", 0) or 0),
            str(row.get("ultimo_estado_marcado", "")),
            str(row.get("estrategia_canal", "")),
            str(row.get("estrategia_accion", "")),
            str(row.get("estrategia_oferta", "")),
            today,
        ))

    execute_values(cur, """
        INSERT INTO clientes (
            cliente_id, score_operativo, segmento, prob_pago, dpd,
            bucket_mora, saldo_total, rpc_rate, ultimo_estado_marcado,
            estrategia_canal, estrategia_accion, estrategia_oferta,
            fecha_primera_carga, fecha_ultima_carga
        ) VALUES %s
        ON CONFLICT (cliente_id) DO UPDATE SET
            score_operativo       = EXCLUDED.score_operativo,
            segmento              = EXCLUDED.segmento,
            prob_pago             = EXCLUDED.prob_pago,
            dpd                   = EXCLUDED.dpd,
            bucket_mora           = EXCLUDED.bucket_mora,
            saldo_total           = EXCLUDED.saldo_total,
            rpc_rate              = EXCLUDED.rpc_rate,
            ultimo_estado_marcado = EXCLUDED.ultimo_estado_marcado,
            estrategia_canal      = EXCLUDED.estrategia_canal,
            estrategia_accion     = EXCLUDED.estrategia_accion,
            estrategia_oferta     = EXCLUDED.estrategia_oferta,
            veces_procesado       = clientes.veces_procesado + 1,
            fecha_ultima_carga    = EXCLUDED.fecha_ultima_carga
    """, rows, page_size=1000)

    # Contar nuevos vs actualizados
    ids = [r[0] for r in rows]
    cur.execute("SELECT COUNT(*) as n FROM clientes WHERE cliente_id = ANY(%s) AND fecha_primera_carga = %s", (ids, today))
    nuevos = cur.fetchone()["n"]
    actualizados = len(rows) - nuevos

    # Historial en batch
    hist_rows = [
        (str(row.get("cliente_id","")), int(row.get("score_operativo",0) or 0),
         str(row.get("segmento","")), float(row.get("prob_pago",0) or 0),
         int(row.get("dpd",0) or 0), float(row.get("saldo_total",0) or 0),
         today, carga_id)
        for _, row in df.iterrows()
    ]
    execute_values(cur, """
        INSERT INTO historial_scores
            (cliente_id, score_operativo, segmento, prob_pago, dpd, saldo_total, fecha_score, carga_id)
        VALUES %s
    """, hist_rows, page_size=1000)

    conn.commit()
    cur.close()
    conn.close()
    return {"nuevos": nuevos, "actualizados": actualizados}


def log_carga(usuario: str, filename: str, total: int, nuevos: int, actualizados: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO cargas (usuario, filename, total_registros, registros_nuevos, registros_actualizados, fecha_carga)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
    """, (usuario, filename, total, nuevos, actualizados, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    carga_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return carga_id


def get_cargas_historico() -> pd.DataFrame:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cargas ORDER BY fecha_carga DESC LIMIT 100")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def get_metricas_globales() -> dict:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as n FROM clientes")
    total = cur.fetchone()["n"]

    cur.execute("""
        SELECT segmento, COUNT(*) as n,
               AVG(score_operativo) as avg_s,
               SUM(saldo_total) as saldo
        FROM clientes GROUP BY segmento
    """)
    por_segmento = {}
    for r in cur.fetchall():
        por_segmento[r["segmento"]] = {
            "count": r["n"],
            "avg_score": round(float(r["avg_s"] or 0), 1),
            "saldo": round(float(r["saldo"] or 0), 2),
        }

    cur.execute("SELECT AVG(score_operativo) as s, AVG(prob_pago) as p FROM clientes")
    r = cur.fetchone()

    cur.execute("SELECT SUM(saldo_total) as s FROM clientes")
    saldo = cur.fetchone()["s"] or 0

    cur.execute("SELECT COUNT(*) as n FROM cargas")
    total_cargas = cur.fetchone()["n"]

    cur.close()
    conn.close()
    return {
        "total_clientes": total,
        "por_segmento": por_segmento,
        "avg_score": round(float(r["s"] or 0), 1),
        "avg_prob_pago": round(float(r["p"] or 0) * 100, 1),
        "saldo_total": float(saldo),
        "total_cargas": total_cargas,
    }


def get_all_clientes_df(limit: int = 10000) -> pd.DataFrame:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clientes ORDER BY score_operativo DESC LIMIT %s", (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
