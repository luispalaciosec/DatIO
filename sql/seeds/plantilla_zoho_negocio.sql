-- Plantilla RRSS Full: páginas CRM Zoho y Google Business Profile. Idempotente.
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

  -- Zoho: misma página que los otros CRM
  SELECT id INTO v_pagina FROM reporte_paginas WHERE plantilla_id = v_plantilla AND plataforma = 'zoho' AND slug = 'metricas';
  IF v_pagina IS NULL THEN
    INSERT INTO reporte_paginas (plantilla_id, plataforma, slug, titulo, orden) VALUES (v_plantilla, 'zoho', 'metricas', 'CRM', 82) RETURNING id INTO v_pagina;
  END IF;
  CALL pg_temp.agregar(v_pagina, 'hero_banner', 10, 12, '{}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 20, 12, '{"titulo":"KPIs del período","bajada":"Actividad comercial: contactos y oportunidades nuevas, cierres y pipeline. Fuente: Zoho CRM."}');
  CALL pg_temp.agregar(v_pagina, 'kpi_fila', 30, 12, '{"items":[
    {"metrica":"contactos_nuevos","etiqueta":"Contactos nuevos","formato":"entero","comparar":"periodo_anterior"},
    {"metrica":"oportunidades_creadas","etiqueta":"Oportunidades creadas","formato":"entero","comparar":"periodo_anterior"},
    {"metrica":"oportunidades_ganadas","etiqueta":"Ganadas","formato":"entero","comparar":"periodo_anterior"},
    {"metrica":"valor_ganado","etiqueta":"Valor ganado","formato":"moneda","comparar":"periodo_anterior"},
    {"metrica":"valor_pipeline","etiqueta":"Pipeline abierto","formato":"moneda","agregacion":"ultimo"}]}');
  CALL pg_temp.agregar(v_pagina, 'separador', 40, 12, '{}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 50, 12, '{"titulo":"Evolutivo comercial","bajada":"Contactos y oportunidades nuevas por semana, y cierres"}');
  CALL pg_temp.agregar(v_pagina, 'serie_temporal', 60, 12, '{"granularidad":"semana","mostrar_notas":true,"series":[
    {"metrica":"contactos_nuevos","color":"#4285F4","nota":"Contactos creados en el CRM"},
    {"metrica":"oportunidades_creadas","color":"#FBBC04","nota":"Oportunidades abiertas en el CRM"},
    {"metrica":"oportunidades_ganadas","color":"#34A853","nota":"Cierres ganados"},
    {"metrica":"oportunidades_perdidas","color":"#EA4335","nota":"Cierres perdidos"}]}');
  CALL pg_temp.agregar(v_pagina, 'pacing_mes', 65, 12, '{"metrica":"valor_ganado","etiqueta":"Valor ganado"}');

  -- Google Business Profile
  SELECT id INTO v_pagina FROM reporte_paginas WHERE plantilla_id = v_plantilla AND plataforma = 'google_negocio' AND slug = 'metricas';
  IF v_pagina IS NULL THEN
    INSERT INTO reporte_paginas (plantilla_id, plataforma, slug, titulo, orden) VALUES (v_plantilla, 'google_negocio', 'metricas', 'Google Negocio', 66) RETURNING id INTO v_pagina;
  END IF;
  CALL pg_temp.agregar(v_pagina, 'hero_banner', 10, 12, '{}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 20, 12, '{"titulo":"KPIs del período","bajada":"Cómo encuentran y contactan al negocio desde Google Maps y la Búsqueda. Fuente: Google Business Profile."}');
  CALL pg_temp.agregar(v_pagina, 'kpi_fila', 30, 12, '{"items":[
    {"metrica":"vistas_maps","etiqueta":"Vistas en Maps","formato":"entero","comparar":"periodo_anterior"},
    {"metrica":"vistas_busqueda_negocio","etiqueta":"Vistas en Búsqueda","formato":"entero","comparar":"periodo_anterior"},
    {"metrica":"llamadas","etiqueta":"Llamadas","formato":"entero","comparar":"periodo_anterior"},
    {"metrica":"indicaciones","etiqueta":"Indicaciones","formato":"entero","comparar":"periodo_anterior"},
    {"metrica":"clics_sitio_web","etiqueta":"Clics al sitio","formato":"entero","comparar":"periodo_anterior"}]}');
  CALL pg_temp.agregar(v_pagina, 'kpi_fila', 35, 12, '{"destacar":0,"items":[
    {"metrica":"conversaciones","etiqueta":"Mensajes","formato":"entero","comparar":"periodo_anterior"},
    {"metrica":"reservas","etiqueta":"Reservas","formato":"entero","comparar":"periodo_anterior"},
    {"metrica":"calificaciones","etiqueta":"Reseñas recibidas","formato":"entero","comparar":"periodo_anterior"},
    {"metrica":"calificacion_promedio","etiqueta":"Calificación","formato":"entero","decimales":2}]}');
  CALL pg_temp.agregar(v_pagina, 'separador', 40, 12, '{}');
  CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 50, 12, '{"titulo":"Evolutivo","bajada":"Vistas de la ficha y acciones de los clientes, por día"}');
  CALL pg_temp.agregar(v_pagina, 'serie_temporal', 60, 12, '{"granularidad":"dia","mostrar_notas":true,"series":[
    {"metrica":"vistas_maps","color":"#34A853","nota":"Veces que la ficha apareció en Google Maps"},
    {"metrica":"vistas_busqueda_negocio","color":"#4285F4","nota":"Veces que la ficha apareció en la Búsqueda"}]}');
  CALL pg_temp.agregar(v_pagina, 'serie_temporal', 61, 12, '{"granularidad":"dia","mostrar_notas":true,"series":[
    {"metrica":"llamadas","color":"#EA4335","nota":"Clics en el botón de llamar"},
    {"metrica":"indicaciones","color":"#FBBC04","nota":"Solicitudes de cómo llegar"},
    {"metrica":"clics_sitio_web","color":"#9333EA","nota":"Clics al sitio web desde la ficha"}]}');
  CALL pg_temp.agregar(v_pagina, 'pacing_mes', 65, 12, '{"metrica":"llamadas","etiqueta":"Llamadas"}');
END $$;
