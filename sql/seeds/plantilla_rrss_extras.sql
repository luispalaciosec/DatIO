-- Plantilla RRSS Full: bloques de dimensiones y publicaciones (idempotente por tipo+orden).
-- Requiere sql/006 y los resolvedores distribucion, demografia, tabla_ranking,
-- top_publicaciones, rendimiento_formato y mejor_dia.
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
  -- La segunda fila de KPIs (orden 35) no lleva tarjetas héroe
  UPDATE reporte_bloques b SET config = b.config || '{"destacar":0}'::jsonb
    FROM reporte_paginas p WHERE p.id = b.pagina_id AND p.plantilla_id = v_plantilla AND b.tipo = 'kpi_fila' AND b.orden = 35;

  -- Instagram · Métricas: audiencia y formato
  SELECT id INTO v_pagina FROM reporte_paginas WHERE plantilla_id = v_plantilla AND plataforma = 'meta_ig' AND slug = 'metricas';
  CALL pg_temp.agregar(v_pagina, 'separador', 65, 12, '{}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 70, 12, '{"titulo":"Audiencia","bajada":"Quiénes son tus seguidores. Datos de Instagram, actualizados en cada captura."}');
  CALL pg_temp.agregar(v_pagina, 'distribucion', 71, 6, '{"metrica":"seguidores","dimension":"ciudad","limite":10}');
  CALL pg_temp.agregar(v_pagina, 'distribucion', 72, 6, '{"metrica":"seguidores","dimension":"pais","limite":8}');
  CALL pg_temp.agregar(v_pagina, 'demografia', 73, 12, '{"metrica":"seguidores"}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 75, 12, '{"titulo":"Alcance por formato","bajada":"Qué formato llega a más personas en el período"}');
  CALL pg_temp.agregar(v_pagina, 'distribucion', 76, 6, '{"metrica":"alcance","dimension":"formato","modo":"suma","limite":6}');
  CALL pg_temp.agregar(v_pagina, 'distribucion', 77, 6, '{"metrica":"impresiones","dimension":"formato","modo":"suma","limite":6}');

  -- Instagram · Publicaciones
  SELECT id INTO v_pagina FROM reporte_paginas WHERE plantilla_id = v_plantilla AND plataforma = 'meta_ig' AND slug = 'publicaciones';
  UPDATE reporte_bloques SET orden = 50 WHERE pagina_id = v_pagina AND tipo = 'tabla_publicaciones';
  UPDATE reporte_bloques SET config = '{"titulo":"Mejores publicaciones","bajada":"Las que más interacción generaron en el período"}' WHERE pagina_id = v_pagina AND tipo = 'titulo_seccion' AND orden = 20;
  CALL pg_temp.agregar(v_pagina, 'top_publicaciones', 25, 12, '{"orden":"interacciones","limite":6,"metricas":["alcance","me_gusta","comentarios","guardados"]}');
  CALL pg_temp.agregar(v_pagina, 'separador', 27, 12, '{}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 28, 12, '{"titulo":"Rendimiento por formato","bajada":"Promedio por publicación según el tipo de contenido"}');
  CALL pg_temp.agregar(v_pagina, 'rendimiento_formato', 29, 7, '{"metricas":["alcance","interacciones","guardados"]}');
  CALL pg_temp.agregar(v_pagina, 'mejor_dia', 30, 5, '{}');
  CALL pg_temp.agregar(v_pagina, 'separador', 45, 12, '{}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 46, 12, '{"titulo":"Todas las publicaciones","bajada":"Ordenadas por interacciones"}');

  -- Facebook · Publicaciones
  SELECT id INTO v_pagina FROM reporte_paginas WHERE plantilla_id = v_plantilla AND plataforma = 'meta_fb' AND slug = 'publicaciones';
  UPDATE reporte_bloques SET orden = 50 WHERE pagina_id = v_pagina AND tipo = 'tabla_publicaciones';
  UPDATE reporte_bloques SET config = '{"titulo":"Mejores publicaciones","bajada":"Las que más interacción generaron en el período"}' WHERE pagina_id = v_pagina AND tipo = 'titulo_seccion' AND orden = 20;
  CALL pg_temp.agregar(v_pagina, 'top_publicaciones', 25, 12, '{"orden":"interacciones","limite":6,"metricas":["me_gusta","comentarios","compartidos","clics"]}');
  CALL pg_temp.agregar(v_pagina, 'separador', 27, 12, '{}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 28, 12, '{"titulo":"Rendimiento por formato","bajada":"Promedio por publicación según el tipo de contenido"}');
  CALL pg_temp.agregar(v_pagina, 'rendimiento_formato', 29, 7, '{"metricas":["interacciones","me_gusta","clics"]}');
  CALL pg_temp.agregar(v_pagina, 'mejor_dia', 30, 5, '{}');
  CALL pg_temp.agregar(v_pagina, 'separador', 45, 12, '{}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 46, 12, '{"titulo":"Todas las publicaciones","bajada":"Ordenadas por interacciones"}');

  -- Sitio web (GA4) · Métricas: origen del tráfico y páginas
  SELECT id INTO v_pagina FROM reporte_paginas WHERE plantilla_id = v_plantilla AND plataforma = 'ga4' AND slug = 'metricas';
  CALL pg_temp.agregar(v_pagina, 'separador', 65, 12, '{}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 70, 12, '{"titulo":"De dónde viene el tráfico","bajada":"Sesiones del período por canal, dispositivo y ubicación"}');
  CALL pg_temp.agregar(v_pagina, 'distribucion', 71, 6, '{"metrica":"sesiones","dimension":"canal","modo":"suma","limite":8}');
  CALL pg_temp.agregar(v_pagina, 'distribucion', 72, 6, '{"metrica":"sesiones","dimension":"dispositivo","modo":"suma","limite":4}');
  CALL pg_temp.agregar(v_pagina, 'distribucion', 73, 6, '{"metrica":"sesiones","dimension":"pais","modo":"suma","limite":8}');
  CALL pg_temp.agregar(v_pagina, 'distribucion', 74, 6, '{"metrica":"sesiones","dimension":"ciudad","modo":"suma","limite":8}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 80, 12, '{"titulo":"Páginas","bajada":"Las más vistas y las de entrada al sitio"}');
  CALL pg_temp.agregar(v_pagina, 'tabla_ranking', 81, 6, '{"dimension":"pagina","etiqueta_dimension":"Página","columnas":["paginas_vistas","sesiones"],"orden":"paginas_vistas","limite":10}');
  CALL pg_temp.agregar(v_pagina, 'tabla_ranking', 82, 6, '{"dimension":"pagina_destino","etiqueta_dimension":"Página de entrada","columnas":["sesiones","conversiones_web"],"orden":"sesiones","limite":10}');

  -- Búsqueda (Search Console): página nueva
  IF NOT EXISTS (SELECT 1 FROM reporte_paginas WHERE plantilla_id = v_plantilla AND plataforma = 'gsc') THEN
    INSERT INTO reporte_paginas (plantilla_id, plataforma, slug, titulo, orden, icono)
    VALUES (v_plantilla, 'gsc', 'busqueda', 'Búsqueda · Métricas', 65, 'busqueda') RETURNING id INTO v_pagina;
    CALL pg_temp.agregar(v_pagina, 'hero_banner', 10, 12, '{}');
    CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 20, 12, '{"titulo":"Búsqueda en Google","bajada":"Cómo aparece el sitio en los resultados de Google. Fuente: Search Console."}');
    CALL pg_temp.agregar(v_pagina, 'kpi_fila', 30, 12, '{"items":[{"metrica":"clics_busqueda","etiqueta":"Clics","formato":"entero","comparar":"periodo_anterior"},{"metrica":"impresiones_busqueda","etiqueta":"Impresiones","formato":"entero","comparar":"periodo_anterior"},{"metrica":"ctr_busqueda","etiqueta":"CTR","formato":"porcentaje","decimales":2},{"metrica":"posicion_promedio","etiqueta":"Posición promedio","formato":"entero","decimales":1}]}');
    CALL pg_temp.agregar(v_pagina, 'serie_temporal', 40, 12, '{"granularidad":"dia","series":[{"metrica":"clics_busqueda","color":"#4285F4","nota":"Clics desde resultados de Google"},{"metrica":"impresiones_busqueda","color":"#34A853","nota":"Veces que el sitio apareció en resultados"}],"mostrar_notas":true}');
    CALL pg_temp.agregar(v_pagina, 'separador', 45, 12, '{}');
    CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 50, 12, '{"titulo":"Consultas y páginas","bajada":"Con qué búsquedas te encuentran y qué páginas posicionan"}');
    CALL pg_temp.agregar(v_pagina, 'tabla_ranking', 51, 7, '{"dimension":"consulta","etiqueta_dimension":"Consulta","columnas":["clics_busqueda","impresiones_busqueda","ctr_busqueda","posicion_promedio"],"orden":"clics_busqueda","limite":15,"modo":"ultimo"}');
    CALL pg_temp.agregar(v_pagina, 'tabla_ranking', 52, 5, '{"dimension":"pagina","etiqueta_dimension":"Página","columnas":["clics_busqueda","impresiones_busqueda"],"orden":"clics_busqueda","limite":10,"modo":"ultimo"}');
    CALL pg_temp.agregar(v_pagina, 'distribucion', 53, 6, '{"metrica":"clics_busqueda","dimension":"dispositivo","modo":"suma","limite":3}');
    CALL pg_temp.agregar(v_pagina, 'distribucion', 54, 6, '{"metrica":"clics_busqueda","dimension":"pais","modo":"suma","limite":8}');
  END IF;
END $$;
