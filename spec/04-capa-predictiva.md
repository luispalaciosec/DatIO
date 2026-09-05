# Los tres estados del dato: histórico, tiempo real y proyectado
### Capa predictiva e inteligencia — Geeks Ecuador

---

## 1. El principio que no se negocia

> **El modelo estadístico produce el número. El LLM produce la explicación.**

Si un LLM genera la cifra proyectada, en algún momento va a inventar un número, un cliente lo va a contrastar y pierdes credibilidad de golpe. Esa es la única forma real de que este proyecto fracase.

El LLM es extraordinario en cosas que un modelo de series de tiempo no puede hacer: explicar *por qué* se movió una métrica, redactar el análisis, responder preguntas en lenguaje natural, recomendar acciones. Ahí es donde va, y ahí es donde vale oro.

---

## 2. Los tres estados, definidos con precisión

Cada dato que sale en pantalla lleva un estado explícito. Esto no es un detalle de UI: es una columna en la base y una regla de negocio.

| Estado | Qué es | Latencia | Confiabilidad | Tratamiento visual |
|---|---|---|---|---|
| `consolidado` | Snapshot ≥ 48h, ya reatribuido | 24–48h | Alta | Línea sólida |
| `provisional` | Hoy y ayer, consulta en vivo | 5–15 min | Media, va a cambiar | Línea sólida clara + badge "provisional" |
| `proyectado` | Salida de un modelo | — | Con banda de incertidumbre | Punteado + área sombreada |

```sql
CREATE TYPE estado_dato AS ENUM ('consolidado', 'provisional', 'proyectado');
```

**Regla dura:** nunca mezclar los tres en una misma serie sin marcar visualmente el corte. Es la causa #1 de que un cliente diga "estos números no cuadran".

---

## 3. Estado 2 — Tiempo real (bien entendido)

En redes sociales el "tiempo real" no existe. Meta consolida insights con 24–48h de retraso. Lo que sí puedes dar es **el dato de hoy, parcial y consultado en vivo**.

### Arquitectura: bypass del warehouse

```
Cliente abre dashboard
      │
      ├─► Rango histórico ──► Postgres (milisegundos)
      │
      └─► Hoy / ayer ──────► Redis cache (TTL 10 min)
                                  │  miss
                                  └─► API en vivo ──► marcar 'provisional'
```

```python
# api/tiempo_real.py
TTL_LIVE = 600  # 10 minutos

async def metricas_hoy(cuenta_id: int, redis, db) -> dict:
    key = f"live:{cuenta_id}:{date.today()}"
    if (hit := await redis.get(key)):
        return json.loads(hit)

    conector = obtener_conector(cuenta_id)
    datos = await conector.extraer(date.today(), date.today())
    payload = {
        "datos": conector.normalizar(datos),
        "estado": "provisional",
        "capturado_en": datetime.now(TZ_ECT).isoformat(),
        "nota": "Datos del día en curso. Se consolidan en 48 horas.",
    }
    await redis.setex(key, TTL_LIVE, json.dumps(payload))
    return payload
```

**Punto crítico de costo:** sin cache, 40 clientes abriendo dashboards revientan tus rate limits de Meta en una mañana. El TTL de 10 minutos es obligatorio, no opcional.

**Dónde sí importa el tiempo real:** campañas de pauta activas, lanzamientos, coberturas de evento en vivo. Para el reporte mensual no aporta nada — no lo pongas donde no suma.

---

## 4. Estado 3 — Proyección: cinco productos, no uno

"Proyecciones con IA" es demasiado vago para construir. Estos son los cinco entregables concretos, ordenados por **valor comercial / facilidad**:

### 4.1 Pacing del mes en curso ⭐ *empieza por aquí*
> *"Vas cerrando agosto en 1.24M de alcance. Proyección de cierre: **1.31M (±7%)**. El mes pasado cerraste en 1.18M."*

- **No requiere historia larga.** Funciona con 30–45 días de data
- Es lo que el cliente pregunta a mitad de mes
- Modelo: curva de acumulación intra-mes ponderada por día de semana

### 4.2 Detección de anomalías
> *"El alcance de Instagram cayó 58% el 14 de agosto, fuera del rango esperado."*

- Alerta interna al ejecutivo **antes** de que el cliente lo note. Vale muchísimo operativamente
- Requiere ~60 días de historia
- Modelo: descomposición STL + z-score sobre residuos

### 4.3 Forecast de crecimiento a 30/60/90 días
> *"A este ritmo llegas a 48.500 seguidores en diciembre (rango 46.100–51.200)."*

