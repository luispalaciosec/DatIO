# Plan: Plataforma de reportería propia para redes sociales y pauta
### Reemplazo de Supermetrics + Looker Studio — Geeks Ecuador

---

## 1. Diagnóstico: el problema real no es Supermetrics

Lo que te está doliendo no es el conector, es el **modelo arquitectónico**.

Supermetrics + Looker Studio es una **tubería sin bodega**. Cada vez que abres un dashboard, Looker le pide a Supermetrics, Supermetrics le pide a la API de Meta/TikTok/LinkedIn, y te devuelve lo que la API le quiera dar **en ese momento**.

Las ventanas de 7 / 14 / 28 días **no son un límite de Supermetrics**: son límites de las APIs de origen.

| Fuente | Límite real |
|---|---|
| Instagram Insights (cuenta) | Muchas métricas solo 30 días hacia atrás; `online_followers` últimos 30 días |
| Instagram Stories | Métricas mueren a las 24h de expirar la historia |
| Instagram Media | Insights existen mientras exista el post; si lo borran, se pierde todo |
| Meta Ads | Reatribuye conversiones hasta ~28 días después (el dato de ayer cambia mañana) |
| TikTok Business | Ventanas de consulta acotadas por request |
| LinkedIn Pages | 12 meses, pero con agregaciones fijas poco flexibles |
| Google Search Console | 16 meses y ahí muere |

**Conclusión dura:** ninguna herramienta del mercado —ni Supermetrics, ni Funnel, ni Windsor.ai— puede devolverte lo que no guardaste. Pagar más caro no resuelve esto. Lo único que lo resuelve es **capturar diariamente y persistir en tu propia base**.

Y ahí está la buena noticia: eso convierte tu limitación en una **ventaja competitiva vendible**. Ninguna agencia en Ecuador le entrega al cliente comparativos año contra año reales de orgánico. Tú sí vas a poder, porque vas a tener la historia.

> ⚠️ **Lo más urgente de todo este documento:** cada día que pasa sin capturar es data que **nunca** vas a poder recuperar. La captura debe arrancar antes que el dashboard, antes que el diseño, antes que todo.

---

## 2. Arquitectura propuesta

Cinco capas, desacopladas. Cada una se puede construir y probar sola.

```
┌──────────────────────────────────────────────────────────────┐
│  1. EXTRACCIÓN  — workers Python, uno por conector           │
│     Meta/IG · TikTok · LinkedIn · YouTube · GA4 · GSC · Ads  │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  2. RAW / LANDING  — payload íntegro en JSONB, append-only   │
│     Nunca se borra. Es tu seguro contra bugs de modelado.    │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  3. MODELADO  — staging → marts (SQL / dbt-core)             │
│     Normalización de métricas entre redes. Capa semántica.   │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  4. ORQUESTACIÓN  — scheduler, reintentos, alertas, backfill │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  5. PRESENTACIÓN                                             │
│     · Metabase (interno, exploración del equipo)             │
│     · Frontend React white-label (cliente final)             │
│     · Export PDF / envío mensual automático                  │
└──────────────────────────────────────────────────────────────┘
```

### Stack recomendado (alineado a lo que ya manejas)

| Capa | Tecnología | Por qué |
|---|---|---|
| Extracción | Python 3.12 + `httpx` + `tenacity` | Ya es tu lenguaje; retry/backoff resuelto |
| Base | PostgreSQL (Supabase o Railway PG) | Ya lo usas; sobra para este volumen |
| Orquestación | Railway Cron → endpoint FastAPI, o **Prefect 3** self-hosted | Empieza con cron; migra a Prefect cuando duela |
| Modelado | `dbt-core` (opcional en fase 1) | Versiona tu lógica de negocio en Git |
| BI interno | **Metabase self-hosted** | Gratis, Docker, reemplaza el 80% de Looker |
| BI cliente | React + Vite + Recharts | White-label real, con tu marca y la del cliente |
| PDF | Playwright headless → PDF | Renderiza el mismo dashboard, sin librería aparte |

**No necesitas** BigQuery, Snowflake, ClickHouse ni Airflow. Ver cálculo de volumen abajo.

---

## 3. Las 6 decisiones de diseño que definen el proyecto

### 3.1 Snapshot diario append-only, no update-in-place
Cada corrida escribe una fila nueva con `fecha_snapshot`. Nunca haces `UPDATE` destructivo sobre el histórico.

