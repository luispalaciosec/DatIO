-- ============================================================================
-- 006 — Hechos por dimensión (ciudad, país, edad, género, canal, página, consulta, formato…)
--
-- fct_metrica_diaria guarda totales por cuenta/día. Las desagregaciones que devuelven las API
-- (seguidores por ciudad, sesiones por canal, clics por consulta, alcance por formato) van
-- aquí, en formato largo. Métricas "lifetime" (demografía) se guardan con fecha = snapshot.
-- ============================================================================

CREATE TABLE fct_metrica_dimension (
    cuenta_id        BIGINT  NOT NULL REFERENCES cuentas_conectadas(id),
    fecha            DATE    NOT NULL,
    metrica_codigo   TEXT    NOT NULL REFERENCES dim_metrica(codigo),
    dimension        TEXT    NOT NULL,   -- 'ciudad','pais','edad','genero','formato','canal',
                                         -- 'dispositivo','pagina','pagina_destino','consulta','hora'
    valor_dimension  TEXT    NOT NULL,
    valor            NUMERIC NOT NULL,
    fecha_snapshot   DATE    NOT NULL,
    PRIMARY KEY (cuenta_id, fecha, metrica_codigo, dimension, valor_dimension, fecha_snapshot)
);
CREATE INDEX idx_fct_dim_cuenta ON fct_metrica_dimension (cuenta_id, metrica_codigo, dimension, fecha DESC);

CREATE VIEW v_metrica_dimension_actual AS
SELECT DISTINCT ON (cuenta_id, fecha, metrica_codigo, dimension, valor_dimension)
       cuenta_id, fecha, metrica_codigo, dimension, valor_dimension, valor, fecha_snapshot
FROM   fct_metrica_dimension
ORDER  BY cuenta_id, fecha, metrica_codigo, dimension, valor_dimension, fecha_snapshot DESC;
