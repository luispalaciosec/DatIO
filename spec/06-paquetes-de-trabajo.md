# Paquetes de trabajo — descomposición para construcción agéntica

Este es el documento operativo de la sesión de construcción. Cada paquete (PT) está
diseñado para que **un agente lo pueda ejecutar de forma autónoma** sin colisionar
con otro agente trabajando en paralelo.

---

## Reglas de la sesión agéntica

1. **Un agente = un paquete = una rama.** Nunca dos agentes en el mismo PT.
2. **Nadie edita `sql/001_schema_inicial.sql`.** Si un PT necesita un cambio de
   esquema, crea `sql/0NN_<descripcion>.sql` como migración nueva y lo documenta
   en su PR. El esquema base es inmutable durante la sesión.
3. **Los contratos entre paquetes son sagrados.** Están definidos abajo. Si un
   agente necesita cambiar un contrato, se detiene y pregunta — no improvisa.
4. **Cada PT termina con sus tests pasando.** Sin tests, el PT no está cerrado.
5. **Todo en español**: nombres de tablas, columnas, variables de dominio,
   comentarios y mensajes de commit. El código de framework queda en inglés.

---

## Mapa de dependencias

```
                      ┌─────────────┐
                      │ PT-01 Base  │  (esquema + config + CI)
                      └──────┬──────┘
             ┌───────────────┼───────────────┐
             ▼               ▼               ▼
      ┌────────────┐  ┌────────────┐  ┌────────────┐
      │ PT-02      │  │ PT-03      │  │ PT-07      │
      │ Semántica  │  │ Core ETL   │  │ API base   │
      └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
            │               │               │
            └───────┬───────┘               │
                    ▼                       │
        ┌───────────────────────┐           │
        │ PT-04..06 Conectores  │           │
        │ (paralelizables)      │           │
        └───────────┬───────────┘           │
                    │      ┌────────────────┘
                    ▼      ▼
              ┌──────────────────┐
              │ PT-08 Resolvedores│
              └────────┬─────────┘
                       ▼
        ┌──────────────────────────┐
        │ PT-09..11 Frontend       │
        └──────────┬───────────────┘
                   ▼
       ┌───────────────────────────────┐
       │ PT-12..20 Capacidades avanzadas│
       └───────────────────────────────┘
```

---

# OLA 1 — Fundación (bloqueante, secuencial)

## PT-01 · Base del proyecto
**Depende de:** nada · **Esfuerzo:** 1 día · **Paralelizable:** no

Monorepo con dos paquetes (`api/`, `web/`) o dos repos separados según preferencia.
Docker Compose local con Postgres + la API. Ejecutar `sql/001_schema_inicial.sql`.
Configuración por variables de entorno con Pydantic Settings. CI en GitHub Actions:
lint (ruff), tipos (mypy), tests (pytest).

**Criterio de aceptación:** `docker compose up` levanta Postgres con el esquema
aplicado y la API respondiendo en `/health`. CI verde.

**Archivos que posee:** `docker-compose.yml`, `pyproject.toml`, `.github/`, `api/config.py`

---

## PT-02 · Capa semántica
**Depende de:** PT-01 · **Esfuerzo:** 1–2 días · **Paralelizable:** sí (con PT-03, PT-07)

Poblar `dim_metrica` con ~45 métricas canónicas y `map_metrica_plataforma` con los
mapeos de las 9 plataformas. Es un trabajo de datos, no de código: la calidad de
todo lo demás depende de esto.

**Criterio de aceptación:** seed idempotente. Test que verifica que toda métrica
nativa referenciada por un conector existe en el mapeo.

**Referencia:** `spec/03-capa-presentacion.md` §Capa semántica, tabla de equivalencias.

**Archivos que posee:** `sql/seeds/metricas.sql`, `tests/test_semantica.py`

---

## PT-03 · Núcleo del ETL
**Depende de:** PT-01 · **Esfuerzo:** 2–3 días · **Paralelizable:** sí

