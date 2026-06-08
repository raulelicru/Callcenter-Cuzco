-- ============================================================
-- SETUP — Ejecutar UNA SOLA VEZ en Supabase SQL Editor
-- Guarda los tableros Excel generados por cuenta/empresa.
-- ============================================================

CREATE TABLE IF NOT EXISTS reporte_historico (
    id          SERIAL PRIMARY KEY,
    cuenta      TEXT NOT NULL,
    nombre      TEXT NOT NULL,           -- contactabilidad | recontacto | tipificacion
    excel_b64   TEXT,                    -- archivo Excel codificado en base64
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (cuenta, nombre)
);

-- Actualiza updated_at en cada upsert
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_touch_updated_at ON reporte_historico;
CREATE TRIGGER trg_touch_updated_at
    BEFORE UPDATE ON reporte_historico
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
