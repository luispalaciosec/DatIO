-- 013 — Conectores Zoho CRM y Google Business Profile (antes Google My Business).
INSERT INTO plataformas (codigo, nombre) VALUES
    ('zoho',           'CRM Zoho'),
    ('google_negocio', 'Google Business Profile')
ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre;
