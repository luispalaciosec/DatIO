# Plataforma de reportería propia — Especificación
### Geeks Ecuador / Stack-Studio · Reemplazo de Supermetrics + Looker Studio

---

## Qué es esto

La especificación completa para construir una plataforma propia de reportería de
redes sociales y pauta, que reemplaza Supermetrics + Looker Studio (~$300/mes) por
un sistema propio (~$128/mes) con capacidades que ninguna herramienta del mercado vende.

Está estructurada para una **sesión de construcción con agentes en paralelo**
(Claude Code + Cursor). Empieza por `spec/06-paquetes-de-trabajo.md`.

---

## El problema en una frase

Supermetrics es una tubería sin bodega: consulta las APIs en vivo y no guarda nada,
así que las ventanas de 7/14/28 días de las APIs de origen se vuelven un techo
permanente. **Ninguna herramienta puede devolver lo que no se almacenó.** La solución
es capturar diariamente y persistir.

## Lo único urgente

Cada día sin capturar es data que **nunca** se recupera. La Fase 0 (PT-01 a PT-04)
no incluye ningún dashboard: solo un cron escribiendo en una tabla. Todo lo demás
puede esperar; esto no.

---

## Índice

| Archivo | Contenido |
|---|---|
| `sql/001_schema_inicial.sql` | **Esquema canónico. Fuente única de verdad.** |
| `spec/01-arquitectura-datos.md` | Diagnóstico, arquitectura de 5 capas, conectores, volumen, roadmap base |
| `spec/03-capa-presentacion.md` | Plantillas, bloques, config declarativa, theming |
| `spec/04-capa-predictiva.md` | Los 3 estados del dato, forecasting, dónde entra el LLM |
| `spec/05-roadmap-producto.md` | Fichas de producto por pilar (crecimiento / automatización) |
| `spec/06-paquetes-de-trabajo.md` | **Descomposición para agentes. Empezar aquí.** |
| `spec/07-infraestructura-costos.md` | **Costeo verificado, escenario Excelencia y selección de modelos LLM** |

---

## Precedencia entre documentos

Los documentos de `spec/` se escribieron en orden cronológico y contienen DDL
ilustrativo. Cuando haya discrepancia:

1. `sql/001_schema_inicial.sql` manda sobre cualquier DDL en los `.md`
2. `spec/06-paquetes-de-trabajo.md` manda sobre los roadmaps de los otros documentos
3. `spec/07-infraestructura-costos.md` manda sobre cualquier cifra de costo
4. Esta errata manda sobre todo lo anterior

---

## ERRATA — leer antes de construir

Correcciones a los documentos originales. **Los agentes deben seguir esta errata,
no el texto original.**

### E-01 · Meta Ad Library no tiene API para anuncios comerciales
`spec/05` originalmente decía que la Ad Library "es pública, gratuita y tiene API".
La API oficial cubre anuncios políticos y de temas sociales a nivel global, más la
totalidad de anuncios en la Unión Europea. **Los anuncios comerciales de marcas
ecuatorianas requieren scraping** (actores de Apify). Sigue siendo viable y barato
(~$15/mes), pero es frágil y hay que validarlo con una corrida de prueba.

### E-02 · Benchmark de competencia: cadencia semanal, no diaria
`spec/03` proponía snapshot diario. Los seguidores de la competencia no se mueven
día a día de forma analíticamente relevante. **Semanal** da 52 puntos anuales,
suficiente para tendencia y proyección competitiva, y reduce el costo de Apify ~7x.

### E-03 · Costos corregidos — escenario EXCELENCIA
Las cifras de `spec/01` ($60/mes) y `spec/04` ($185–210/mes) están superadas.
El costeo verificado está en `spec/07`. **Escenario elegido: EXCELENCIA, ~$128/mes.**
Decisión explícita del cliente: no escatimar. El presupuesto extra va a
confiabilidad (backups gestionados, staging, monitoreo) y a capacidad de cara al
cliente — no a modelos de lenguaje más caros.

### E-04 · Bug en el DDL de `fct_proyeccion`
`spec/04` contenía `PRIMARY KEY_ALT UNIQUE (...)`, que no es SQL válido. Corregido
en el esquema canónico como `CONSTRAINT uq_proyeccion UNIQUE (...)` sobre una PK
serial.

### E-05 · Supabase y Redis SÍ van (escenario Excelencia)
Una versión intermedia de este plan proponía eliminarlos para ahorrar. **Se revirtió.**
Los agentes deben asumir: Supabase Pro con backups gestionados y PITR, Supabase Auth
para la autenticación de clientes, Redis gestionado para el cache de tiempo real
(no cache en proceso), y un ambiente de staging separado del de producción.

