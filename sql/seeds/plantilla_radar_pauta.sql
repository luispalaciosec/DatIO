-- Plantilla RRSS Full: radar de pauta (PT-15b) en la página Benchmark de Facebook.
-- Idempotente por tipo+orden. Requiere sql/009 y los resolvedores radar_*.
CREATE OR REPLACE PROCEDURE pg_temp.agregar(p BIGINT, t TEXT, o INT, a INT, c JSONB)
LANGUAGE plpgsql AS $p$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM reporte_bloques WHERE pagina_id = p AND tipo = t AND orden = o) THEN
    INSERT INTO reporte_bloques (pagina_id, tipo, orden, ancho, config) VALUES (p, t, o, a, c);
  END IF;
END $p$;

DO $$
DECLARE v_plantilla BIGINT; v_pagina BIGINT;
BEGIN
  SELECT id INTO v_plantilla FROM reporte_plantillas WHERE nombre = 'RRSS Full';
  SELECT id INTO v_pagina FROM reporte_paginas
   WHERE plantilla_id = v_plantilla AND plataforma = 'meta_fb' AND slug = 'benchmark';
  IF v_pagina IS NULL THEN RETURN; END IF;
  CALL pg_temp.agregar(v_pagina, 'separador', 130, 12, '{}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 140, 12, '{"titulo":"Pauta de la competencia","bajada":"Qué anuncios corre cada competidor ahora mismo en Facebook e Instagram (Ecuador). Fuente: Biblioteca de anuncios de Meta, captura semanal."}');
  CALL pg_temp.agregar(v_pagina, 'radar_share_of_voice', 150, 12, '{}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 160, 12, '{"titulo":"Los anuncios que más les duran","bajada":"Un anuncio que lleva semanas activo es un anuncio que le está funcionando a alguien. Nadie sostiene pauta que no convierte."}');
  CALL pg_temp.agregar(v_pagina, 'radar_longevidad', 170, 12, '{"limite":8}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 180, 12, '{"titulo":"Anuncios activos","bajada":"Las creatividades vigentes, de la más nueva a la más antigua. Clic para abrirlas en la Biblioteca de anuncios."}');
  CALL pg_temp.agregar(v_pagina, 'radar_anuncios_activos', 190, 12, '{"limite":24,"orden":"recientes"}');
END $$;