- Requiere 6–12 meses de historia por métrica
- Modelo: ETS / SARIMAX / Prophet, seleccionado por backtest

### 4.4 Proyección de meta inversa
> *"Para llegar a 50.000 seguidores en diciembre necesitas subir de 12 a 18 publicaciones mensuales, o sumar $800/mes de pauta."*

- Es el bloque que **vende ampliación de fee**. El más rentable de todos
- Requiere 4.3 funcionando + curva de respuesta a inversión

### 4.5 Proyección competitiva ⭐ *el diferenciador*
> *"Al ritmo actual, superas a Banco Internacional en seguidores en 14 meses. Si sostienes el ritmo de julio, en 9."*

- Nadie en el mercado ecuatoriano entrega esto
- Requiere el snapshot diario de competencia vía Apify

---

## 5. El problema del arranque en frío (y cómo resolverlo)

**Realidad dura:** el día 1 no tienes historia. Un modelo estacional necesita 2–3 ciclos completos, o sea 18–24 meses para capturar estacionalidad anual.

Tres salidas, en este orden:

### a) Empezar por lo que no necesita historia
Pacing intra-mes (4.1) funciona desde el día 30. Anomalías (4.2) desde el día 60. Esos dos ya dan valor visible mientras acumulas.

### b) Modelo jerárquico por sector ⭐
Este es el truco que te da tu escala de agencia: con 40 clientes tienes un **panel de datos**. Un cliente nuevo del sector banca hereda la estacionalidad promedio de los otros bancos de tu cartera, y a medida que acumula su propia historia, el modelo migra del promedio sectorial al suyo.

```python
def proyectar_con_prior(serie_cliente, sector, db):
    n = len(serie_cliente)
    if n < 90:
        # peso del prior sectorial decae con la historia propia
        peso_prior = max(0.0, 1 - n / 90)
        estacionalidad_sector = db.perfil_estacional(sector)
        return modelo_hibrido(serie_cliente, estacionalidad_sector, peso_prior)
    return modelo_propio(serie_cliente)
```

Ningún competidor tuyo puede hacer esto. Es un activo que solo existe porque tienes cartera.

### c) Rescatar historia
Lo que exportes de Supermetrics antes de cancelar (Fase 0.5 del plan base) acorta el arranque en frío meses.

---

## 6. Modelo de datos de proyecciones

La tabla clave no es la de proyecciones: es la de **evaluación**. Guardar cada proyección y después compararla contra el real es lo que separa un sistema serio de un juguete.

```sql
CREATE TABLE fct_proyeccion (
    id              BIGSERIAL PRIMARY KEY,
    cuenta_id       BIGINT REFERENCES cuentas_conectadas(id),
    metrica_codigo  TEXT REFERENCES dim_metrica(codigo),
    fecha_objetivo  DATE NOT NULL,          -- el día proyectado
    corrida_en      DATE NOT NULL,          -- cuándo se generó (para backtest honesto)
    horizonte_dias  INT  NOT NULL,
    valor_p50       NUMERIC NOT NULL,       -- mediana
    valor_p10       NUMERIC,                -- banda baja
    valor_p90       NUMERIC,                -- banda alta
    modelo          TEXT NOT NULL,          -- 'ets','sarimax','prophet','pacing','jerarquico'
    modelo_version  TEXT NOT NULL,
    features        JSONB,                  -- inversión, n_publicaciones, feriados
    PRIMARY KEY_ALT UNIQUE (cuenta_id, metrica_codigo, fecha_objetivo, corrida_en, modelo)
);

-- Evaluación: se llena cuando el real se consolida
CREATE TABLE fct_proyeccion_eval (
    proyeccion_id   BIGINT REFERENCES fct_proyeccion(id) ON DELETE CASCADE,
    valor_real      NUMERIC NOT NULL,
    error_abs       NUMERIC GENERATED ALWAYS AS (ABS(valor_real - valor_p50)) STORED,
    dentro_banda    BOOLEAN,
    evaluado_en     DATE DEFAULT CURRENT_DATE,
    PRIMARY KEY (proyeccion_id)
);

-- Precisión por modelo/métrica → alimenta la selección automática
CREATE VIEW v_precision_modelo AS
SELECT p.modelo, p.metrica_codigo, p.horizonte_dias,
       COUNT(*)                                              AS n,
       AVG(e.error_abs / NULLIF(e.valor_real,0)) * 100        AS mape,
       AVG(e.dentro_banda::int) * 100                         AS cobertura_banda
FROM   fct_proyeccion p
JOIN   fct_proyeccion_eval e ON e.proyeccion_id = p.id
GROUP  BY 1,2,3;
```