`ConectorBase` abstracto, el repositorio de datos (`guardar_raw`, `upsert_metricas`,
`abrir_job`, `cerrar_job`), retry con backoff exponencial, y el runner que despacha
todos los conectores activos.

**Contrato que expone — no cambiar sin acuerdo:**
```python
class ConectorBase(ABC):
    codigo: str
    async def extraer(self, desde: date, hasta: date) -> list[dict]: ...
    def normalizar(self, payload: list[dict]) -> list[tuple[date, str, Decimal]]: ...
```

**Reglas obligatorias:** ventana de re-sync de 28 días; `guardar_raw` SIEMPRE antes
de `normalizar`; upsert idempotente.

**Criterio de aceptación:** un conector falso (`ConectorDemo`) corre de punta a punta
escribiendo en `fct_metrica_diaria`. Test de idempotencia: correr dos veces produce
el mismo estado.

**Archivos que posee:** `api/etl/`, `tests/test_etl_core.py`

---

## PT-07 · API base y autenticación
**Depende de:** PT-01 · **Esfuerzo:** 2 días · **Paralelizable:** sí

FastAPI con Google OAuth para el equipo interno y JWT por cliente para el acceso
externo. Middleware que **inyecta `cliente_id` en el servidor**, nunca desde el
request.

**Regla de seguridad crítica:** ninguna consulta puede recibir `cliente_id` como
parámetro del cliente. Se deriva del token. Test dedicado que intenta acceder a
data de otro cliente y debe fallar con 403.

**Archivos que posee:** `api/auth/`, `api/deps.py`, `tests/test_auth.py`

---

# OLA 2 — Conectores (altamente paralelizable)

Todos dependen de PT-02 y PT-03. **Un agente por conector, en paralelo.**
Cada uno posee únicamente su archivo en `api/etl/conectores/`.

| PT | Conector | Esfuerzo | Notas |
|---|---|---|---|
| **PT-04** | GA4 + Search Console | 2 d | **Empezar por aquí.** Service Account, sin App Review. Valida el patrón end-to-end |
| **PT-05** | Meta (IG + FB orgánico) | 4 d | Requiere App Review aprobado. Usar System User token |
| **PT-06** | Meta Ads | 1 d | Reutiliza el token de PT-05 |
| **PT-04b** | Google Ads | 2 d | Requiere developer token |
| **PT-04c** | YouTube | 2 d | OAuth por canal |
| **PT-04d** | LinkedIn | 3 d | Aprobación lenta. Puente vía Metricool mientras tanto |
| **PT-04e** | TikTok | 3 d | Docs pobres. Puente vía Metricool mientras tanto |

**Criterio de aceptación común:** el conector extrae 28 días reales de una cuenta de
prueba, guarda raw, normaliza contra `map_metrica_plataforma` y escribe en
`fct_metrica_diaria`. Test con payload fijado (fixture), sin llamar a la API real.

---

# OLA 3 — Presentación

## PT-08 · Resolvedores de bloques
**Depende de:** PT-02, PT-07 · **Esfuerzo:** 3 días

El endpoint único `POST /consulta` y el registro de resolvedores.

**Contrato que expone:**
```
POST /consulta
  { instancia_id, bloque_id, desde, hasta, comparar }
  → { datos: [...], estado: 'consolidado'|'provisional', meta: {...} }
```

Resolvedores de esta ola: `kpi_fila`, `serie_temporal`, `tabla_publicaciones`,
`distribucion_geo`.

**Criterio de aceptación:** ningún resolvedor escribe SQL a mano fuera del repositorio.
Agregar un bloque nuevo no debe requerir tocar el endpoint.

**Archivos que posee:** `api/consulta/`, `api/resolvedores/`

---

## PT-09 · Renderer y sistema de tema
**Depende de:** PT-08 · **Esfuerzo:** 3 días

React + Vite. `TemaProvider` con variables CSS desde `cliente_tema`. Grid de 12
columnas. Ruteo `/{slug_publico}/{plataforma}/{pagina}`. Estados de carga y error
por bloque, no por página.

