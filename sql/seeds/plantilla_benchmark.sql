-- Plantilla RRSS Full: páginas Benchmark completas (tabla comparativa, evolución de seguidores,
-- mejores publicaciones de la competencia). Idempotente por tipo+orden. Requiere sql/007 y los
-- resolvedores benchmark_tabla, benchmark_serie y benchmark_publicaciones.
CREATE OR REPLACE PROCEDURE pg_temp.agregar(p BIGINT, t TEXT, o INT, a INT, c JSONB)
LANGUAGE plpgsql AS $p$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM reporte_bloques WHERE pagina_id = p AND tipo = t AND orden = o) THEN
    INSERT INTO reporte_bloques (pagina_id, tipo, orden, ancho, config) VALUES (p, t, o, a, c);
  END IF;
END $p$;

DO $$
DECLARE v_plantilla BIGINT; v_pagina BIGINT; v_red TEXT;
BEGIN
  SELECT id INTO v_plantilla FROM reporte_plantillas WHERE nombre = 'RRSS Full';
  FOREACH v_red IN ARRAY ARRAY['meta_ig', 'meta_fb', 'tiktok'] LOOP
    SELECT id INTO v_pagina FROM reporte_paginas
     WHERE plantilla_id = v_plantilla AND plataforma = v_red AND slug = 'benchmark';
    CONTINUE WHEN v_pagina IS NULL;

    -- El grid de tarjetas pasa a ser el resumen de seguidores; el detalle va en la tabla.
    UPDATE reporte_bloques SET config = '{"titulo":"Seguidores frente a la competencia","bajada":"Quién tiene la audiencia más grande y cómo cambió desde la captura anterior del radar."}'
      WHERE pagina_id = v_pagina AND tipo = 'titulo_seccion' AND orden = 20;
    UPDATE reporte_bloques SET config = '{"metricas":["seguidores","publicaciones_semana","tasa_engagement"],"etiqueta_propio":"Tu marca"}'
      WHERE pagina_id = v_pagina AND tipo = 'benchmark_grid' AND orden = 30;

    CALL pg_temp.agregar(v_pagina, 'separador', 40, 12, '{}');
    CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 50, 12, '{"titulo":"Tabla comparativa","bajada":"Todas las marcas con la misma vara: promedios por publicación sobre las últimas 12, ritmo semanal, engagement y mezcla de formatos. Tu posición en cada columna."}');
    CALL pg_temp.agregar(v_pagina, 'benchmark_tabla', 60, 12, '{"etiqueta_propio":"Tu marca"}');
    CALL pg_temp.agregar(v_pagina, 'separador', 70, 12, '{}');
    CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 80, 12, '{"titulo":"Evolución de seguidores","bajada":"Tu crecimiento diario frente a las capturas semanales de la competencia."}');
    CALL pg_temp.agregar(v_pagina, 'benchmark_serie', 90, 12, '{"metrica":"seguidores","etiqueta_propio":"Tu marca"}');
    CALL pg_temp.agregar(v_pagina, 'separador', 100, 12, '{}');
    CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 110, 12, '{"titulo":"Lo que mejor le funciona a la competencia","bajada":"Sus publicaciones con más interacciones entre las últimas capturadas por el radar."}');
    CALL pg_temp.agregar(v_pagina, 'benchmark_publicaciones', 120, 12, '{"limite":8}');
  END LOOP;
END $$;