Esto te permite responder algo que Supermetrics jamás podrá: *"¿cuántos seguidores tenía este cliente el 14 de marzo?"* y también *"¿cuánto cambió Meta la cifra de conversiones de marzo entre lo que reportó el día 1 y lo que reporta hoy?"*.

### 3.2 Ventana móvil de re-sincronización de 28 días
Meta Ads reatribuye. GA4 tiene datos incompletos las primeras 48h. TikTok ajusta.

Regla: **cada corrida diaria re-consulta los últimos 28 días**, no solo ayer. Upsert idempotente. Sin esto, tus números no van a cuadrar con la plataforma nativa y el cliente te lo va a reclamar en reunión.

### 3.3 Formato largo (métrica como fila), no ancho
Instagram tiene métricas que TikTok no tiene, LinkedIn tiene otras. Una tabla ancha te obliga a hacer `ALTER TABLE` cada vez que agregas una red o Meta lanza una métrica nueva.

Formato largo → agregar métricas es insertar filas, no migrar esquema.

### 3.4 Capa semántica: diccionario de métricas unificado
El activo estratégico real del proyecto. Cada red llama distinto a lo mismo:

| Concepto canónico | Meta/IG | TikTok | LinkedIn | YouTube |
|---|---|---|---|---|
| `alcance` | `reach` | `reach` | `uniqueImpressions` | — |
| `impresiones` | `impressions` | `video_views` | `impressionCount` | `views` |
| `interacciones` | `engagement` | `likes+comments+shares` | `engagement` | `likes+comments` |

Sin esto no puedes hacer un solo gráfico cross-network y tu reporte se ve igual de fragmentado que hoy.

### 3.5 Tokens: usa System User de Meta, no tokens de usuario
El token de usuario de Meta vive 60 días y se cae cuando el community manager cambia la clave o sale de la empresa. Un **System User token** de Business Manager **no expira**. Es la diferencia entre un sistema que funciona y uno que se rompe cada dos meses.

Credenciales cifradas en reposo (`pgcrypto` o Vault de Supabase), nunca en variables de entorno por cliente.

### 3.6 Corre en paralelo con Supermetrics 60 días antes de cancelar
No apagues el pago hasta haber cuadrado los números lado a lado dos meses. Es plata bien gastada como seguro.

---

## 4. Modelo de datos (DDL listo para ejecutar)

