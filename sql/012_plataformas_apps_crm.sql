-- 012 — Nuevos conectores: tiendas de apps y CRM como fuente de datos.
-- App Store Connect (ventas y reseñas), Google Play Console (informes en Cloud Storage),
-- PrometIO y HubSpot (pipeline comercial). Las métricas van en sql/seeds/metricas.sql.
INSERT INTO plataformas (codigo, nombre) VALUES
    ('app_store',   'App Store'),
    ('google_play', 'Google Play'),
    ('prometio',    'CRM PrometIO'),
    ('hubspot',     'CRM HubSpot')
ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre;
