-- Plantilla RRSS Full: bloques pacing_mes (PT-13) debajo de la fila de KPIs de cada página
-- de métricas. Idempotente por tipo+orden. Requiere el resolvedor pacing_mes.
CREATE OR REPLACE PROCEDURE pg_temp.agregar(p BIGINT, t TEXT, o INT, a INT, c JSONB)
LANGUAGE plpgsql AS $p$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM reporte_bloques WHERE pagina_id = p AND tipo = t AND orden = o) THEN
    INSERT INTO reporte_bloques (pagina_id, tipo, orden, ancho, config) VALUES (p, t, o, a, c);
  END IF;
END $p$;

DO $$
DECLARE v_plantilla BIGINT; v_pagina BIGINT; v_orden INT; r RECORD;
BEGIN
  SELECT id INTO v_plantilla FROM reporte_plantillas WHERE nombre = 'RRSS Full';
  FOR r IN SELECT * FROM (VALUES
      ('meta_ig',  'metricas', 'alcance',       'Alcance del mes'),
      ('meta_ig',  'metricas', 'seguidores',    'Seguidores a fin de mes'),
      ('meta_fb',  'metricas', 'interacciones', 'Interacciones del mes'),
      ('meta_fb',  'metricas', 'seguidores',    'Seguidores a fin de mes'),
      ('linkedin', 'metricas', 'impresiones',   'Impresiones del mes'),
      ('linkedin', 'metricas', 'seguidores',    'Seguidores a fin de mes'),
      ('tiktok',   'metricas', 'impresiones',   'Reproducciones del mes'),
      ('tiktok',   'metricas', 'seguidores',    'Seguidores a fin de mes'),
      ('youtube',  'metricas', 'impresiones',   'Vistas del mes'),
      ('youtube',  'metricas', 'seguidores',    'Suscriptores a fin de mes'),
      ('ga4',      'metricas', 'sesiones',      'Sesiones del mes'),
      ('ga4',      'metricas', 'conversiones_web', 'Conversiones del mes'),
      ('gsc',      'busqueda', 'clics_busqueda', 'Clics desde Google en el mes')
    ) AS t(plataforma, slug, metrica, etiqueta)
  LOOP
    SELECT id INTO v_pagina FROM reporte_paginas
     WHERE plantilla_id = v_plantilla AND plataforma = r.plataforma AND slug = r.slug;
    CONTINUE WHEN v_pagina IS NULL;
    -- Justo después de la primera fila de KPIs
    SELECT min(orden) INTO v_orden FROM reporte_bloques WHERE pagina_id = v_pagina AND tipo = 'kpi_fila';
    CONTINUE WHEN v_orden IS NULL;
    -- Dos bloques por página (ancho 6): el primero en orden+1, el segundo en orden+2
    IF NOT EXISTS (SELECT 1 FROM reporte_bloques WHERE pagina_id = v_pagina AND tipo = 'pacing_mes'
                   AND config->>'metrica' = r.metrica) THEN
      SELECT v_orden + 1 + count(*)::int INTO v_orden
        FROM reporte_bloques WHERE pagina_id = v_pagina AND tipo = 'pacing_mes';
      CALL pg_temp.agregar(v_pagina, 'pacing_mes', v_orden, 6,
        jsonb_build_object('metrica', r.metrica, 'etiqueta', r.etiqueta));
    END IF;
  END LOOP;
END $$;
