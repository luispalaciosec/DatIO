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

Python 3.12 · FastAPI · PostgreSQL 15 · React + Vite · Railway · Playwright ·
statsforecast · LiteLLM (router multi-proveedor: Google, DeepSeek, Together)

---

## Arranque

La base vive en **Supabase** (errata E-05). El esquema `sql/001` y la migración `sql/002`
ya están aplicados en el proyecto `DatIO` junto con el seed de métricas.

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env        # completar DATABASE_URL (pooler de Supabase, puerto 5432) y secretos
.venv/bin/uvicorn api.main:app --reload
.venv/bin/pytest -q          # los tests de base corren solo si DATABASE_URL está definido
```

Estructura del monorepo:

| Carpeta | Contenido |
|---|---|
| `backend/` | API FastAPI, ETL, conectores y tests (Python) |
| `frontend/` | Renderer React + Vite white-label (PT-09/10) |
| `sql/` | Esquema canónico, migraciones y seeds (compartido) |
| `spec/` | Especificación |

Con Docker (opcional): `docker compose up -d` levanta Postgres local con esquema y seed aplicados.

Migraciones nuevas: `sql/0NN_<descripcion>.sql`, aplicadas con Supabase CLI o el panel SQL.
`sql/001` no se edita.

### Estado de construcción (Fase 0)

| PT | Estado | Dónde |
|---|---|---|
| PT-01 Base | listo | `backend/pyproject.toml`, `docker-compose.yml`, `.github/`, `backend/api/config.py`, `backend/api/main.py` |
| PT-02 Semántica | listo (46 métricas, 89 mapeos, 9 plataformas) | `sql/seeds/metricas.sql`, `backend/tests/test_semantica.py` |
| PT-03 Núcleo ETL | listo | `backend/api/etl/`, `backend/tests/test_etl_core.py` |
| PT-07 API y auth | listo (Supabase Auth, `usuarios` en `sql/002`) | `backend/api/auth/`, `backend/api/deps.py`, `backend/tests/test_auth.py` |
| PT-04 GA4 + GSC | listo, **capturando** para geeks.com.ec (piloto) | `backend/api/etl/conectores/ga4.py`, `gsc.py` |
| PT-05 Meta IG + FB | listo, **capturando** para Geeks Ecuador (piloto) | `backend/api/etl/conectores/meta_fb.py`, `meta_ig.py`, `meta_base.py` |
| PT-06 Meta Ads | listo, capturando (cuenta piloto sin pauta activa) | `backend/api/etl/conectores/meta_ads.py` |
| PT-08 Resolvedores | listo: `POST /consulta`, `GET /reportes/{slug}`, plantilla RRSS Full (`sql/seeds/plantilla_rrss.sql`) | `backend/api/consulta/`, `backend/api/resolvedores/` |
| PT-09 Renderer y tema | listo: React + Vite, `TemaProvider`, grid 12 col, ruteo por slug/red/página, estados por bloque | `frontend/src/reporte/`, `frontend/src/tema/` |
| PT-10 Bloques | listo: los 6 base + `distribucion_geo`; página Métricas de Banco Amazonas renderiza con datos reales | `frontend/src/bloques/` |
| PT-11 Export PDF | listo: `GET /reportes/{slug}/pdf?desde&hasta`, Playwright sobre `/{slug}/imprimir?modo=print` con token de render de 5 min; botón Descargar PDF | `backend/api/pdf/`, `frontend/src/reporte/Imprimir.tsx` |
| PT-04d/e LinkedIn + TikTok | puente Metricool: `POST /etl/importar/metricool` alimentado por una rutina de Claude con el MCP de Metricool | `backend/api/etl/conectores/metricool.py` |

Notas de los conectores Meta (v21): Meta retiró impresiones y alcance a nivel página de
Facebook; quedan a nivel publicación. En Instagram `impressions` fue reemplazada por `views`
y las métricas de cuenta solo salen como `total_value`, por lo que se consulta un día por
llamada. Los tokens de System User van cifrados en `cuentas_conectadas` con `appsecret_proof`.

Captura diaria: en Railway, un segundo servicio del mismo repo (root `backend/`) con
`Cron Schedule = 0 11 * * *` (06:00 Ecuador) y Start Command `python -m api.etl.cli`.
El endpoint `POST /etl/correr` con header `X-Cron-Secret` queda para disparos manuales.

Luego abrir `spec/06-paquetes-de-trabajo.md` y arrancar PT-01.

**En paralelo, fuera del código, hoy mismo:** enviar el App Review de Meta, crear el
Service Account de Google Cloud, y correr la prueba de costo real de Apify.
