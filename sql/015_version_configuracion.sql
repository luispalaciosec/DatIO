-- 015 · Versión de configuración para invalidar la cache de /consulta (B-7 / R-2).
--
-- La cache en proceso de /consulta (api/consulta/cache.py) se invalidaba solo cuando cerraba
-- una corrida del ETL. Lo que el equipo edita (editor del reporte, tema, competidores, cuentas,
-- datos del cliente) cambia las respuestas cacheadas y tardaba hasta 15 min en verse; el PDF del
-- envío podía salir con la configuración anterior.
--
-- Una sola fila con un contador que suben triggers a nivel de sentencia en todas las tablas de
-- configuración. La API arma la "generación" de la cache con max(finalizado_en) del ETL y este
-- contador, así que invalida aunque corra en varios procesos y venga de donde venga la escritura.
-- No depende de los esquemas auth/storage de Supabase (CI la aplica).

CREATE TABLE IF NOT EXISTS config_version (
    id             SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    version        BIGINT      NOT NULL DEFAULT 0,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO config_version (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
-- Como el resto del esquema public (ver 011): sin acceso para anon/authenticated.
ALTER TABLE config_version ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION tocar_config_version() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
    UPDATE config_version SET version = version + 1, actualizado_en = NOW() WHERE id = 1;
    RETURN NULL;
END;
$$;

DO $$
DECLARE
    tabla TEXT;
BEGIN
    FOREACH tabla IN ARRAY ARRAY[
        'reporte_overrides', 'reporte_instancias', 'reporte_paginas', 'reporte_bloques',
        'cliente_tema', 'cliente_competidores', 'clientes', 'cuentas_conectadas'
    ] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS tocar_config_version ON %I', tabla);
        EXECUTE format(
            'CREATE TRIGGER tocar_config_version AFTER INSERT OR UPDATE OR DELETE ON %I '
            'FOR EACH STATEMENT EXECUTE FUNCTION tocar_config_version()', tabla);
    END LOOP;
END;
$$;
