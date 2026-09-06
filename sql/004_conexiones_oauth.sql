-- ============================================================================
-- 004 — Conexiones OAuth iniciadas desde el admin (botones "Conectar con ...")
--
-- Guarda el token obtenido en el retorno de OAuth (cifrado con pgcrypto) y la lista de
-- activos que ese token puede ver, hasta que el equipo elige cuáles convertir en
-- cuentas_conectadas. Las filas viven poco: se limpian al activar o a las 24 horas.
-- ============================================================================

CREATE TABLE conexiones_oauth (
    id               BIGSERIAL PRIMARY KEY,
    cliente_id       BIGINT NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    proveedor        TEXT   NOT NULL,          -- 'meta' | 'google'
    creado_por       TEXT   NOT NULL,          -- email del usuario de equipo
    token_cifrado    BYTEA  NOT NULL,          -- pgcrypto; nunca texto plano
    token_expira_en  TIMESTAMPTZ,
    activos          JSONB  NOT NULL DEFAULT '[]',
    estado           TEXT   NOT NULL DEFAULT 'pendiente',  -- 'pendiente' | 'activada'
    creado_en        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_conexiones_cliente ON conexiones_oauth (cliente_id, creado_en DESC);
