-- PT-15 (benchmark completo): últimas publicaciones de cada competidor, tal como las devuelve
-- el radar (Apify). Permite comparar formato, ritmo y mejores publicaciones de la competencia.
-- Se actualiza en cada corrida del radar; el histórico de métricas por publicación no se
-- conserva (basta el último valor visto para el benchmark).
CREATE TABLE IF NOT EXISTS competidor_publicaciones (
    competidor_id   BIGINT NOT NULL REFERENCES cliente_competidores(id) ON DELETE CASCADE,
    id_externo      TEXT   NOT NULL,
    tipo            TEXT,                    -- 'reel','carrusel','imagen','video'
    publicado_en    TIMESTAMPTZ,
    permalink       TEXT,
    caption         TEXT,
    thumbnail_url   TEXT,
    me_gusta        NUMERIC,
    comentarios     NUMERIC,
    reproducciones  NUMERIC,
    fecha_snapshot  DATE   NOT NULL,
    PRIMARY KEY (competidor_id, id_externo)
);
CREATE INDEX IF NOT EXISTS idx_competidor_pub_fecha
    ON competidor_publicaciones (competidor_id, publicado_en DESC);
