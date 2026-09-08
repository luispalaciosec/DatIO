-- PT-15 (benchmark completo): copia local de las imágenes de la competencia (foto de perfil y
-- miniaturas de publicaciones). Las URLs de la CDN de Instagram caducan en días y la CDN regional
-- bloquea la carga desde otro dominio (Cross-Origin-Resource-Policy: same-origin), así que el
-- radar descarga cada imagen una vez, la reduce (máx. 640 px) y la sirve la API en
-- GET /radar/imagen/{competidor_id}/{clave}. clave = 'perfil' o el id_externo de la publicación.
CREATE TABLE IF NOT EXISTS competidor_imagenes (
    competidor_id   BIGINT NOT NULL REFERENCES cliente_competidores(id) ON DELETE CASCADE,
    clave           TEXT   NOT NULL,
    tipo_mime       TEXT   NOT NULL,
    contenido       BYTEA  NOT NULL,
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (competidor_id, clave)
);
