-- 016 · El bucket público "marcas" deja de aceptar SVG (S-7 / checklist #16).
--
-- DEPENDE DEL ESQUEMA storage DE SUPABASE: no existe en un Postgres vanilla, por eso
-- scripts/aplicar_sql.sh la excluye (igual que 003 y 011). Aplicar en Supabase.
--
-- Un SVG puede llevar scripts y el bucket es público: servido desde el dominio de Supabase
-- Storage se abriría como documento activo. Los logos y banners solo necesitan PNG, JPEG o
-- WebP. Los SVG ya subidos (si los hay) siguen ahí; revisarlos a mano con la consulta de abajo.
UPDATE storage.buckets
SET    allowed_mime_types = ARRAY['image/png', 'image/jpeg', 'image/webp']
WHERE  id = 'marcas';

-- Revisión manual (solo lectura):
-- SELECT name, metadata->>'mimetype' FROM storage.objects
-- WHERE bucket_id = 'marcas' AND (metadata->>'mimetype' = 'image/svg+xml' OR name ILIKE '%.svg');