**Criterio de aceptación:** cambiar `color_primario` en la base cambia todo el
reporte sin tocar código.

---

## PT-10 · Biblioteca de bloques
**Depende de:** PT-09 · **Esfuerzo:** 4 días · **Paralelizable por bloque**

Los 6 bloques base: `hero_banner`, `titulo_seccion`, `kpi_fila`, `serie_temporal`,
`tabla_publicaciones`, `separador`.

**Criterio de aceptación:** reproducir la página "Métricas · Facebook" de Banco
Amazonas con fidelidad visual al Looker actual. Ese es el hito de aceptación de
toda la Ola 3.

---

## PT-11 · Export PDF
**Depende de:** PT-10 · **Esfuerzo:** 2 días

Playwright headless sobre la misma vista web con `?modo=print`.

---

# OLA 4 — Tiempo real y automatización

| PT | Nombre | Depende de | Esfuerzo |
|---|---|---|---|
| **PT-12** | Cache en proceso + endpoint live (estado `provisional`) | PT-08 | 2 d |
| **PT-13** | Pacing del mes en curso | PT-08 | 3 d |
| **PT-14** | Detección de anomalías (STL + z-score) + alertas Slack | PT-13 | 3 d |
| **PT-15** | Radar competitivo (Apify, cadencia **semanal**) | PT-03 | 5 d |
| **PT-16** | Puente CRM (disparadores → oportunidades) | PT-14, CRM | 6 d |
| **PT-17** | Genoma de contenido (clasificación Haiku + uplift) | PT-10 | 8 d |
| **PT-18** | Copiloto WhatsApp (Jelou + MCP) | PT-08 | 7 d |
| **PT-19** | Health score de cartera | PT-16 | 5 d |
| **PT-20** | Motor de forecasting (statsforecast + backtest) | PT-13 | 8 d |

**PT-16 y PT-19 están bloqueados por el CRM.** No los arranques hasta que ese
proyecto exponga su API.

**PT-20 está bloqueado por los datos, no por el código.** Requiere 6+ meses de
captura. Escribir el código antes es desperdicio: los guardrails no se pueden
calibrar sin historia real.

---

# Contratos entre paquetes

Estos son los puntos de acoplamiento. Cambiarlos requiere acuerdo explícito.

| Contrato | Definido en | Consumido por |
|---|---|---|
| `ConectorBase` | PT-03 | Todos los conectores |
| Fila de `fct_metrica_diaria` | `sql/001` | ETL, resolvedores, forecasting |
| `POST /consulta` | PT-08 | Frontend, PDF, WhatsApp |
| Config JSON de bloque | `spec/03` §4 | PT-08, PT-10 |
| Variables CSS de tema | PT-09 | Todos los bloques |
| API del CRM | Proyecto CRM | PT-16, PT-19 |

---

# Definición de "terminado"

Un PT está cerrado cuando:

- [ ] Tests unitarios pasan y cubren el camino feliz + al menos un caso de error
- [ ] No rompe ningún contrato de la tabla de arriba
- [ ] Los nombres de dominio están en español
- [ ] No hay credenciales en el código ni en los commits
- [ ] Cualquier decisión que se desvíe de la spec está documentada en el PR
- [ ] Si tocó el esquema, agregó migración numerada y no editó `001`

---

# Orden de arranque sugerido para la primera sesión

**Hilo 1 (secuencial, bloqueante):** PT-01 → PT-03 → PT-04
**Hilo 2 (en paralelo desde el minuto uno):** PT-02
**Hilo 3 (en paralelo apenas PT-01 cierre):** PT-07

Con esos cuatro cerrados ya tienes captura real corriendo, que es el objetivo de la
Fase 0 y lo único verdaderamente urgente: cada día sin capturar es data que no se
recupera.

**Fuera de la sesión de código, arrancar hoy mismo:**
- Enviar el App Review de Meta (es lo que más demora y no depende de desarrollo)
- Crear el Service Account de Google Cloud
- Correr una prueba de costo real de Apify con 6 competidores durante 7 días
