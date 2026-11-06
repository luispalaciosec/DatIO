-- Plantilla RRSS Full: bloque de narrativa en cada página de métricas, justo antes de los KPIs.
-- Toma los mismos items de la primera fila de KPIs de la página. Idempotente.
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT DISTINCT ON (p.id) p.id AS pagina_id, b.config -> 'items' AS items
    FROM   reporte_paginas p
    JOIN   reporte_plantillas t ON t.id = p.plantilla_id AND t.nombre = 'RRSS Full'
    JOIN   reporte_bloques b ON b.pagina_id = p.id AND b.tipo = 'kpi_fila'
    WHERE  p.slug IN ('metricas', 'busqueda')
    ORDER  BY p.id, b.orden
  LOOP
    IF NOT EXISTS (SELECT 1 FROM reporte_bloques WHERE pagina_id = r.pagina_id AND tipo = 'narrativa') THEN
      INSERT INTO reporte_bloques (pagina_id, tipo, orden, ancho, config)
      VALUES (r.pagina_id, 'narrativa', 25, 12, jsonb_build_object('items', r.items));
    END IF;
  END LOOP;
END $$;