```sql
-- ============================================================
-- DIMENSIONES
-- ============================================================

CREATE TABLE clientes (
    id              BIGSERIAL PRIMARY KEY,
    nombre          TEXT NOT NULL,
    slug            TEXT UNIQUE NOT NULL,
    logo_url        TEXT,
    color_primario  TEXT DEFAULT '#000000',
    activo          BOOLEAN DEFAULT TRUE,
    creado_en       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE plataformas (
    codigo  TEXT PRIMARY KEY,        -- 'meta_ig','meta_fb','tiktok','linkedin','youtube','ga4','gsc','google_ads'
    nombre  TEXT NOT NULL
);

CREATE TABLE cuentas_conectadas (
    id                  BIGSERIAL PRIMARY KEY,
    cliente_id          BIGINT REFERENCES clientes(id) ON DELETE CASCADE,
    plataforma          TEXT REFERENCES plataformas(codigo),
    id_externo          TEXT NOT NULL,          -- ig_user_id, ad_account_id, property_id...
    nombre_cuenta       TEXT,
    credencial_cifrada  BYTEA,                  -- pgcrypto
    token_expira_en     TIMESTAMPTZ,            -- NULL = system user, no expira
    activo              BOOLEAN DEFAULT TRUE,
    UNIQUE (plataforma, id_externo)
);

-- Diccionario canónico: el corazón de la capa semántica
CREATE TABLE dim_metrica (
    codigo          TEXT PRIMARY KEY,           -- 'alcance','impresiones','interacciones','ctr','cpm'
    nombre_es       TEXT NOT NULL,
    unidad          TEXT,                       -- 'conteo','porcentaje','moneda','segundos'
    agregacion      TEXT NOT NULL,              -- 'suma','promedio','ultimo','maximo'
    es_acumulada    BOOLEAN DEFAULT FALSE,      -- seguidores = TRUE (lifetime), alcance = FALSE (day)
    categoria       TEXT                        -- 'audiencia','contenido','pauta','web'
);

CREATE TABLE map_metrica_plataforma (
    plataforma      TEXT REFERENCES plataformas(codigo),
    metrica_nativa  TEXT NOT NULL,              -- 'reach','impressionCount'...
    metrica_codigo  TEXT REFERENCES dim_metrica(codigo),
    factor          NUMERIC DEFAULT 1,          -- para normalizar unidades
    PRIMARY KEY (plataforma, metrica_nativa)
);

-- ============================================================
-- RAW — append-only, jamás se borra ni se modifica
-- ============================================================

CREATE TABLE raw_payloads (
    id              BIGSERIAL PRIMARY KEY,
    cuenta_id       BIGINT REFERENCES cuentas_conectadas(id),
    endpoint        TEXT NOT NULL,
    params          JSONB,
    payload         JSONB NOT NULL,
    capturado_en    TIMESTAMPTZ DEFAULT NOW(),
    job_id          BIGINT
);
CREATE INDEX idx_raw_cuenta_fecha ON raw_payloads (cuenta_id, capturado_en DESC);

-- ============================================================
-- HECHOS
-- ============================================================

-- Métricas a nivel cuenta/día (formato largo)
CREATE TABLE fct_metrica_diaria (
    cuenta_id       BIGINT NOT NULL REFERENCES cuentas_conectadas(id),
    fecha           DATE   NOT NULL,            -- fecha del dato
    metrica_codigo  TEXT   NOT NULL REFERENCES dim_metrica(codigo),
    valor           NUMERIC NOT NULL,
    fecha_snapshot  DATE   NOT NULL,            -- cuándo lo capturamos (para auditar reatribución)
    PRIMARY KEY (cuenta_id, fecha, metrica_codigo, fecha_snapshot)
);
CREATE INDEX idx_fct_cuenta_fecha ON fct_metrica_diaria (cuenta_id, fecha DESC);

-- Publicaciones: metadata + métricas
CREATE TABLE dim_publicacion (
    id              BIGSERIAL PRIMARY KEY,
    cuenta_id       BIGINT REFERENCES cuentas_conectadas(id),
    id_externo      TEXT NOT NULL,
    tipo            TEXT,                       -- 'reel','carrusel','imagen','video','story'
    publicado_en    TIMESTAMPTZ,
    permalink       TEXT,
    caption         TEXT,
    thumbnail_url   TEXT,
    visto_por_ultima_vez DATE,                  -- si desaparece, ya no existe pero conservamos histórico
    UNIQUE (cuenta_id, id_externo)
);

CREATE TABLE fct_publicacion_diaria (
    publicacion_id  BIGINT NOT NULL REFERENCES dim_publicacion(id),
    fecha_snapshot  DATE NOT NULL,
    metrica_codigo  TEXT NOT NULL REFERENCES dim_metrica(codigo),
    valor           NUMERIC NOT NULL,
    PRIMARY KEY (publicacion_id, fecha_snapshot, metrica_codigo)
);

-- ============================================================
-- OBSERVABILIDAD
-- ============================================================

CREATE TABLE jobs_ejecucion (
    id              BIGSERIAL PRIMARY KEY,
    cuenta_id       BIGINT REFERENCES cuentas_conectadas(id),
    conector        TEXT NOT NULL,
    estado          TEXT NOT NULL,              -- 'corriendo','ok','error','parcial'
    filas_escritas  INT DEFAULT 0,
    error_detalle   TEXT,
    iniciado_en     TIMESTAMPTZ DEFAULT NOW(),
    finalizado_en   TIMESTAMPTZ
);
```

### Vista de conveniencia: último snapshot por dato

```sql
CREATE VIEW v_metrica_actual AS
SELECT DISTINCT ON (cuenta_id, fecha, metrica_codigo)
       cuenta_id, fecha, metrica_codigo, valor, fecha_snapshot
FROM   fct_metrica_diaria
ORDER  BY cuenta_id, fecha, metrica_codigo, fecha_snapshot DESC;
```

---

## 5. Volumen: por qué Postgres sobra

Supuesto: **40 clientes × 5 plataformas × 45 métricas × 365 días**

```
40 × 5 × 45 × 365 ≈ 3.3 millones de filas / año  (cuenta/día)
+ publicaciones: 40 × 5 × 20 posts/mes × 12 × 15 métricas ≈ 1.4 M / año
────────────────────────────────────────────────────────────
≈ 4.7 M filas/año  ·  ~1.5 GB con índices
```

Postgres maneja esto sin despeinarse. El punto de dolor real aparece cerca de **300–500 millones de filas**. Estás a más de 60 años de distancia de necesitar ClickHouse.

Si algún día llega: `pg_partman` particionando `fct_metrica_diaria` por mes te da otros 10 años.

---

## 6. Diseño del extractor (patrón base)

