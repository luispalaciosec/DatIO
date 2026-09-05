-- ============================================================================
-- 003 — Bucket público "marcas" para logos y banners (módulo administrador)
--
-- Decisión: las imágenes de marca se suben desde el frontend con la sesión de Supabase
-- del usuario (sin claves nuevas en el servidor). Solo usuarios con rol 'equipo' en
-- public.usuarios pueden escribir; lectura pública porque son logos.
-- ============================================================================

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('marcas', 'marcas', TRUE, 5242880,
        ARRAY['image/png','image/jpeg','image/svg+xml','image/webp'])
ON CONFLICT (id) DO NOTHING;

CREATE OR REPLACE FUNCTION public.es_equipo() RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.usuarios
        WHERE email = lower(auth.jwt() ->> 'email') AND rol = 'equipo' AND activo
    );
$$;

DROP POLICY IF EXISTS "marcas lectura publica" ON storage.objects;
CREATE POLICY "marcas lectura publica" ON storage.objects
    FOR SELECT USING (bucket_id = 'marcas');

DROP POLICY IF EXISTS "marcas escribe equipo" ON storage.objects;
CREATE POLICY "marcas escribe equipo" ON storage.objects
    FOR INSERT TO authenticated WITH CHECK (bucket_id = 'marcas' AND public.es_equipo());

DROP POLICY IF EXISTS "marcas actualiza equipo" ON storage.objects;
CREATE POLICY "marcas actualiza equipo" ON storage.objects
    FOR UPDATE TO authenticated USING (bucket_id = 'marcas' AND public.es_equipo());

DROP POLICY IF EXISTS "marcas borra equipo" ON storage.objects;
CREATE POLICY "marcas borra equipo" ON storage.objects
    FOR DELETE TO authenticated USING (bucket_id = 'marcas' AND public.es_equipo());
