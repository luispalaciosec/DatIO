-- 014 — Estreno con clientes: invitaciones, narrativa cacheada y envíos del reporte mensual.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS invitado_en TIMESTAMPTZ;

-- Narrativa del período por página (texto generado a partir de hechos ya calculados).
-- fuente: 'ia' si el LLM la redactó y pasó la validación de cifras; 'reglas' si es la base.
CREATE TABLE IF NOT EXISTS narrativas (
    cliente_id   BIGINT NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    plataforma   TEXT   NOT NULL,
    desde        DATE   NOT NULL,
    hasta        DATE   NOT NULL,
    generada_el  DATE   NOT NULL DEFAULT CURRENT_DATE,
    texto        TEXT   NOT NULL,
    fuente       TEXT   NOT NULL,
    hechos       JSONB  NOT NULL,
    PRIMARY KEY (cliente_id, plataforma, desde, hasta)
);

-- Un envío del reporte mensual por instancia y período (idempotencia del cron).
CREATE TABLE IF NOT EXISTS envios_reporte (
    id            BIGSERIAL PRIMARY KEY,
    instancia_id  BIGINT NOT NULL REFERENCES reporte_instancias(id) ON DELETE CASCADE,
    periodo       DATE   NOT NULL,          -- primer día del mes reportado
    destinatarios TEXT[] NOT NULL,
    automatico    BOOLEAN NOT NULL DEFAULT TRUE,
    estado        TEXT   NOT NULL,          -- 'enviado' | 'error' | 'sin_destinatarios'
    error         TEXT,
    enviado_en    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_envios_instancia ON envios_reporte (instancia_id, periodo);

ALTER TABLE narrativas     ENABLE ROW LEVEL SECURITY;
ALTER TABLE envios_reporte ENABLE ROW LEVEL SECURITY;
