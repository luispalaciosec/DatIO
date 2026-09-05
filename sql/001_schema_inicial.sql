-- ============================================================================
-- PLATAFORMA DE REPORTERÍA — ESQUEMA CANÓNICO
-- Geeks Ecuador / Stack-Studio
--
-- FUENTE ÚNICA DE VERDAD. Los documentos en /spec contienen DDL ilustrativo;
-- si hay discrepancia, MANDA ESTE ARCHIVO.
--
-- PostgreSQL 15+
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================================
-- BLOQUE A — CLIENTES Y CUENTAS
-- ============================================================================

CREATE TABLE clientes (
    id              BIGSERIAL PRIMARY KEY,
    nombre          TEXT NOT NULL,
    slug            TEXT UNIQUE NOT NULL,
    sector          TEXT,                    -- 'banca','retail','salud','educacion'
                                             -- necesario para el modelo jerárquico (PT-14)
    crm_empresa_id  BIGINT,                  -- FK lógica al CRM (PT-16)
    activo          BOOLEAN DEFAULT TRUE,
    creado_en       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE plataformas (
    codigo  TEXT PRIMARY KEY,
    nombre  TEXT NOT NULL
);

INSERT INTO plataformas (codigo, nombre) VALUES
    ('meta_ig',    'Instagram'),
    ('meta_fb',    'Facebook'),
    ('meta_ads',   'Meta Ads'),
    ('tiktok',     'TikTok'),
    ('linkedin',   'LinkedIn'),
    ('youtube',    'YouTube'),
    ('ga4',        'Google Analytics 4'),
    ('gsc',        'Google Search Console'),
    ('google_ads', 'Google Ads');

CREATE TABLE cuentas_conectadas (
    id                  BIGSERIAL PRIMARY KEY,
    cliente_id          BIGINT NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    plataforma          TEXT   NOT NULL REFERENCES plataformas(codigo),
    id_externo          TEXT   NOT NULL,
    nombre_cuenta       TEXT,
    credencial_cifrada  BYTEA,               -- pgcrypto, NUNCA texto plano
    token_expira_en     TIMESTAMPTZ,         -- NULL = system user token (no expira)
    activo              BOOLEAN DEFAULT TRUE,
    creado_en           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (plataforma, id_externo)
);
CREATE INDEX idx_cuentas_cliente ON cuentas_conectadas (cliente_id) WHERE activo;

-- ============================================================================
-- BLOQUE B — CAPA SEMÁNTICA
-- Sin esto no hay gráficos cross-network. Se puebla ANTES que los conectores.
-- ============================================================================

CREATE TABLE dim_metrica (
    codigo          TEXT PRIMARY KEY,
    nombre_es       TEXT NOT NULL,
    unidad          TEXT NOT NULL,           -- 'conteo','porcentaje','moneda','segundos'
    agregacion      TEXT NOT NULL,           -- 'suma','promedio','ultimo','maximo'
    es_acumulada    BOOLEAN DEFAULT FALSE,   -- TRUE = lifetime (seguidores)
    proyectable     BOOLEAN DEFAULT TRUE,    -- FALSE para ratios volátiles (ver 04-capa-predictiva §7)
    categoria       TEXT NOT NULL            -- 'audiencia','contenido','pauta','web'
);

CREATE TABLE map_metrica_plataforma (
    plataforma      TEXT NOT NULL REFERENCES plataformas(codigo),
    metrica_nativa  TEXT NOT NULL,
    metrica_codigo  TEXT NOT NULL REFERENCES dim_metrica(codigo),
    factor          NUMERIC DEFAULT 1,
    PRIMARY KEY (plataforma, metrica_nativa)
);

-- ============================================================================
-- BLOQUE C — RAW (append-only, jamás se borra ni se modifica)
-- ============================================================================

CREATE TABLE raw_payloads (
    id              BIGSERIAL PRIMARY KEY,
    cuenta_id       BIGINT NOT NULL REFERENCES cuentas_conectadas(id),
    endpoint        TEXT   NOT NULL,
    params          JSONB,
    payload         JSONB  NOT NULL,
    capturado_en    TIMESTAMPTZ DEFAULT NOW(),
    job_id          BIGINT
);
CREATE INDEX idx_raw_cuenta_fecha ON raw_payloads (cuenta_id, capturado_en DESC);

-- ============================================================================
-- BLOQUE D — HECHOS
-- ============================================================================

CREATE TYPE estado_dato AS ENUM ('consolidado', 'provisional', 'proyectado');

CREATE TABLE fct_metrica_diaria (
    cuenta_id       BIGINT  NOT NULL REFERENCES cuentas_conectadas(id),
    fecha           DATE    NOT NULL,          -- fecha del dato
    metrica_codigo  TEXT    NOT NULL REFERENCES dim_metrica(codigo),
    valor           NUMERIC NOT NULL,
    fecha_snapshot  DATE    NOT NULL,          -- cuándo se capturó (auditoría de reatribución)
    estado          estado_dato NOT NULL DEFAULT 'consolidado',
    PRIMARY KEY (cuenta_id, fecha, metrica_codigo, fecha_snapshot)
);
CREATE INDEX idx_fct_cuenta_fecha ON fct_metrica_diaria (cuenta_id, fecha DESC);

-- Último snapshot por dato (lo que consume la API por defecto)
CREATE VIEW v_metrica_actual AS
SELECT DISTINCT ON (cuenta_id, fecha, metrica_codigo)
       cuenta_id, fecha, metrica_codigo, valor, fecha_snapshot, estado
FROM   fct_metrica_diaria
ORDER  BY cuenta_id, fecha, metrica_codigo, fecha_snapshot DESC;

CREATE TABLE dim_publicacion (
    id                   BIGSERIAL PRIMARY KEY,
    cuenta_id            BIGINT NOT NULL REFERENCES cuentas_conectadas(id),
    id_externo           TEXT   NOT NULL,
    tipo                 TEXT,               -- 'reel','carrusel','imagen','video','story'
    publicado_en         TIMESTAMPTZ,
    permalink            TEXT,
    caption              TEXT,
    thumbnail_url        TEXT,
    visto_por_ultima_vez DATE,               -- si desaparece, el histórico se conserva
    UNIQUE (cuenta_id, id_externo)
);

CREATE TABLE fct_publicacion_diaria (
    publicacion_id  BIGINT  NOT NULL REFERENCES dim_publicacion(id) ON DELETE CASCADE,
    fecha_snapshot  DATE    NOT NULL,
    metrica_codigo  TEXT    NOT NULL REFERENCES dim_metrica(codigo),
    valor           NUMERIC NOT NULL,
    PRIMARY KEY (publicacion_id, fecha_snapshot, metrica_codigo)
);

-- Atributos del Genoma de contenido (PT-17)
CREATE TABLE publicacion_atributos (
    publicacion_id  BIGINT PRIMARY KEY REFERENCES dim_publicacion(id) ON DELETE CASCADE,
    tema            TEXT,
    tono            TEXT,
    tiene_rostro    BOOLEAN,
    tiene_texto_img BOOLEAN,
    tipo_cta        TEXT,
    duracion_seg    INT,
    color_dominante TEXT,
    largo_copy      INT,
    clasificado_en  TIMESTAMPTZ DEFAULT NOW(),
    modelo_version  TEXT
);

-- ============================================================================
-- BLOQUE E — OBSERVABILIDAD
-- ============================================================================

CREATE TABLE jobs_ejecucion (
    id              BIGSERIAL PRIMARY KEY,
    cuenta_id       BIGINT REFERENCES cuentas_conectadas(id),
    conector        TEXT NOT NULL,
    estado          TEXT NOT NULL,           -- 'corriendo','ok','error','parcial'
    filas_escritas  INT DEFAULT 0,
    error_detalle   TEXT,
    iniciado_en     TIMESTAMPTZ DEFAULT NOW(),
    finalizado_en   TIMESTAMPTZ
);
CREATE INDEX idx_jobs_estado ON jobs_ejecucion (estado, iniciado_en DESC);

-- ============================================================================
-- BLOQUE F — REPORTES (plantillas, bloques, instancias, tema)
-- ============================================================================

CREATE TABLE reporte_plantillas (
    id          BIGSERIAL PRIMARY KEY,
    nombre      TEXT NOT NULL,
    descripcion TEXT,
    version     INT DEFAULT 1,
    activa      BOOLEAN DEFAULT TRUE
);

CREATE TABLE reporte_paginas (
    id           BIGSERIAL PRIMARY KEY,
    plantilla_id BIGINT NOT NULL REFERENCES reporte_plantillas(id) ON DELETE CASCADE,
    plataforma   TEXT REFERENCES plataformas(codigo),   -- NULL = cross-network
    slug         TEXT NOT NULL,
    titulo       TEXT NOT NULL,
    orden        INT  NOT NULL,
    icono        TEXT,
    UNIQUE (plantilla_id, plataforma, slug)
);

CREATE TABLE reporte_bloques (
    id         BIGSERIAL PRIMARY KEY,
    pagina_id  BIGINT NOT NULL REFERENCES reporte_paginas(id) ON DELETE CASCADE,
    tipo       TEXT   NOT NULL,             -- catálogo en 03-capa-presentacion §3
    orden      INT    NOT NULL,
    ancho      INT    DEFAULT 12,           -- grid de 12 columnas
    config     JSONB  NOT NULL DEFAULT '{}'
);

CREATE TABLE reporte_instancias (
    id             BIGSERIAL PRIMARY KEY,
    cliente_id     BIGINT NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    plantilla_id   BIGINT NOT NULL REFERENCES reporte_plantillas(id),
    nombre_publico TEXT,
    slug_publico   TEXT UNIQUE,
    activa         BOOLEAN DEFAULT TRUE,
    creada_en      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE reporte_overrides (
    instancia_id BIGINT NOT NULL REFERENCES reporte_instancias(id) ON DELETE CASCADE,
    bloque_id    BIGINT NOT NULL REFERENCES reporte_bloques(id) ON DELETE CASCADE,
    oculto       BOOLEAN DEFAULT FALSE,
    config_merge JSONB DEFAULT '{}',
    PRIMARY KEY (instancia_id, bloque_id)
);

CREATE TABLE cliente_tema (
    cliente_id       BIGINT PRIMARY KEY REFERENCES clientes(id) ON DELETE CASCADE,
    logo_url         TEXT,
    banner_url       TEXT,
    color_primario   TEXT DEFAULT '#C8102E',
    color_secundario TEXT DEFAULT '#1F1F1F',
    color_acento     TEXT DEFAULT '#F5F5F5',
    fuente_titulos   TEXT DEFAULT 'Inter',
    fuente_cuerpo    TEXT DEFAULT 'Inter',
    modo_oscuro      BOOLEAN DEFAULT FALSE
);

-- Analítica de uso: alimenta el Health Score (PT-19).
-- "Dejó de abrir el reporte" es la señal de fuga más predictiva.
CREATE TABLE reporte_visitas (
    id            BIGSERIAL PRIMARY KEY,
    instancia_id  BIGINT REFERENCES reporte_instancias(id) ON DELETE CASCADE,
    usuario_email TEXT,
    pagina_slug   TEXT,
    visto_en      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_visitas_instancia ON reporte_visitas (instancia_id, visto_en DESC);

-- ============================================================================
-- BLOQUE G — COMPETENCIA (Radar)
-- NOTA: cadencia SEMANAL, no diaria. Ver 07-infraestructura §Apify.
-- ============================================================================

CREATE TABLE cliente_competidores (
    id           BIGSERIAL PRIMARY KEY,
    cliente_id   BIGINT NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    plataforma   TEXT   NOT NULL REFERENCES plataformas(codigo),
    nombre       TEXT   NOT NULL,
    handle       TEXT   NOT NULL,
    logo_url     TEXT,
    orden        INT DEFAULT 0,
    UNIQUE (cliente_id, plataforma, handle)
);

CREATE TABLE fct_competidor_snapshot (
    competidor_id   BIGINT  NOT NULL REFERENCES cliente_competidores(id) ON DELETE CASCADE,
    fecha_snapshot  DATE    NOT NULL,
    metrica_codigo  TEXT    NOT NULL REFERENCES dim_metrica(codigo),
    valor           NUMERIC NOT NULL,
    PRIMARY KEY (competidor_id, fecha_snapshot, metrica_codigo)
);

-- Radar de pauta. La columna de valor es dias_activo: un anuncio que lleva
-- 90 días corriendo es un anuncio que funciona.
CREATE TABLE dim_anuncio_competencia (
    id                 BIGSERIAL PRIMARY KEY,
    competidor_id      BIGINT NOT NULL REFERENCES cliente_competidores(id) ON DELETE CASCADE,
    ad_archive_id      TEXT   NOT NULL,
    primera_vez_visto  DATE   NOT NULL,
    ultima_vez_visto   DATE   NOT NULL,
    plataformas        TEXT[],
    creatividad_url    TEXT,
    copy_texto         TEXT,
    formato            TEXT,
    oferta             TEXT,
    tono               TEXT,
    UNIQUE (competidor_id, ad_archive_id)
);

-- ============================================================================
-- BLOQUE H — PROYECCIONES
-- ============================================================================

CREATE TABLE fct_proyeccion (
    id              BIGSERIAL PRIMARY KEY,
    cuenta_id       BIGINT  NOT NULL REFERENCES cuentas_conectadas(id),
    metrica_codigo  TEXT    NOT NULL REFERENCES dim_metrica(codigo),
    fecha_objetivo  DATE    NOT NULL,
    corrida_en      DATE    NOT NULL,
    horizonte_dias  INT     NOT NULL,
    valor_p50       NUMERIC NOT NULL,
    valor_p10       NUMERIC,
    valor_p90       NUMERIC,
    modelo          TEXT    NOT NULL,
    modelo_version  TEXT    NOT NULL,
    features        JSONB,
    CONSTRAINT uq_proyeccion
        UNIQUE (cuenta_id, metrica_codigo, fecha_objetivo, corrida_en, modelo)
);
CREATE INDEX idx_proy_cuenta ON fct_proyeccion (cuenta_id, fecha_objetivo);

CREATE TABLE fct_proyeccion_eval (
    proyeccion_id BIGINT PRIMARY KEY REFERENCES fct_proyeccion(id) ON DELETE CASCADE,
    valor_real    NUMERIC NOT NULL,
    error_abs     NUMERIC,
    dentro_banda  BOOLEAN,
    evaluado_en   DATE DEFAULT CURRENT_DATE
);

CREATE VIEW v_precision_modelo AS
SELECT p.modelo, p.metrica_codigo, p.horizonte_dias,
       COUNT(*)                                        AS n,
       AVG(e.error_abs / NULLIF(e.valor_real, 0))*100  AS mape,
       AVG(e.dentro_banda::int) * 100                  AS cobertura_banda
FROM   fct_proyeccion p
JOIN   fct_proyeccion_eval e ON e.proyeccion_id = p.id
GROUP  BY 1, 2, 3;

-- ============================================================================
-- BLOQUE I — PUENTE CRM Y ALERTAS
-- ============================================================================

CREATE TABLE disparos_crm (
    id             BIGSERIAL PRIMARY KEY,
    cuenta_id      BIGINT REFERENCES cuentas_conectadas(id),
    codigo         TEXT NOT NULL,            -- código del disparador
    contexto       JSONB,
    crm_objeto_id  BIGINT,                   -- id devuelto por el CRM
    disparado_en   TIMESTAMPTZ DEFAULT NOW()
);
-- Anti-duplicado: ver guardrail de ventana de 30 días en 05-roadmap §Ficha 6
CREATE INDEX idx_disparos_dedupe ON disparos_crm (cuenta_id, codigo, disparado_en DESC);

CREATE TABLE alertas (
    id            BIGSERIAL PRIMARY KEY,
    cuenta_id     BIGINT REFERENCES cuentas_conectadas(id),
    tipo          TEXT NOT NULL,             -- 'anomalia','oportunidad','operativa'
    severidad     TEXT NOT NULL,             -- 'alta','media','baja'
    titulo        TEXT NOT NULL,
    detalle       JSONB,
    resuelta      BOOLEAN DEFAULT FALSE,
    creada_en     TIMESTAMPTZ DEFAULT NOW()
);
