-- PT-08: plantilla "RRSS Full" — páginas por red con los 6 bloques base (spec/03 §3-4).
-- Idempotente: si la plantilla ya existe no se toca (los IDs de bloque los usa el frontend).
DO $$
DECLARE
    v_plantilla BIGINT;
    v_pagina    BIGINT;
    r           RECORD;
BEGIN
    SELECT id INTO v_plantilla FROM reporte_plantillas WHERE nombre = 'RRSS Full';
    IF v_plantilla IS NOT NULL THEN
        RAISE NOTICE 'Plantilla RRSS Full ya existe (id %)', v_plantilla;
        RETURN;
    END IF;

    INSERT INTO reporte_plantillas (nombre, descripcion)
    VALUES ('RRSS Full', 'Métricas y publicaciones por red: Facebook, Instagram, LinkedIn, TikTok, YouTube, web')
    RETURNING id INTO v_plantilla;

    FOR r IN SELECT * FROM (VALUES
        ('meta_fb',  'Facebook',  1, 'facebook',
         '[{"metrica":"seguidores","etiqueta":"Seguidores","formato":"entero","agregacion":"ultimo"},
           {"metrica":"seguidores_nuevos","etiqueta":"Nuevos seguidores","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"interacciones","etiqueta":"Interacciones","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"visualizaciones_pagina","etiqueta":"Visitas a la página","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"reproducciones_video","etiqueta":"Reproducciones","formato":"entero","comparar":"periodo_anterior"}]'::jsonb,
         '[{"metrica":"interacciones","color":"#FBBC04","nota":"Interacciones totales: reacciones, comentarios, compartidos y clics"},
           {"metrica":"visualizaciones_pagina","color":"#4285F4","nota":"Veces que se vio el perfil de la página"},
           {"metrica":"reproducciones_video","color":"#34A853","nota":"Reproducciones de video de al menos 3 segundos"}]'::jsonb),
        ('meta_ig',  'Instagram', 2, 'instagram',
         '[{"metrica":"alcance","etiqueta":"Alcance","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"impresiones","etiqueta":"Visualizaciones","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"interacciones","etiqueta":"Interacciones","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"seguidores","etiqueta":"Seguidores","formato":"entero","agregacion":"ultimo"},
           {"metrica":"visitas_perfil","etiqueta":"Visitas al perfil","formato":"entero","comparar":"periodo_anterior"}]'::jsonb,
         '[{"metrica":"alcance","color":"#4285F4","nota":"Personas diferentes a las que se les mostró contenido"},
           {"metrica":"impresiones","color":"#34A853","nota":"Cantidad de veces que el contenido apareció en pantalla"},
           {"metrica":"interacciones","color":"#FBBC04","nota":"Me gusta, comentarios, compartidos y guardados"}]'::jsonb),
        ('linkedin', 'LinkedIn',  3, 'linkedin',
         '[{"metrica":"seguidores","etiqueta":"Seguidores","formato":"entero","agregacion":"ultimo"},
           {"metrica":"seguidores_nuevos","etiqueta":"Nuevos seguidores","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"impresiones","etiqueta":"Impresiones","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"interacciones","etiqueta":"Interacciones","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"clics","etiqueta":"Clics","formato":"entero","comparar":"periodo_anterior"}]'::jsonb,
         '[{"metrica":"impresiones","color":"#4285F4","nota":"Veces que se mostraron las publicaciones"},
           {"metrica":"interacciones","color":"#FBBC04","nota":"Reacciones, comentarios, compartidos y clics"},
           {"metrica":"seguidores_nuevos","color":"#34A853","nota":"Balance diario de seguidores ganados y perdidos"}]'::jsonb),
        ('tiktok',   'TikTok',    4, 'tiktok',
         '[{"metrica":"seguidores","etiqueta":"Seguidores","formato":"entero","agregacion":"ultimo"},
           {"metrica":"alcance","etiqueta":"Alcance","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"impresiones","etiqueta":"Reproducciones","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"interacciones","etiqueta":"Interacciones","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"me_gusta","etiqueta":"Me gusta","formato":"entero","comparar":"periodo_anterior"}]'::jsonb,
         '[{"metrica":"impresiones","color":"#4285F4","nota":"Reproducciones de los videos en el período"},
           {"metrica":"interacciones","color":"#FBBC04","nota":"Me gusta, comentarios y compartidos"},
           {"metrica":"seguidores_nuevos","color":"#34A853","nota":"Balance diario de seguidores"}]'::jsonb),
        ('youtube',  'YouTube',   5, 'youtube',
         '[{"metrica":"seguidores","etiqueta":"Suscriptores","formato":"entero","agregacion":"ultimo"},
           {"metrica":"impresiones","etiqueta":"Vistas","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"me_gusta","etiqueta":"Me gusta","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"comentarios","etiqueta":"Comentarios","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"tiempo_visualizacion_seg","etiqueta":"Tiempo de visualización","formato":"duracion","comparar":"periodo_anterior"}]'::jsonb,
         '[{"metrica":"impresiones","color":"#4285F4","nota":"Vistas de los videos"},
           {"metrica":"me_gusta","color":"#FBBC04","nota":"Me gusta recibidos"},
           {"metrica":"seguidores_nuevos","color":"#34A853","nota":"Suscriptores ganados"}]'::jsonb),
        ('ga4',      'Sitio web', 6, 'web',
         '[{"metrica":"sesiones","etiqueta":"Sesiones","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"usuarios_activos","etiqueta":"Usuarios","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"paginas_vistas","etiqueta":"Páginas vistas","formato":"entero","comparar":"periodo_anterior"},
           {"metrica":"tasa_rebote","etiqueta":"Tasa de rebote","formato":"porcentaje","decimales":1},
           {"metrica":"conversiones_web","etiqueta":"Conversiones","formato":"entero","comparar":"periodo_anterior"}]'::jsonb,
         '[{"metrica":"sesiones","color":"#4285F4","nota":"Visitas al sitio"},
           {"metrica":"usuarios_activos","color":"#34A853","nota":"Personas distintas que visitaron el sitio"},
           {"metrica":"paginas_vistas","color":"#FBBC04","nota":"Páginas vistas en total"}]'::jsonb)
    ) AS t(plataforma, titulo, orden, icono, kpis, series)
    LOOP
        INSERT INTO reporte_paginas (plantilla_id, plataforma, slug, titulo, orden, icono)
        VALUES (v_plantilla, r.plataforma, 'metricas', r.titulo || ' · Métricas', r.orden * 10, r.icono)
        RETURNING id INTO v_pagina;

        INSERT INTO reporte_bloques (pagina_id, tipo, orden, ancho, config) VALUES
        (v_pagina, 'hero_banner',     1, 12, '{}'),
        (v_pagina, 'titulo_seccion',  2, 12, '{"titulo":"KPIs claves del mes","bajada":"Comparado con el período anterior"}'),
        (v_pagina, 'kpi_fila',        3, 12, jsonb_build_object('items', r.kpis)),
        (v_pagina, 'separador',       4, 12, '{}'),
        (v_pagina, 'titulo_seccion',  5, 12, '{"titulo":"Evolutivo de los KPIs más importantes"}'),
        (v_pagina, 'serie_temporal',  6, 12, jsonb_build_object('granularidad', 'dia', 'series', r.series, 'mostrar_notas', true));
        -- distribucion_geo se agrega cuando exista el conector de audiencia (demografía, Ola 2)

        IF r.plataforma <> 'ga4' THEN
            INSERT INTO reporte_paginas (plantilla_id, plataforma, slug, titulo, orden, icono)
            VALUES (v_plantilla, r.plataforma, 'publicaciones', r.titulo || ' · Publicaciones', r.orden * 10 + 1, r.icono)
            RETURNING id INTO v_pagina;

            INSERT INTO reporte_bloques (pagina_id, tipo, orden, ancho, config) VALUES
            (v_pagina, 'hero_banner',    1, 12, '{}'),
            (v_pagina, 'titulo_seccion', 2, 12, '{"titulo":"Publicaciones del período","bajada":"Ordenadas por interacciones"}'),
            (v_pagina, 'tabla_publicaciones', 3, 12, '{"columnas":["alcance","impresiones","interacciones"],"orden":"interacciones","limite":20}');
        END IF;
    END LOOP;
END $$;