### E-06 · Selección de modelos LLM
`spec/04` asume modelos de Anthropic. **Superado por `spec/07` §3:** router
multi-proveedor con LiteLLM. Gemini 3.1 Flash-Lite para clasificación (es
multimodal, requisito que DeepSeek no cumple), DeepSeek V4 Flash para el agente de
WhatsApp (cacheo automático de prefijo), y narrativa a definir por benchmark ciego.
El modelo se resuelve por configuración, nunca hardcodeado. Clientes del sector
financiero usan host occidental por residencia de datos.

---

## Principios no negociables

Estos aparecen repetidos en varios documentos porque violarlos rompe el sistema:

1. **Guardar el raw antes de normalizar.** Permite reprocesar sin volver a llamar la API.
2. **Ventana de re-sync de 28 días.** Meta reatribuye; sin esto los números no cuadran.
3. **Append-only con `fecha_snapshot`.** Nunca `UPDATE` destructivo sobre el histórico.
4. **`cliente_id` se inyecta en el servidor**, jamás viene del request.
5. **El modelo estadístico produce el número; el LLM produce la explicación.**
6. **Toda cifra en texto generado por IA se valida contra los datos de entrada.**
8. **El modelo LLM se resuelve por configuración**, nunca hardcodeado en el código.
7. **Correr en paralelo con Supermetrics 60 días** antes de cancelar.

---

## Stack

Python 3.12 · FastAPI (async, asyncpg) · PostgreSQL 17 en Supabase (Auth + Storage) ·
React + Vite + TypeScript + Recharts · Railway (API y cron) · Vercel (frontend) · Playwright
(PDF) · Pillow · LiteLLM (router multi-proveedor) · Apify (radar de competencia) · Resend (correo).

---

## Arranque local

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env            # DATABASE_URL (pooler de Supabase, puerto 5432) y secretos
.venv/bin/uvicorn api.main:app --port 8000
.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q   # tests de base solo con DATABASE_URL