```python
# core/conector.py
from abc import ABC, abstractmethod
from datetime import date, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

VENTANA_RESYNC = 28  # días

class ConectorBase(ABC):
    codigo: str

    def __init__(self, cuenta, db):
        self.cuenta = cuenta
        self.db = db

    @abstractmethod
    async def extraer(self, desde: date, hasta: date) -> list[dict]:
        """Devuelve el payload crudo de la API. Sin transformar."""

    @abstractmethod
    def normalizar(self, payload: list[dict]) -> list[tuple]:
        """(fecha, metrica_codigo, valor) usando map_metrica_plataforma."""

    @retry(stop=stop_after_attempt(5),
           wait=wait_exponential(multiplier=2, min=4, max=120))
    async def correr(self, hasta: date | None = None):
        hasta = hasta or date.today() - timedelta(days=1)
        desde = hasta - timedelta(days=VENTANA_RESYNC)

        job = await self.db.abrir_job(self.cuenta.id, self.codigo)
        try:
            crudo = await self.extraer(desde, hasta)
            await self.db.guardar_raw(self.cuenta.id, self.codigo, crudo, job)

            filas = self.normalizar(crudo)
            n = await self.db.upsert_metricas(self.cuenta.id, filas, date.today())

            await self.db.cerrar_job(job, "ok", n)
        except Exception as e:
            await self.db.cerrar_job(job, "error", 0, str(e))
            raise
```

**Regla de oro:** guardar el raw **antes** de normalizar. Si mañana descubres que mapeaste mal una métrica, reprocesas desde `raw_payloads` sin volver a llamar a la API.

### Upsert idempotente

```sql
INSERT INTO fct_metrica_diaria
       (cuenta_id, fecha, metrica_codigo, valor, fecha_snapshot)
VALUES %s
ON CONFLICT (cuenta_id, fecha, metrica_codigo, fecha_snapshot)
DO UPDATE SET valor = EXCLUDED.valor;
```

---

## 7. Orden de construcción de conectores

Priorizado por **valor / esfuerzo**, no por gusto:

| # | Conector | Esfuerzo | Nota |
|---|---|---|---|
| 1 | **Meta (IG + FB orgánico)** | Medio | Es el 60% del dolor. Requiere App Review: `instagram_basic`, `pages_read_engagement`, `instagram_manage_insights` |
| 2 | **Meta Ads** | Bajo | Misma app, mismo token. Casi gratis una vez hecho el #1 |
| 3 | **GA4 Data API** | Bajo | Service Account, sin App Review. El más fácil de todos |
| 4 | **Google Search Console** | Bajo | Mismo Service Account que GA4 |
| 5 | **Google Ads** | Medio | Requiere developer token (aprobación de Google, ~1 semana) |
| 6 | **YouTube Data + Analytics** | Medio | OAuth por canal |
| 7 | **LinkedIn Pages** | Alto | Aprobación lenta de LinkedIn. Es el que más se demora |
| 8 | **TikTok Business** | Alto | Docs pobres, cambios frecuentes |

> **Atajo táctico:** ya tienes Metricool conectado. Para LinkedIn y TikTok —los dos más caros de construir— la API de Metricool te sirve de puente mientras desarrollas el conector nativo. Ingiere desde Metricool a tu misma base con el mismo esquema; el día que tengas el conector propio, solo cambias la fuente. El cliente nunca se entera.

---

## 8. Hoja de ruta

### Fase 0 — Semana 1: **empezar a capturar YA**
Objetivo: que no se pierda ni un día más de data.

- Levantar Postgres (Supabase o Railway) y correr el DDL
- Conector Meta/IG funcional para **1 cliente piloto**
- Cron diario 06:00 ECT
- Sin dashboard. Sin UI. Solo capturar.

**Entregable:** tabla `fct_metrica_diaria` creciendo todos los días.

### Fase 0.5 — Paralelo: **rescate del histórico**
Mientras todavía pagas Supermetrics, exporta a CSV **todo** lo que puedas recuperar (Looker → export, Sheets, informes viejos, PDFs de reportes pasados). Cárgalo como semilla con `fecha_snapshot` = fecha del export.

No vas a recuperar todo, pero cada mes que rescates es un mes que no tendrás que esperar para hacer comparativos año contra año.

### Fase 1 — Semanas 2–4: cobertura
- Conectores 2 a 6 (Meta Ads, GA4, GSC, Google Ads, YouTube)
- Poblar `dim_metrica` y `map_metrica_plataforma` completos
- Todos los clientes cargados
- Metabase self-hosted arriba para que el equipo explore

