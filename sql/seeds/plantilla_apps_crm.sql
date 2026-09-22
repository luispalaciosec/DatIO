-- Plantilla RRSS Full: páginas para App Store, Google Play y CRM (PrometIO / HubSpot).
-- Idempotente: no duplica páginas ni bloques. Requiere sql/012 y el seed de métricas.
CREATE OR REPLACE PROCEDURE pg_temp.agregar(p BIGINT, t TEXT, o INT, a INT, c JSONB)
LANGUAGE plpgsql AS $p$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM reporte_bloques WHERE pagina_id = p AND tipo = t AND orden = o) THEN
    INSERT INTO reporte_bloques (pagina_id, tipo, orden, ancho, config) VALUES (p, t, o, a, c);
  END IF;
END $p$;

DO $$
DECLARE v_plantilla BIGINT; v_pagina BIGINT; r RECORD;
BEGIN
  SELECT id INTO v_plantilla FROM reporte_plantillas WHERE nombre = 'RRSS Full';

  FOR r IN SELECT * FROM (VALUES
    ('app_store',   'App Store',   70, 'Cómo va la app en la App Store: descargas, actualizaciones, ingresos y calificaciones. Fuente: App Store Connect.'),
    ('google_play', 'Google Play', 71, 'Cómo va la app en Google Play: instalaciones, desinstalaciones, dispositivos activos y calificación. Fuente: Play Console.'),
    ('prometio',    'CRM',         80, 'Actividad comercial: contactos y oportunidades nuevas, cierres y pipeline. Fuente: PrometIO.'),
    ('hubspot',     'CRM',         81, 'Actividad comercial: contactos y oportunidades nuevas, cierres y pipeline. Fuente: HubSpot.')
  ) AS t(plataforma, titulo, orden, bajada) LOOP
    SELECT id INTO v_pagina FROM reporte_paginas
     WHERE plantilla_id = v_plantilla AND plataforma = r.plataforma AND slug = 'metricas';
    IF v_pagina IS NULL THEN
      INSERT INTO reporte_paginas (plantilla_id, plataforma, slug, titulo, orden)
      VALUES (v_plantilla, r.plataforma, 'metricas', r.titulo, r.orden) RETURNING id INTO v_pagina;
    END IF;
    CALL pg_temp.agregar(v_pagina, 'hero_banner', 10, 12, '{}');
    CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 20, 12, jsonb_build_object('titulo', 'KPIs del período', 'bajada', r.bajada));

    IF r.plataforma IN ('app_store', 'google_play') THEN
      CALL pg_temp.agregar(v_pagina, 'kpi_fila', 30, 12, '{"items":[
        {"metrica":"descargas","etiqueta":"Descargas","formato":"entero","comparar":"periodo_anterior"},
        {"metrica":"actualizaciones_app","etiqueta":"Actualizaciones","formato":"entero","comparar":"periodo_anterior"},
        {"metrica":"calificacion_promedio","etiqueta":"Calificación","formato":"entero","decimales":2},
        {"metrica":"ingresos_app","etiqueta":"Ingresos","formato":"moneda","comparar":"periodo_anterior"},
        {"metrica":"dispositivos_activos","etiqueta":"Dispositivos activos","formato":"entero","agregacion":"ultimo"}]}');
      CALL pg_temp.agregar(v_pagina, 'separador', 40, 12, '{}');
      CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 50, 12, '{"titulo":"Evolutivo","bajada":"Descargas diarias frente a desinstalaciones y actualizaciones"}');
      CALL pg_temp.agregar(v_pagina, 'serie_temporal', 60, 12, '{"granularidad":"dia","mostrar_notas":true,"series":[
        {"metrica":"descargas","color":"#4285F4","nota":"Instalaciones nuevas del día"},
        {"metrica":"desinstalaciones","color":"#EA4335","nota":"Dispositivos que quitaron la app"},
        {"metrica":"actualizaciones_app","color":"#34A853","nota":"Actualizaciones a una versión nueva"}]}');
      CALL pg_temp.agregar(v_pagina, 'pacing_mes', 65, 12, '{"metrica":"descargas","etiqueta":"Descargas"}');
      CALL pg_temp.agregar(v_pagina, 'separador', 70, 12, '{}');
      CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 80, 12, '{"titulo":"De dónde descargan","bajada":"Descargas del período por país"}');
      CALL pg_temp.agregar(v_pagina, 'distribucion', 90, 6, '{"metrica":"descargas","dimension":"pais","limite":8,"modo":"suma"}');
      CALL pg_temp.agregar(v_pagina, 'serie_temporal', 91, 6, '{"granularidad":"dia","series":[
        {"metrica":"calificacion_promedio","color":"#FBBC04","nota":"Calificación promedio de las reseñas del día"},
        {"metrica":"fallos_app","color":"#EA4335","nota":"Fallos reportados (solo Google Play)"}]}');
    ELSE
      CALL pg_temp.agregar(v_pagina, 'kpi_fila', 30, 12, '{"items":[
        {"metrica":"contactos_nuevos","etiqueta":"Contactos nuevos","formato":"entero","comparar":"periodo_anterior"},
        {"metrica":"oportunidades_creadas","etiqueta":"Oportunidades creadas","formato":"entero","comparar":"periodo_anterior"},
        {"metrica":"oportunidades_ganadas","etiqueta":"Ganadas","formato":"entero","comparar":"periodo_anterior"},
        {"metrica":"valor_ganado","etiqueta":"Valor ganado","formato":"moneda","comparar":"periodo_anterior"},
        {"metrica":"valor_pipeline","etiqueta":"Pipeline abierto","formato":"moneda","agregacion":"ultimo"}]}');
      CALL pg_temp.agregar(v_pagina, 'separador', 40, 12, '{}');
      CALL pg_temp.agregar(v_pagina, 'titulo_seccion', 50, 12, '{"titulo":"Evolutivo comercial","bajada":"Contactos y oportunidades nuevas por día, y cierres"}');
      CALL pg_temp.agregar(v_pagina, 'serie_temporal', 60, 12, '{"granularidad":"semana","mostrar_notas":true,"series":[
        {"metrica":"contactos_nuevos","color":"#4285F4","nota":"Contactos creados en el CRM"},
        {"metrica":"oportunidades_creadas","color":"#FBBC04","nota":"Oportunidades abiertas en el CRM"},
        {"metrica":"oportunidades_ganadas","color":"#34A853","nota":"Cierres ganados"},
        {"metrica":"oportunidades_perdidas","color":"#EA4335","nota":"Cierres perdidos"}]}');
      CALL pg_temp.agregar(v_pagina, 'pacing_mes', 65, 12, '{"metrica":"valor_ganado","etiqueta":"Valor ganado"}');
    END IF;
  END LOOP;
END $$;
