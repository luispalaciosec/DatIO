-- 011 — Endurecer el acceso vía PostgREST (alerta de Supabase 2026-09-13/22).
--
-- DatIO accede a Postgres SOLO desde la API (rol postgres vía DATABASE_URL). El frontend usa
-- la clave anónima únicamente para Auth y Storage; jamás consulta tablas. Sin embargo, por
-- defecto Supabase concede a anon/authenticated todos los privilegios sobre public y ninguna
-- tabla tenía RLS, así que cualquiera con la clave anónima (pública en el bundle) podía leer,
-- editar y borrar usuarios, credenciales, raw_payloads, etc.
--
-- Decisión: cerrar el esquema public a los roles de la API REST de Supabase en lugar de
-- escribir políticas por tabla. Es lo más simple y verificable: nada del producto depende
-- de PostgREST. RLS se activa además como segunda barrera (sin políticas = nada pasa).

-- 1) Quitar todo privilegio actual y futuro a los roles de PostgREST.
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES    FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES    FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;

-- 2) RLS en todas las tablas de public (segunda barrera). El rol postgres la salta.
DO $$
DECLARE t TEXT;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

-- 3) Las vistas respetan los permisos de quien consulta, no del creador.
ALTER VIEW public.v_metrica_actual           SET (security_invoker = on);
ALTER VIEW public.v_metrica_dimension_actual SET (security_invoker = on);
ALTER VIEW public.v_precision_modelo         SET (security_invoker = on);

-- 4) es_equipo(): la usan las políticas del bucket "marcas" (sql/003), que corren como el
-- usuario autenticado, así que debe seguir siendo SECURITY DEFINER para leer usuarios.
-- Se fija search_path y solo authenticated puede ejecutarla (anon no).
CREATE OR REPLACE FUNCTION public.es_equipo() RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.usuarios
        WHERE email = lower(auth.jwt() ->> 'email') AND rol = 'equipo' AND activo
    );
$$;
REVOKE EXECUTE ON FUNCTION public.es_equipo() FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.es_equipo() TO authenticated;
