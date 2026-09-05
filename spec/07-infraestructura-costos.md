# Infraestructura, costos y selección de modelos
### Documento de referencia — manda sobre cualquier cifra de costo en otros documentos

Precios verificados al 2 de septiembre de 2026. **Revalidar antes de comprometer
presupuesto**: las tarifas de LLM cambiaron varias veces solo en 2026.

---

## 1. Escenario elegido: EXCELENCIA (~$128/mes)

Decisión del cliente: no escatimar. El objetivo no es el ahorro sino que el salto
de calidad sea evidente para el cliente final. El ahorro contra Supermetrics
($300/mes) sigue siendo del 57%.

| Componente | Detalle | Mensual |
|---|---|---|
| **Supabase Pro** | Backups gestionados, PITR, Auth, instancia Small | $40 |
| **Railway Pro** | API + workers + Metabase + Redis + staging | $38 |
| **Apify** | Radar competitivo + Ad Library, plan Starter | $29 |
| **Vercel Pro** | Frontend, previews por PR, edge | $20 |
| **LLM** | Ver §3 — router multi-proveedor | $8 |
| **Sentry** | Monitoreo de errores, plan Team | $0–26 |
| **Resend** | Envío de reportes mensuales | $20 |
| **Dominio + Better Stack** | SSL, uptime, alertas | $5 |
| **Total** | | **$128** (rango $110–160) |

### Qué compra el dinero adicional (vs. el escenario austero de $61)

Nada de esto es lujo — cada línea elimina un modo de falla real:

| Lo que se agrega | Modo de falla que elimina |
|---|---|
| Supabase Pro | Perder data por un backup casero mal hecho. Con PITR recuperas a cualquier punto |
| Ambiente de staging | Romper el reporte de un cliente el día 1 del mes al desplegar |
| Sentry | Enterarte de un error por el reclamo del cliente en vez de por una alerta |
| Metabase always-on | Que el equipo no pueda responder una pregunta en medio de una reunión |
| Vercel Pro | Previews por PR: revisar un cambio de diseño antes de que lo vea el cliente |
| Redis gestionado | Techo de una sola réplica de API. Con Redis escalas horizontal |
| Apify holgado | Poder monitorear 10 competidores en vez de 6, y sumar Ad Library |

**Regla:** el dinero extra va a confiabilidad y a capacidad de cara al cliente.
No a un modelo de lenguaje más caro. Por qué, en la siguiente sección.

---

## 2. Por qué el LLM no era el problema

El LLM representaba $10–20 de un presupuesto de ~$100. Migrar de un proveedor a
otro ahorra unos $8 al mes. Es el renglón más pequeño del presupuesto.

Dicho eso, la pregunta sí vale la pena — pero por razones **técnicas**, no de
precio. Cada carga de trabajo tiene requisitos distintos y el modelo correcto
cambia según la tarea.

---

## 3. Selección de modelos por carga de trabajo

### Las tres cargas y sus requisitos reales

| Carga | Volumen/mes | Requisito dominante | Sensible al costo |
|---|---|---|---|
| **A. Clasificación** (Genoma + Radar) | ~4.500 ítems | **Multimodal** (thumbnail + caption) | Sí |
| **B. Narrativa** del reporte | ~200 llamadas | **Calidad en español de Ecuador** | No |
| **C. Agente WhatsApp** | ~500 conversaciones | **Cacheo de prefijo + tool use** | Medio |

### Precios verificados (USD por millón de tokens)

| Modelo | Input | Output | Cache hit | Nota |
|---|---|---|---|---|
| Gemini 3.1 Flash-Lite | $0.25 | $1.50 | — | Sucesor de 2.5 Flash-Lite |
| Gemini 3.7 Flash | $0.75 | $3.75 | $0.075 | **Sube a $1.50/$7.50 el 1 ene 2027** |
| DeepSeek V4 Flash | $0.14 | $0.28 | $0.0028 | Cacheo automático de prefijo |
| DeepSeek V4 Pro | $0.435 | $0.87 | $0.003625 | Tarifas pico/valle desde ago 2026 |

**Advertencia de calendario:** Gemini 2.5 Flash-Lite ($0.10/$0.40) se retira el 16 de
octubre de 2026. No construyas sobre él. Y las tarifas introductorias de Gemini 3.7
y 3.6 Flash rigen hasta el 31 de diciembre de 2026 y se duplican el 1 de enero de 2027.

---

### Carga A — Clasificación: **Gemini 3.1 Flash-Lite**

El Genoma clasifica el thumbnail más el caption. **Eso es multimodal, y ahí DeepSeek
queda fuera** — no por precio, sino por capacidad. La decisión se toma sola.

```
4.500 ítems × ~1.200 tokens input + 150 output
= 5,4M input + 0,68M output
Gemini 3.1 Flash-Lite:  $1,35 + $1,02 = $2,37/mes
Con Batch API (−50%):                    $1,20/mes
```

La clasificación no es urgente: corre de noche por Batch y se abarata a la mitad.

---

### Carga B — Narrativa: **decidir por calidad, no por precio**

Aquí está el dato que cierra la discusión:

```
200 narrativas × (5k input + 800 output) = 1M input, 0,16M output

DeepSeek V4 Pro:      $0,44 + $0,14 = $0,58/mes
Gemini 3.7 Flash:     $0,75 + $0,60 = $1,35/mes
Modelo premium:       ~$3,00 + $2,40 = $5,40/mes
```

