"""
Base de Datos SQLite — Gestión Persistente de Cartera
======================================================
Almacena clientes, scores históricos, cargas y usuarios.
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

# Ruta absoluta relativa al archivo — funciona sin importar desde dónde se ejecute
DB_PATH = Path(__file__).parent.parent / "data" / "callcenter.db"
DB_PATH.parent.mkdir(exist_ok=True)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Crea todas las tablas si no existen."""
    conn = get_connection()
    conn.executescript("""
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
        );

        CREATE TABLE IF NOT EXISTS historial_scores (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id      TEXT,
            score_operativo INTEGER,
            segmento        TEXT,
            prob_pago       REAL,
            dpd             INTEGER,
            saldo_total     REAL,
            fecha_score     TEXT,
            carga_id        INTEGER
        );

        CREATE TABLE IF NOT EXISTS cargas (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario                TEXT,
            filename               TEXT,
            total_registros        INTEGER,
            registros_nuevos       INTEGER,
            registros_actualizados INTEGER,
            fecha_carga            TEXT
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            username       TEXT UNIQUE NOT NULL,
            nombre         TEXT NOT NULL,
            email          TEXT,
            rol            TEXT NOT NULL,
            password_hash  TEXT NOT NULL,
            activo         INTEGER DEFAULT 1,
            fecha_creacion TEXT DEFAULT (date('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_clientes_segmento ON clientes(segmento);
        CREATE INDEX IF NOT EXISTS idx_historial_cliente ON historial_scores(cliente_id);
    """)
    conn.commit()
    conn.close()


def get_clientes_by_ids(ids: list) -> pd.DataFrame:
    """Retorna clientes existentes en la BD. Procesa en lotes de 900 para respetar el límite de SQLite."""
    if not ids:
        return pd.DataFrame()
    conn = get_connection()
    chunks = [ids[i:i+900] for i in range(0, len(ids), 900)]
    resultados = []
    for chunk in chunks:
        ph = ",".join("?" * len(chunk))
        df_chunk = pd.read_sql_query(
            f"SELECT * FROM clientes WHERE cliente_id IN ({ph})",
            conn, params=chunk,
        )
        resultados.append(df_chunk)
    conn.close()
    return pd.concat(resultados, ignore_index=True) if resultados else pd.DataFrame()


