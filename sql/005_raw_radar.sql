-- ============================================================================
-- 005 — raw_payloads acepta payloads del radar competitivo (sin cuenta_id)
-- Regla "raw antes de normalizar" también para Apify: cada snapshot de competidor
-- guarda su payload íntegro referenciando al competidor en vez de a una cuenta.
-- ============================================================================
ALTER TABLE raw_payloads ALTER COLUMN cuenta_id DROP NOT NULL;
ALTER TABLE raw_payloads ADD COLUMN competidor_id BIGINT REFERENCES cliente_competidores(id) ON DELETE CASCADE;
ALTER TABLE raw_payloads ADD CONSTRAINT chk_raw_origen CHECK (cuenta_id IS NOT NULL OR competidor_id IS NOT NULL);
CREATE INDEX idx_raw_competidor ON raw_payloads (competidor_id, capturado_en DESC) WHERE competidor_id IS NOT NULL;