**Uso comercial de esto:** poder decirle al cliente *"nuestras proyecciones de alcance a 30 días tienen un error promedio de 8%"* es un argumento devastador. Nadie más lo puede afirmar con datos.

---

## 7. Motor de forecasting

### Selección automática de modelo por backtest

```python
# forecast/motor.py
from statsforecast import StatsForecast
from statsforecast.models import AutoETS, AutoARIMA, SeasonalNaive, WindowAverage

MODELOS = [
    AutoETS(season_length=7),
    AutoARIMA(season_length=7),
    SeasonalNaive(season_length=7),   # baseline honesto
    WindowAverage(window_size=28),
]

def entrenar_y_elegir(serie: pd.DataFrame, horizonte: int = 30):
    """
    Backtest rolling-origin. Gana el de menor MAPE.
    Si ninguno le gana al SeasonalNaive, se usa SeasonalNaive.
    """
    sf = StatsForecast(models=MODELOS, freq="D", n_jobs=-1)
    cv = sf.cross_validation(df=serie, h=horizonte, step_size=7, n_windows=6)

    errores = {
        m: mape(cv["y"], cv[m])
        for m in [type(x).__name__ for x in MODELOS]
    }
    ganador = min(errores, key=errores.get)

    # Regla anti-sobreingeniería
    if errores[ganador] > errores["SeasonalNaive"] * 0.95:
        ganador = "SeasonalNaive"

    return ganador, errores
```

> **Por qué `statsforecast` y no Prophet:** es ~50x más rápido, y con 40 clientes × 5 redes × 15 métricas son ~3.000 series a reentrenar por semana. Prophet no te da esa escala en un contenedor de Railway.

### Guardrails obligatorios

```python
REGLAS = {
    "historia_minima_dias":    90,     # menos que esto → solo pacing, no forecast
    "horizonte_maximo_dias":   90,     # más allá es adivinar
    "mape_maximo_publicable":  25,     # si el backtest da peor, no se muestra al cliente
    "ancho_banda_maximo":      0.60,   # si p90-p10 > 60% de p50, se oculta el número
}
```

Si una serie no pasa los guardrails, el bloque muestra: *"Historia insuficiente para proyectar esta métrica"*. Es infinitamente mejor que mostrar un número malo.

### Métricas que NO se deben proyectar
Ratios volátiles (CTR, engagement rate con denominador chico), métricas de posts individuales, cualquier cosa con menos de 90 días. Proyecta volúmenes y acumulados; los ratios se derivan de los volúmenes proyectados.

---

## 8. Dónde entra el LLM (y dónde no)

### ✅ Sí

**a) Narrativa del reporte** — el bloque `texto_rico` autogenerado:

```python
PROMPT_NARRATIVA = """
Eres analista senior de redes sociales de una agencia ecuatoriana.
Escribe el análisis del período para el cliente, en español de Ecuador.

DATOS DEL PERÍODO (ya calculados, no los recalcules):
{datos_json}

CONTEXTO:
- Publicaciones del período: {publicaciones}
- Inversión en pauta: {inversion}
- Anomalías detectadas: {anomalias}
- Proyección de cierre: {proyeccion}

REGLAS ESTRICTAS:
1. Usa ÚNICAMENTE cifras presentes en los datos entregados. Nunca calcules ni estimes.
2. Toda proyección va con su rango de incertidumbre.
3. Máximo 4 párrafos. Directo, sin relleno.
4. Si un movimiento no tiene explicación en los datos, dilo. No inventes causas.
5. Cierra con 2 recomendaciones accionables para el próximo mes.
"""
```

**b) Validador de cifras — el control que hace esto seguro:**

```python
def validar_narrativa(texto: str, datos: dict) -> list[str]:
    """Toda cifra del texto debe existir en los datos. Si no, se rechaza."""
    permitidos = {round(float(v), 2) for v in extraer_numeros(datos)}
    encontrados = re.findall(r'[\d]+(?:[.,]\d+)*', texto)

    huerfanos = [
        n for n in encontrados
        if round(normalizar(n), 2) not in permitidos and not es_fecha_o_porcentaje_derivado(n)
    ]
    return huerfanos  # si no está vacío → se regenera o se marca para revisión humana
```

Sin este validador, no publiques narrativa automática. Con él, puedes.

**c) Q&A en lenguaje natural sobre el warehouse** — el ejecutivo pregunta *"¿cómo le fue a Amazonas en reels vs. carruseles este trimestre?"* y obtiene la respuesta. Text-to-SQL restringido a la capa semántica (`dim_metrica`), no SQL libre: solo puede consultar métricas del catálogo, con `cliente_id` forzado por el sistema.

