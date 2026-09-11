-- PT-16: puente con el CRM. Cada cliente puede tener un CRM (prometio | hubspot) con la
-- referencia a su empresa y contacto allá. HubSpot lleva token privado por cliente (cifrado);
-- PrometIO usa las credenciales globales de la agencia (variables de entorno).
ALTER TABLE clientes
    ADD COLUMN IF NOT EXISTS crm_proveedor          TEXT,      -- 'prometio' | 'hubspot'
    ADD COLUMN IF NOT EXISTS crm_empresa_ref        TEXT,      -- id de empresa/company en el CRM
    ADD COLUMN IF NOT EXISTS crm_contacto_ref       TEXT,      -- id de contacto (PrometIO lo exige)
    ADD COLUMN IF NOT EXISTS crm_config             JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS crm_credencial_cifrada BYTEA;     -- pgcrypto, nunca texto plano

-- disparos_crm (sql/001) guarda cada acción enviada al CRM. Los ids de PrometIO son UUID,
-- por eso la referencia va en texto; error queda cuando el CRM rechazó la acción.
ALTER TABLE disparos_crm
    ADD COLUMN IF NOT EXISTS cliente_id     BIGINT REFERENCES clientes(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS crm_objeto_ref TEXT,
    ADD COLUMN IF NOT EXISTS titulo         TEXT,
    ADD COLUMN IF NOT EXISTS error          TEXT;
CREATE INDEX IF NOT EXISTS idx_disparos_cliente ON disparos_crm (cliente_id, codigo, disparado_en DESC);
