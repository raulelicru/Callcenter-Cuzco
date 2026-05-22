-- ============================================================
-- SETUP INICIAL — Ejecutar UNA SOLA VEZ en Supabase SQL Editor
-- ============================================================

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
    id              SERIAL PRIMARY KEY,
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
    id                     SERIAL PRIMARY KEY,
    usuario                TEXT,
    filename               TEXT,
    total_registros        INTEGER,
    registros_nuevos       INTEGER,
    registros_actualizados INTEGER,
    fecha_carga            TEXT
);

CREATE TABLE IF NOT EXISTS usuarios (
    id             SERIAL PRIMARY KEY,
    username       TEXT UNIQUE NOT NULL,
    nombre         TEXT NOT NULL,
    email          TEXT,
    rol            TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    activo         INTEGER DEFAULT 1,
    fecha_creacion TEXT DEFAULT CURRENT_DATE::TEXT
);

-- Trigger: protege fecha_primera_carga y auto-incrementa veces_procesado en UPDATE
CREATE OR REPLACE FUNCTION protect_cliente_history()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fecha_primera_carga := OLD.fecha_primera_carga;
    NEW.veces_procesado     := COALESCE(OLD.veces_procesado, 0) + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_protect_cliente ON clientes;
CREATE TRIGGER trg_protect_cliente
    BEFORE UPDATE ON clientes
    FOR EACH ROW EXECUTE FUNCTION protect_cliente_history();

-- Funcion RPC para metricas globales (evita transferir 353K filas)
CREATE OR REPLACE FUNCTION get_metricas_globales()
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
AS $$
    SELECT jsonb_build_object(
        'total_clientes', (SELECT COUNT(*) FROM clientes),
        'avg_score',      (SELECT ROUND(COALESCE(AVG(score_operativo),0)::numeric, 1) FROM clientes),
        'avg_prob_pago',  (SELECT ROUND((COALESCE(AVG(prob_pago),0)*100)::numeric, 1) FROM clientes),
        'saldo_total',    (SELECT ROUND(COALESCE(SUM(saldo_total),0)::numeric, 2) FROM clientes),
        'total_cargas',   (SELECT COUNT(*) FROM cargas),
        'por_segmento',   (
            SELECT COALESCE(jsonb_object_agg(
                segmento,
                jsonb_build_object(
                    'count',     cnt,
                    'avg_score', avg_s,
                    'saldo',     saldo
                )
            ), '{}'::jsonb)
            FROM (
                SELECT segmento,
                       COUNT(*)                                          AS cnt,
                       ROUND(COALESCE(AVG(score_operativo),0)::numeric, 1) AS avg_s,
                       ROUND(COALESCE(SUM(saldo_total),0)::numeric, 2)    AS saldo
                FROM clientes
                GROUP BY segmento
            ) s
        )
    );
$$;