cd ../frontend
cp .env.example .env            # VITE_API_URL, VITE_SUPABASE_URL, VITE_SUPABASE_KEY
npm install && npx vite --port 5174
```

Estructura del monorepo:

| Carpeta | Contenido |
|---|---|
| `backend/api/etl/` | Núcleo ETL, runner, cron (`python -m api.etl.cli`), radar, mantenimiento y `conectores/` |
| `backend/api/consulta/`, `resolvedores/` | `POST /consulta`, `GET /reportes/{slug}`, cache en proceso y un resolvedor por tipo de bloque |
| `backend/api/admin/` | Módulo administrador: clientes, marca, cuentas, OAuth, competidores, CRM, datos, reporte |
| `backend/api/alertas/`, `prediccion/`, `puente/`, `narrativa/`, `reportes/` | Anomalías y correo diario, pacing y evaluación, puente CRM, narrativa, invitaciones y envío mensual |
| `backend/api/pdf/`, `llm/`, `datos/` | Export PDF, router LLM (`llm_uso`), explorador de datos |
| `frontend/src/reporte/`, `bloques/`, `admin/` | Renderer white-label, biblioteca de bloques, administración |
| `sql/` | `001` esquema canónico (no se edita), migraciones `002`–`014` y `seeds/` (métricas y plantilla) |
| `spec/` | Especificación original |

Migraciones nuevas: `sql/0NN_<descripcion>.sql`, aplicadas en Supabase (panel SQL o MCP) y
documentadas en el commit. Los seeds son idempotentes y se pueden volver a correr.

### Despliegue

- **API**: Railway, servicio `DatIO` desde `backend/` (Dockerfile con Chromium para el PDF).
  https://datio-production.up.railway.app
- **Cron**: Railway, servicio `datio-cron`, mismo repo, `Cron Schedule = 0 11 * * *` (06:00
  Ecuador), `python -m api.etl.cli`. Ejecuta en orden: captura de todas las cuentas (re-sync
  28 días), radar semanal, alertas y correo al equipo, puente CRM, evaluación de proyecciones,
  envío mensual del PDF (días 1 a 5) y mantenimiento los domingos. **Toda variable nueva en
  `DatIO` debe replicarse en `datio-cron`** (referencia `${{DatIO.NOMBRE}}`) o moverse a
  Shared Variables; ya causó dos incidentes.
- **Frontend**: Vercel, proyecto `dat-io`, root `frontend/`. https://dat-io.vercel.app
  (`vercel.json` lleva las cabeceras de seguridad y la CSP, que nombra el dominio de la API).

### Variables de entorno (backend)

| Grupo | Variables |
|---|---|
| Base y auth | `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_JWT_SECRET`, `CLAVE_CIFRADO`, `AMBIENTE`, `ORIGENES_PERMITIDOS`, `FRONTEND_URL`, `API_URL`, `PDF_SECRET`, `CRON_SECRET`, `LIMITE_PETICIONES_MIN` |
| Meta | `META_APP_ID`, `META_APP_SECRET`, `META_SYSTEM_USER_ID`, `META_SYSTEM_USER_TOKEN`, `META_LOGIN_CONFIG_ID`, `META_BUSINESS_ID` |
| Google | `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` / `GOOGLE_CLIENT_SECRET`, `GOOGLE_PLAY_BUCKET` |
| LinkedIn | `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, `LINKEDIN_API_VERSION` (AAAAMM, caduca al año), `LINKEDIN_SCOPES` (opcional) |
| Radar | `APIFY_TOKEN`, `RADAR_DIAS_MINIMOS` |
| Correo | `RESEND_API_KEY`, `CORREO_REMITENTE`, `ALERTAS_DESTINATARIOS_EXTRA` |
| CRM PrometIO | `PROMETIO_URL`, `PROMETIO_FRONTEND_URL`, `PROMETIO_SUPABASE_URL`, `PROMETIO_SUPABASE_ANON_KEY`, `PROMETIO_EMAIL`, `PROMETIO_PASSWORD` |
| LLM | `LLM_MODELOS` (JSON por tarea), `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `TOGETHER_AI_API_KEY` |

Las credenciales por cuenta (tokens de Meta, refresh tokens de Google, claves de App Store,
Zoho, HubSpot) nunca van en variables: se cifran con `pgcrypto` en `cuentas_conectadas`.

---

## Estado de construcción

Todo lo listado está en producción con datos reales (clientes piloto: Banco Amazonas, Geeks
Ecuador, Grupo Jerilex, Jerivet). 141 tests.

### Paquetes del spec

| PT | Estado |
|---|---|
| PT-01 Base, PT-02 Semántica, PT-03 Núcleo ETL, PT-07 API y auth | listo |
| PT-04 GA4 + Search Console (con dimensiones), PT-05 Meta IG + FB (+ publicaciones), PT-06 Meta Ads | listo, capturando |
| PT-04d LinkedIn | **nativo** (Community Management API) para cuentas con token; puente Metricool para el resto |
| PT-04e TikTok | puente Metricool (`POST /etl/importar/metricool`); app nativa pendiente de crear |
| PT-04b Google Ads, PT-04c YouTube | mapeados; bloqueados por developer token y acceso al canal |
| PT-08 Resolvedores, PT-09 Renderer, PT-10 Bloques, PT-11 PDF | listo (26 tipos de bloque) |
| PT-12 Cache + live | listo (cache en proceso invalidada por la última captura; `--live` intradía provisional) |
| PT-13 Pacing | listo (`pacing_mes`, proyecciones guardadas y evaluadas al cerrar el mes) |
| PT-14 Alertas | listo: anomalías (STL simplificada + z-score), operativas (capturas, tokens, sin publicar, datos atrasados, radar detenido), correo diario por Resend |
| PT-15 Radar | listo: Instagram, Facebook y TikTok vía Apify (semanal), benchmark completo, radar de pauta (Meta Ad Library) |
| PT-16 Puente CRM | listo: PrometIO y HubSpot, 4 disparadores con ventana de 30 días |
| PT-17 Genoma, PT-18 WhatsApp | descartados por decisión del cliente |
| PT-19 Health score | pendiente (ya se registran visitas al reporte) |
| PT-20 Forecasting | pendiente por datos: desde ~febrero 2027 con estacionalidad semanal |

### Fuera del spec, construido

- **Administración** (`/admin`, rol equipo): clientes con puesta en marcha, marca, cuentas
  (botones Conectar con Meta / Business Manager / Google / LinkedIn y alta manual),
  competidores, usuarios e invitaciones, editor del reporte por cliente (ocultar páginas y
  bloques, textos, objetivos), alertas, puente CRM, explorador de datos con descarga CSV y
  catálogo de conectores, capturas.
- **Conectores adicionales**: App Store Connect, Google Play Console, Google Business Profile,
  CRM PrometIO / HubSpot / Zoho como fuente de datos.
- **Narrativa** por página: redacción por reglas a partir de hechos calculados; si hay LLM,
  reescritura aceptada solo cuando toda cifra existe en los hechos.
- **Envío mensual** del PDF con resumen narrado a los usuarios del cliente (días 1 a 5).
- **Seguridad**: esquema `public` cerrado a los roles de PostgREST (sql/011), RLS en todas las
  tablas, cabeceras y CSP, límite de peticiones por IP. Ver `sql/011_endurecer_acceso.sql`.
- **Mantenimiento**: compactación semanal de snapshots sin cambio de valor y caducidad de
  conexiones OAuth pendientes.

### Notas de plataformas

- Meta v21: sin impresiones ni alcance a nivel página de Facebook; Instagram usa `views` y
  métricas de cuenta por día; `-1` significa "no disponible" y se omite.
- LinkedIn REST exige una versión mensual vigente (`LINKEDIN_API_VERSION`) y URN codificados en
  rutas y `List(...)`.
- Google Business Profile y Google Play necesitan aprobación/invitación previa en Google.
- Las miniaturas de Instagram no se enlazan: el radar copia una versión reducida a la base.