**Entregable:** el equipo ya puede sacar cualquier número sin abrir Looker.

### Fase 2 — Semanas 5–7: modelado y calidad
- Marts en dbt-core: `mart_resumen_mensual`, `mart_top_publicaciones`, `mart_pauta_por_campana`
- Tests de calidad: no-nulos, rangos, detección de caídas anómalas (>50% día a día → alerta a Slack)
- **Cuadre lado a lado contra Supermetrics** (el hito que autoriza cancelar)

### Fase 3 — Semanas 8–11: producto de cara al cliente
- Frontend React white-label: logo y colores del cliente desde `clientes`
- Login por cliente (Supabase Auth), acceso solo a su data
- Export PDF vía Playwright
- Envío automático mensual por Resend

**Entregable:** el cliente entra a `reportes.geeksecuador.com` y ve **su** marca, no la de Google.

### Fase 4 — Semana 12: apagar Supermetrics
Cancelar tras 60 días de operación en paralelo cuadrada.

---

## 9. Economía

| Concepto | Hoy | Propuesto |
|---|---|---|
| Supermetrics | $300/mes | $0 |
| Base de datos (Supabase Pro) | $0 | $25/mes |
| Railway (workers + cron + Metabase) | $0 | ~$30/mes |
| Almacenamiento/egress | $0 | ~$5/mes |
| **Operación mensual** | **$300** | **~$60** |
| **Anual** | **$3,600** | **$720** |

**Ahorro: ~$2,880/año.** Inversión de desarrollo: ~10–12 semanas de un dev part-time. **Payback ≈ 14–18 meses** solo contando el ahorro.

Pero el ROI real no está ahí. Está en:

1. **Data que nadie más tiene** — comparativos históricos reales como argumento de renovación de fee
2. **Activo reutilizable** — el mismo motor alimenta el módulo de Anuncios y SEO del CRM que ya estás construyendo. No es un proyecto aparte: es la capa de datos del CRM
3. **Producto vendible** — reportería white-label como servicio para otras agencias (Stack-Studio)
4. **Diferenciador comercial** — "nuestros reportes no dependen de un proveedor externo"

---

## 10. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Meta rechaza el App Review | Alto | Empezar el review **la semana 1**. Video de demo claro, política de privacidad publicada, caso de uso descrito como "reportería para clientes de agencia" |
| Cliente revoca acceso a su Business Manager | Medio | Alerta automática en `jobs_ejecucion`; protocolo de re-conexión documentado para el ejecutivo de cuenta |
| Números no cuadran con la plataforma nativa | **Alto — riesgo de credibilidad** | Ventana de re-sync de 28 días + tabla de conciliación + nota metodológica en cada reporte |
| Cambio de API rompe un conector | Medio | Raw guardado + tests + alerta a Slack. Reprocesable sin volver a llamar la API |
| El dev se va y nadie entiende el sistema | Alto | dbt + README + un solo patrón `ConectorBase` para todos. Nada de código artesanal por conector |
| Se alarga y sigues pagando Supermetrics | Medio | Fase 0 en 1 semana. Si a la semana 3 no hay 3 conectores, se recorta alcance, no se extiende plazo |

---

## 11. Lo que haría yo esta semana, en orden

1. Crear proyecto Supabase y correr el DDL de la sección 4
2. Crear la App de Meta y **enviar el App Review hoy** (es lo que más se demora, y no depende de ti)
3. Crear Service Account de Google Cloud para GA4 + GSC
4. Escribir `ConectorBase` + el conector GA4 (el más fácil, para validar el patrón end-to-end en un día)
5. Elegir 1 cliente piloto y dejar el cron corriendo
6. Recién ahí pensar en cómo se va a ver el dashboard

**El dashboard es lo último. La captura es lo primero.**

---

## 12. Preguntas abiertas para cerrar el alcance

1. ¿Cuántos clientes activos y cuántas cuentas por cliente? (define si Fase 1 son 3 semanas o 6)
2. ¿Los clientes van a tener acceso self-service en vivo, o basta con el PDF mensual? (define si Fase 3 existe o se reemplaza por un job de PDF)
3. ¿Este motor vive **dentro** del CRM que estás construyendo o como servicio aparte con su propia base? (mi recomendación: base propia, expuesta al CRM vía API interna — así el CRM no se vuelve un monolito)
4. ¿Necesitas granularidad por campaña/adset/anuncio en pauta, o basta a nivel campaña? (impacta volumen ×20)