**d) Clasificación de contenido** — etiquetar cada publicación por tema, formato, tono y CTA. Esto habilita el insight que hoy nadie te da: *"los carruseles educativos generan 3.2x más interacciones que los promocionales en tu audiencia"*.

**e) Servidor MCP propio** — igual que planeaste para el CRM, para poder preguntarle a Claude directamente sobre la data de cualquier cliente durante una reunión.

### ❌ No

- Generar el número proyectado
- Calcular agregados (el LLM suma mal)
- Explicar una anomalía sin evidencia en los datos — que diga "no identificado"
- Decidir qué modelo usar (eso lo decide el backtest)

---

## 9. Bloques nuevos para la capa de presentación

Se suman al catálogo del documento anterior:

| `tipo` | Qué muestra |
|---|---|
| `serie_con_proyeccion` | Histórico sólido + proyección punteada + banda p10–p90 |
| `pacing_mes` | Acumulado del mes, cierre proyectado, comparación con mes anterior |
| `alerta_anomalia` | Tarjeta de desvío con severidad y fecha |
| `narrativa_ia` | Texto generado, editable por el ejecutivo antes de publicar |
| `proyeccion_meta` | Simulador: mueve inversión o frecuencia → recalcula la proyección |
| `carrera_competitiva` | Proyección de cruce con competidores |
| `precision_modelo` | Badge con MAPE histórico. Transparencia como argumento de venta |

**Regla de UI:** el bloque `narrativa_ia` nunca se publica sin aprobación humana en v1. El ejecutivo edita y aprueba. Pasado 3 meses, si la calidad es consistente, se evalúa auto-publicar.

---

## 10. Infraestructura adicional

| Componente | Tecnología | Costo |
|---|---|---|
| Cache tiempo real | Redis (Railway) | ~$10/mes |
| Worker de forecasting | Job semanal, `statsforecast` | ~$10/mes |
| LLM (narrativas) | Claude Haiku para clasificación, Sonnet para narrativa | ~$15–25/mes |

**Total con capa predictiva: ~$185–210/mes.** Frente a $300 de Supermetrics — que no te da nada de esto.

---

## 11. Roadmap ampliado

| Fase | Semanas | Entregable |
|---|---|---|
| **F5 — Tiempo real** | 13–14 | Redis + endpoint live + estados en UI (`consolidado` / `provisional`) |
| **F6 — Pacing y anomalías** | 15–17 | Pacing del mes + detección STL + alertas a Slack. **Ya se puede vender** |
| **F7 — Forecasting** | 18–21 | `statsforecast` + tablas de proyección/eval + backtest + bloques con banda |
| **F8 — LLM** | 22–25 | Narrativa + validador de cifras + clasificación de contenido + Q&A |
| **F9 — Avanzado** | 26+ | Proyección de meta inversa + carrera competitiva + modelo jerárquico por sector |

**Nota de secuencia:** F7 solo tiene sentido cuando tengas 6+ meses de captura. Si arrancas la Fase 0 este mes, el forecasting serio es realista para el primer trimestre de 2027. F5, F6 y F8 sí se pueden hacer antes — y ya son diferenciadores fuertes.

---

## 12. Qué NO va a funcionar (para que no lo prometas)

- **Predecir virales.** El contenido que explota es un evento de cola. Ningún modelo lo anticipa. Lo que sí puedes: detectarlo dentro de las primeras 3 horas y avisar para amplificar con pauta
- **Proyectar a 12 meses con precisión útil.** El horizonte honesto son 90 días
- **Explicar caídas por factores externos** que no están en tus datos (cambio de algoritmo, crisis de marca, feriado no cargado). Por eso hace falta una tabla de eventos/hitos que el ejecutivo alimenta manualmente — y que además mejora el modelo
- **Proyecciones confiables sin estacionalidad anual.** El primer año, las bandas van a ser anchas. Muéstralas anchas. La honestidad estadística es parte del producto

---

## 13. El argumento comercial completo

Con esto dejas de venderle al cliente un reporte y le vendes un sistema de decisión:

| Estado | Pregunta que responde |
|---|---|
| **Histórico** | ¿Qué pasó? ¿Cómo vengo contra el año pasado? |
| **Tiempo real** | ¿Qué está pasando ahora con la campaña activa? |
| **Proyectado** | ¿Dónde voy a cerrar? ¿Qué tengo que hacer para llegar a mi meta? |

Ese tercer estado es el que justifica un fee mayor, porque deja de ser reportería y pasa a ser consultoría con respaldo de datos.
