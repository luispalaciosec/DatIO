-- PT-15b: columnas extra del radar de pauta sobre dim_anuncio_competencia (sql/001).
-- titulo/enlace/url_biblioteca vienen del actor; activo se apaga cuando un anuncio deja de
-- aparecer en una corrida. Los campos oferta y tono del esquema original se mantienen.
ALTER TABLE dim_anuncio_competencia
    ADD COLUMN IF NOT EXISTS titulo         TEXT,
    ADD COLUMN IF NOT EXISTS enlace         TEXT,
    ADD COLUMN IF NOT EXISTS url_biblioteca TEXT,
    ADD COLUMN IF NOT EXISTS activo         BOOLEAN NOT NULL DEFAULT TRUE;
CREATE INDEX IF NOT EXISTS idx_anuncio_comp_activo
    ON dim_anuncio_competencia (competidor_id, activo, primera_vez_visto);