**La diferencia entre el más barato y el mejor es menos de $5 al mes.** Este es
texto que va firmado con tu marca a un banco. Elegir por precio aquí es optimizar
la variable equivocada.

**Cómo decidir bien:** benchmark ciego con 30 casos reales tuyos. Criterios:

1. Naturalidad del español de Ecuador (registro profesional, sin españolismos)
2. **Obediencia a la restricción de no inventar cifras** — el criterio decisivo
3. Capacidad de decir "no identificado" cuando no hay explicación en los datos
4. Ausencia de relleno y de tono de marketing

El criterio 2 no se predice por benchmarks públicos. Se mide con tus datos.

---

### Carga C — Agente WhatsApp: **DeepSeek V4 Flash, por el cacheo**

Aquí sí hay un argumento técnico fuerte a favor de DeepSeek, y no es el precio de
lista. DeepSeek cachea automáticamente el prefijo del prompt y cobra los tokens
repetidos a la tarifa de cache-hit — $0.0028 por millón contra $0.14.

El agente de WhatsApp manda el mismo prefijo en cada llamada: prompt de sistema +
esquema de la capa semántica + reglas. Son ~6k tokens fijos que se repiten 500
veces al mes. Con cacheo automático, ese costo se vuelve prácticamente cero.

**Contraste importante:** el cacheo explícito de Gemini cobra $0.50/hora de
almacenamiento, o sea ~$365/mes si lo dejas activo. Para volumen bajo e
intermitente como el tuyo, **el cacheo de Gemini es una trampa de costo**. El de
DeepSeek es automático y sin cargo de almacenamiento.

---

## 4. Riesgo de residencia de datos — leer antes de decidir

DeepSeek y Qwen se sirven desde infraestructura china. Para clientes como un banco,
esto puede ser un problema **contractual o de percepción**, aunque los datos de
redes sociales no sean especialmente sensibles.

Tres consideraciones honestas:

1. **Revisa tus contratos.** Si alguno tiene cláusula de tratamiento de datos o
   restricción de subprocesadores, esto la activa.
2. **Mitigación disponible:** tanto DeepSeek como Qwen tienen pesos abiertos y se
   sirven desde proveedores occidentales (Together, Fireworks, OpenRouter). Pagas
   algo más y resuelves la residencia sin cambiar de modelo.
3. **Segmenta por cliente.** Clientes regulados → proveedor occidental. El resto →
   la ruta más económica. Con el router de la §5 esto es un campo en la base.

**Recomendación:** no uses la API directa de DeepSeek para clientes del sector
financiero sin consultarlo con ellos primero. Es una conversación de cinco minutos
que evita un problema de confianza.

---

## 5. La decisión arquitectónica real: router, no proveedor

No elijas un proveedor. Elige poder cambiarlo sin tocar código — igual que
planeaste para el CRM.

```python
# api/llm/router.py
MODELOS = {
    "clasificacion": {"proveedor": "google",   "modelo": "gemini-3.1-flash-lite", "batch": True},
    "narrativa":     {"proveedor": "google",   "modelo": "gemini-3.7-flash"},
    "agente":        {"proveedor": "deepseek", "modelo": "deepseek-v4-flash"},
    "narrativa_regulado": {"proveedor": "together", "modelo": "deepseek-v4-pro"},
}

async def completar(tarea: str, mensajes: list, cliente_id: int | None = None) -> str:
    cfg = resolver_config(tarea, cliente_id)   # override por cliente regulado
    respuesta = await litellm.acompletion(
        model=f"{cfg['proveedor']}/{cfg['modelo']}",
        messages=mensajes,
    )
    await registrar_uso(tarea, cfg, respuesta.usage, cliente_id)
    return respuesta.choices[0].message.content
```

Usar **LiteLLM** como capa de abstracción: una sola interfaz para Google, DeepSeek,
Together, OpenAI y Anthropic. Cambiar de modelo es cambiar una fila de config.

**Registrar el uso desde el día 1** en una tabla `llm_uso` (tarea, modelo, tokens,
costo, latencia). Sin eso no puedes comparar proveedores con datos propios, y
vuelves a decidir por listas de precios de terceros.

---

## 6. Recomendación final

| Carga | Modelo | Razón | Costo/mes |
|---|---|---|---|
| Clasificación | Gemini 3.1 Flash-Lite + Batch | Multimodal; DeepSeek no compite aquí | $1,20 |
| Narrativa | A definir por benchmark ciego | Calidad en español; el costo es irrelevante | $1–5 |
| Agente WhatsApp | DeepSeek V4 Flash | Cacheo automático de prefijo | $1–2 |
| Clientes regulados | Mismo modelo, host occidental | Residencia de datos | +$1 |
| **Total** | | | **~$8/mes** |

**Lo que no haría:** unificar todo en un solo proveedor para simplificar. Las tres
cargas tienen requisitos genuinamente distintos, el router hace que la complejidad
sea de configuración y no de código, y depender de un solo proveedor con precios
que se duplican en enero de 2027 es un riesgo evitable.

---

## 7. Tarea pendiente antes de construir

- [ ] Benchmark ciego de narrativa: 30 casos reales, 3 modelos, evaluación a ciegas
      por dos personas del equipo
- [ ] Prueba de costo real de Apify: 6 competidores × 7 días, medir consumo efectivo
- [ ] Revisar contratos de clientes financieros por cláusulas de subprocesadores
- [ ] Confirmar precios vigentes — este documento se desactualiza rápido
