-- ============================================================================
-- 002 — Usuarios (Supabase Auth → cliente) y registro de uso de LLM
--
-- Decisiones (documentadas en el PR de PT-07 / PT-01):
--  * usuarios: la autenticación la hace Supabase Auth (errata E-05). Esta tabla
--    solo resuelve email → cliente_id en el servidor. cliente_id NUNCA viene del
--    request. rol 'equipo' = Geeks/Stack-Studio (cliente_id NULL, ve todo).
--  * llm_uso: spec/07 §5 exige registrar cada llamada desde el día 1.
-- ============================================================================

CREATE TABLE usuarios (
    email       TEXT PRIMARY KEY,
    cliente_id  BIGINT REFERENCES clientes(id) ON DELETE CASCADE,
    rol         TEXT NOT NULL DEFAULT 'cliente',   -- 'cliente' | 'equipo'
    activo      BOOLEAN DEFAULT TRUE,
    creado_en   TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_usuario_rol CHECK (
        (rol = 'equipo'  AND cliente_id IS NULL) OR
        (rol = 'cliente' AND cliente_id IS NOT NULL)
    )
);
CREATE INDEX idx_usuarios_cliente ON usuarios (cliente_id) WHERE activo;

CREATE TABLE llm_uso (
    id             BIGSERIAL PRIMARY KEY,
    tarea          TEXT NOT NULL,            -- 'clasificacion','narrativa','agente'
    proveedor      TEXT NOT NULL,
    modelo         TEXT NOT NULL,
    cliente_id     BIGINT REFERENCES clientes(id) ON DELETE SET NULL,
    tokens_entrada INT  NOT NULL DEFAULT 0,
    tokens_salida  INT  NOT NULL DEFAULT 0,
    costo_usd      NUMERIC(10,6),
    latencia_ms    INT,
    exito          BOOLEAN NOT NULL DEFAULT TRUE,
    error_detalle  TEXT,
    creado_en      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_llm_uso_tarea_fecha ON llm_uso (tarea, creado_en DESC);