def upsert_clientes_batch(df: pd.DataFrame, carga_id: int) -> dict:
    """
    Inserta o actualiza clientes en batch. Optimizado para 30K+ registros.
    Retorna dict con conteo de nuevos y actualizados.
    """
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.today().strftime("%Y-%m-%d")

    ids = df["cliente_id"].tolist()
    existing = {}
    for i in range(0, len(ids), 900):
        chunk = ids[i:i+900]
        ph = ",".join("?" * len(chunk))
        cursor.execute(
            f"SELECT cliente_id, veces_procesado, fecha_primera_carga FROM clientes WHERE cliente_id IN ({ph})",
            chunk,
        )
        for row in cursor.fetchall():
            existing[row["cliente_id"]] = row

    nuevos = 0
    actualizados = 0
    rows_clientes = []
    rows_historial = []

    for _, row in df.iterrows():
        cid = row["cliente_id"]
        score = int(row.get("score_operativo", 0))
        seg = str(row.get("segmento", ""))
        prob = float(row.get("prob_pago", 0))
        dpd_val = int(row.get("dpd", 0)) if pd.notna(row.get("dpd")) else 0
        bucket = str(row.get("bucket_mora", ""))
        saldo = float(row.get("saldo_total", 0)) if pd.notna(row.get("saldo_total")) else 0.0
        rpc = float(row.get("rpc_rate", 0)) if pd.notna(row.get("rpc_rate")) else 0.0
        estado = str(row.get("ultimo_estado_marcado", ""))
        canal = str(row.get("estrategia_canal", ""))
        accion = str(row.get("estrategia_accion", ""))
        oferta = str(row.get("estrategia_oferta", ""))

        rows_historial.append((cid, score, seg, prob, dpd_val, saldo, today, carga_id))

        if cid in existing:
            veces = existing[cid]["veces_procesado"] + 1
            primera = existing[cid]["fecha_primera_carga"]
            rows_clientes.append(("UPDATE", cid, score, seg, prob, dpd_val, bucket, saldo, rpc,
                                   estado, canal, accion, oferta, veces, today, primera))
            actualizados += 1
        else:
            rows_clientes.append(("INSERT", cid, score, seg, prob, dpd_val, bucket, saldo, rpc,
                                   estado, canal, accion, oferta, 1, today, today))
            nuevos += 1

    for r in rows_clientes:
        op = r[0]
        if op == "UPDATE":
            _, cid, score, seg, prob, dpd_val, bucket, saldo, rpc, estado, canal, accion, oferta, veces, ultima, primera = r
            cursor.execute("""
                UPDATE clientes SET
                    score_operativo=?, segmento=?, prob_pago=?, dpd=?,
                    bucket_mora=?, saldo_total=?, rpc_rate=?,
                    ultimo_estado_marcado=?, estrategia_canal=?,
                    estrategia_accion=?, estrategia_oferta=?,
                    veces_procesado=?, fecha_ultima_carga=?
                WHERE cliente_id=?
            """, (score, seg, prob, dpd_val, bucket, saldo, rpc, estado, canal, accion, oferta,
                  veces, ultima, cid))
        else:
            _, cid, score, seg, prob, dpd_val, bucket, saldo, rpc, estado, canal, accion, oferta, veces, ultima, primera = r
            cursor.execute("""
                INSERT OR IGNORE INTO clientes (
                    cliente_id, score_operativo, segmento, prob_pago, dpd,
                    bucket_mora, saldo_total, rpc_rate, ultimo_estado_marcado,
                    estrategia_canal, estrategia_accion, estrategia_oferta,
                    veces_procesado, fecha_primera_carga, fecha_ultima_carga
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (cid, score, seg, prob, dpd_val, bucket, saldo, rpc, estado, canal, accion, oferta,
                  veces, primera, ultima))

    cursor.executemany("""
        INSERT INTO historial_scores
            (cliente_id, score_operativo, segmento, prob_pago, dpd, saldo_total, fecha_score, carga_id)
        VALUES (?,?,?,?,?,?,?,?)
    """, rows_historial)

    conn.commit()
    conn.close()
    return {"nuevos": nuevos, "actualizados": actualizados}


def log_carga(usuario: str, filename: str, total: int, nuevos: int, actualizados: int) -> int:
    """Registra una carga. Retorna el ID de la carga."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cargas (usuario, filename, total_registros, registros_nuevos, registros_actualizados, fecha_carga)
        VALUES (?,?,?,?,?,?)
    """, (usuario, filename, total, nuevos, actualizados, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    carga_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return carga_id


def get_cargas_historico() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM cargas ORDER BY fecha_carga DESC LIMIT 100", conn
    )
    conn.close()
    return df


def get_metricas_globales() -> dict:
    """Métricas agregadas de toda la base de datos."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as n FROM clientes")
    total = cursor.fetchone()["n"]

    cursor.execute("SELECT segmento, COUNT(*) as n, AVG(score_operativo) as avg_s, SUM(saldo_total) as saldo FROM clientes GROUP BY segmento")
    por_segmento = {}
    for row in cursor.fetchall():
        por_segmento[row["segmento"]] = {
            "count": row["n"],
            "avg_score": round(row["avg_s"] or 0, 1),
            "saldo": round(row["saldo"] or 0, 2),
        }

    cursor.execute("SELECT AVG(score_operativo) as s, AVG(prob_pago) as p FROM clientes")
    row = cursor.fetchone()
    avg_score = round(row["s"] or 0, 1)
    avg_prob = round((row["p"] or 0) * 100, 1)

    cursor.execute("SELECT SUM(saldo_total) as s FROM clientes")
    saldo_total = cursor.fetchone()["s"] or 0

    cursor.execute("SELECT COUNT(*) as n FROM cargas")
    total_cargas = cursor.fetchone()["n"]

    conn.close()
    return {
        "total_clientes": total,
        "por_segmento": por_segmento,
        "avg_score": avg_score,
        "avg_prob_pago": avg_prob,
        "saldo_total": saldo_total,
        "total_cargas": total_cargas,
    }


def get_all_clientes_df(limit: int = 50000) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        f"SELECT * FROM clientes ORDER BY score_operativo DESC LIMIT {limit}", conn
    )
    conn.close()
    return df
