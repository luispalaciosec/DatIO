# Fichas de producto: crecimiento y automatización
### Detalle de las iniciativas de la plataforma de reportería — Geeks Ecuador / Stack-Studio

---

## 0. Corrección importante antes de empezar

En el mensaje anterior te dije que la Meta Ad Library "es pública, gratuita y tiene API". **Eso fue impreciso y puede costarte una decisión mal tomada.**

La realidad: la API oficial de la Ad Library cubre anuncios sobre temas sociales, elecciones y política a nivel global, más la totalidad de anuncios en la Unión Europea bajo el DSA. **Los anuncios comerciales de marcas ecuatorianas no salen por la API oficial.** La interfaz web sí los muestra todos, pero acceder programáticamente requiere scraping — hay actores de Apify específicos para Ad Library.

Qué cambia: sigue siendo la iniciativa que más recomiendo, sigue siendo barata (~$10–15/mes de Apify adicional), pero **no es gratis y depende de scraping**, con la fragilidad que eso implica. Valídalo con una corrida de prueba antes de comprometerlo en un pitch.

---

## 1. Los pilares como regla de decisión, no como etiqueta

Para que "crecimiento" y "automatización" sirvan de verdad, tienen que poder rechazar ideas. Así los traduzco:

| Pilar | Pregunta que debe responder cada feature | Métrica que mueve |
|---|---|---|
| **Crecimiento** | ¿Esto hace crecer al cliente, o hace crecer a Geeks? | Fee promedio, retención, tasa de cierre |
| **Automatización** | ¿Cuántas horas-persona elimina al mes? | Horas liberadas por cliente atendido |

**La regla:** si una iniciativa no mueve ninguna de las dos, no entra al roadmap por más elegante que sea.

Y hay una tercera categoría que aparece sola cuando cruzas ambos pilares, y es donde está el negocio real: **features que automatizan la detección de una oportunidad de crecimiento.** El loop con el CRM es el ejemplo puro.

### Taxonomía de módulos (nombres para vender)

Si esto va a ser producto, necesita nombres. Propuesta:

| Módulo | Qué es | Pilar |
|---|---|---|
| **Bóveda** | El warehouse histórico | Base |
| **Radar** | Inteligencia competitiva (benchmark + Ad Library) | Crecimiento |
| **Genoma** | Análisis de qué contenido funciona y por qué | Crecimiento |
| **Horizonte** | Proyecciones y simulador | Crecimiento |
| **Pulso** | Alertas, anomalías, detección de virales | Automatización |
| **Copiloto** | Narrativa IA, WhatsApp, Q&A | Automatización |
| **Puente** | Integración con el CRM | Ambos |

---

# CRECIMIENTO

---

## Ficha 1 — RADAR: inteligencia de pauta de la competencia

### Qué hace
Para cada cliente, muestra qué anuncios está corriendo su competencia **ahora mismo**: creatividades, copies, desde cuándo llevan activos, en qué plataformas, cuántas variaciones.

El insight de negocio no es ver el anuncio. Es la **antigüedad**: un anuncio que lleva 90 días corriendo es un anuncio que le está funcionando a alguien. Esa es la señal más honesta de performance que existe, porque nadie sostiene pauta que no convierte.

### Cómo se construye
```
Job semanal
  → Apify Ad Library actor por cada página competidora
  → Guardar en dim_anuncio_competencia:
      (competidor_id, ad_archive_id, primera_vez_visto,
       ultima_vez_visto, plataformas[], creatividad_url, copy_texto)
  → Calcular dias_activo = ultima_vez_visto - primera_vez_visto
  → Clasificar con Haiku: formato, oferta, tono, tipo de CTA
```

Como capturas semanalmente y guardas primera/última aparición, construyes algo que ni la propia Ad Library te da: **el historial de duración de cada campaña de tu competencia**.

### Bloques de reporte que habilita
- `radar_anuncios_activos` — grid de creatividades con días activos
- `radar_longevidad` — ranking de los anuncios más longevos del sector (los que funcionan)
- `radar_share_of_voice` — cuántos anuncios corre cada competidor, evolución mensual

### Esfuerzo y costo
5–7 días de desarrollo. ~$15/mes de Apify.

### Cómo se vende
Es un servicio nuevo facturable, no un extra del reporte. *"Monitoreo de pauta competitiva"*, $150–250/mes por cliente. Con 10 clientes tomándolo, paga toda la infraestructura y sobra.

**Riesgo:** depende de scraping. Ten un plan B manual documentado por si se rompe una semana antes de una presentación.

---

## Ficha 2 — GENOMA: la fórmula de contenido de cada marca

### Qué hace
Descompone cada publicación en atributos y correlaciona con rendimiento, hasta llegar a la fórmula específica de esa marca. No "el video funciona mejor que la imagen" — eso lo sabe cualquiera. Sino: *"para Banco Amazonas, los carruseles educativos con rostro humano, publicados martes o jueves antes de las 10am, con CTA suave, generan 3.2x más interacciones que el promedio de la cuenta"*.

### Cómo se construye
```python
ATRIBUTOS = {
    "formato":        ["reel","carrusel","imagen","video","story"],
    "tema":           ["educativo","promocional","institucional","fecha_especial","testimonial"],
    "tono":           ["informativo","emocional","urgente","aspiracional","humoristico"],
    "tiene_rostro":   bool,
    "tiene_texto_imagen": bool,
    "tipo_cta":       ["ninguno","suave","directo","urgente"],
    "duracion_seg":   int,      # video
    "color_dominante": str,     # hex
    "largo_copy":     int,
}
```

Clasificación con Haiku sobre el thumbnail + caption. ~$0.0005 por publicación: clasificar un año entero de 40 clientes cuesta menos de $30 una sola vez.

Luego, análisis de uplift por atributo controlando por fecha y alcance base:

```sql
-- uplift de cada atributo vs. la mediana de la cuenta
SELECT atributo, valor,
       COUNT(*) AS n,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY interacciones) AS mediana,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY interacciones)
         / NULLIF(mediana_cuenta, 0) AS uplift
FROM   v_publicaciones_atributos
WHERE  cuenta_id = $1 AND n >= 8      -- mínimo de muestra, si no es ruido
GROUP  BY atributo, valor
ORDER  BY uplift DESC;
```

**Guardrail crítico:** mínimo 8 publicaciones por combinación de atributos. Por debajo de eso estás leyendo ruido y vas a dar una recomendación que hace perder plata al cliente.

### El giro comercial
Del Genoma sale automáticamente el **brief creativo del mes siguiente**. El reporte deja de describir el pasado y empieza a dictar la producción. Eso justifica que la reunión mensual pase de "revisión de resultados" a "planificación estratégica" — y las reuniones de planificación se cobran distinto.

### Esfuerzo
8–10 días. Requiere 6 meses de historia para tener muestra suficiente.

---

## Ficha 3 — HORIZONTE: el gemelo digital de la cuenta

### Qué hace
Un simulador que corres **en vivo, con el cliente al lado**, en la reunión de planificación anual. Mueves sliders y la proyección se recalcula.

```
Inversión mensual en pauta:     [$800] ──────●────── $3.500
Publicaciones orgánicas/mes:    [  12] ────●──────── 30
Mix reels vs. estáticos:        [ 40% ] ──●───────── 90%

──────────────────────────────────────────────────────
Proyección a diciembre 2027:
  Seguidores:     48.500  (rango 46.100 – 51.200)
  Alcance/mes:     1,82M  (rango 1,61M – 2,04M)
  Costo por interacción:  $0,043
──────────────────────────────────────────────────────
Escenario actual vs. escenario simulado:  +34% alcance
```

### Cómo se construye
Encima del motor de forecasting, con una curva de respuesta a inversión:

```python
def respuesta_a_inversion(inversion, alpha, beta, saturacion):
    """Curva de Hill: rendimientos decrecientes. Parámetros ajustados
       por cliente con regresión sobre el histórico de inversión vs. resultado."""
    return saturacion * (inversion**alpha) / (beta**alpha + inversion**alpha)
```

El parámetro de saturación es el que hace la magia: le muestra al cliente **dónde deja de rendir su plata**. Un cliente que ve que su curva se aplana en $2.000 entiende por qué necesita cambiar de estrategia y no solo subir presupuesto.

### Por qué es la más rentable
Es la herramienta de venta de ampliación de fee más potente que vas a tener. El cliente no te está pidiendo más presupuesto porque tú se lo pediste: lo está viendo él mismo en la pantalla.

**Honestidad obligatoria:** requiere 12+ meses de historia con variación real de inversión. Si el cliente siempre gastó lo mismo, no puedes ajustar la curva. Muéstralo con bandas anchas y di que se afina con el tiempo.

### Esfuerzo
10–12 días. Fase tardía (2027).

---

## Ficha 4 — Pitch con data: ganar la cuenta antes de la reunión

### Qué hace
Metes el nombre de un prospecto y en 20 minutos tienes: su perfil en las 5 redes, sus 6 competidores, benchmark sectorial contra tu cartera, qué pauta corre cada uno, y un diagnóstico de sus 3 debilidades más evidentes.

### Por qué gana pitches
Llegas a la primera reunión con un diagnóstico de su cuenta **que ellos no tienen de sí mismos**. Cambia por completo la dinámica: dejas de ser un proveedor presentando credenciales y pasas a ser un consultor que ya trabajó gratis.

Piensa en lo que esto hubiera significado en Navona.

### Cómo se construye
Reutiliza todo lo del Radar, pero sin cuentas conectadas: solo data pública. Un endpoint `/prospecto/analizar` + una plantilla de reporte especial `Pitch`. Genera un PDF de 8 páginas con tu marca.

### Esfuerzo
3–4 días **si ya existen Radar y la capa de plantillas**. Es la iniciativa con mejor relación esfuerzo/retorno de toda la lista.

---

## Ficha 5 — Índice Geeks de Redes Sociales Ecuador

### Qué hace
Estudio trimestral público con benchmarks sectoriales anonimizados: engagement promedio de banca, retail, salud, educación en Ecuador. Datos que **solo tú tienes** porque nadie más administra 40 marcas con historia longitudinal.

### Por qué importa
- Prensa y autoridad de categoría gratis
- Generación de leads inbound sostenida
- Los prospectos te buscan a ti para saber si están bien o mal
- Es un foso competitivo: nadie lo puede copiar sin conseguir 40 clientes primero

### Requisito legal y ético — no negociable
Necesitas **cláusula de uso agregado y anonimizado en tus contratos**, con opción de exclusión. Mínimo 5 marcas por sector antes de publicar un dato, y nunca cifras que permitan identificar a una marca por deducción. Esto conversalo con tu abogado antes de la primera publicación, no después.

### Esfuerzo
2 días de desarrollo (queries de agregación) + el trabajo editorial y de diseño, que es donde está el verdadero costo. Ahí tu agencia ya es buena.

---

# AUTOMATIZACIÓN

---

## Ficha 6 — PUENTE: el loop con el CRM ⭐ *la más importante de todas*

### Qué hace
El motor de reportería detecta una condición de negocio y **crea sola la oportunidad comercial en tu CRM**, con la propuesta ya calculada y el sustento en datos.

```
Disparadores → acción automática en el CRM

1. Cliente 40% bajo su meta proyectada
   → Oportunidad "Refuerzo de pauta" + monto sugerido por la curva de saturación
   → Asignada al ejecutivo de la cuenta, con el gráfico adjunto

2. Competidor sube 3+ anuncios nuevos en una semana
   → Tarea "Alerta competitiva" + brief de contraataque

3. Cliente con excelente rendimiento orgánico y cero pauta
   → Oportunidad de venta cruzada, con el argumento pre-armado

4. Cliente con 3 meses de caída sostenida
   → Alerta de riesgo de fuga al jefe comercial (ver Ficha 9)

5. Servicio recurrente próximo a renovar
   → Genera el reporte de valor entregado en los últimos 12 meses,
     automáticamente, 30 días antes de la renovación
```

### Por qué esta es la que paga todo
Convierte tu centro de costo (reportería) en tu **máquina de generación de pipeline**. Una sola oportunidad de refuerzo de pauta cerrada al mes paga la infraestructura del año completo.

Y es la razón técnica por la que la reportería y el CRM **deben compartir base de datos desde el diseño**, no integrarse después. Si los construyes separados, esto se vuelve un proyecto de integración caro en vez de un `INSERT`.

### Cómo se construye
```python
# puente/disparadores.py
@dataclass
class Disparador:
    codigo: str
    condicion: Callable[[dict], bool]
    plantilla_oportunidad: str
    valor_sugerido: Callable[[dict], Decimal]
    prioridad: str

async def evaluar_diario(db):
    for cuenta in await db.cuentas_activas():
        ctx = await construir_contexto(db, cuenta)   # métricas, proyección, pauta, competencia
        for d in DISPARADORES:
            if d.condicion(ctx) and not await db.disparo_reciente(cuenta, d.codigo, dias=30):
                await crm.crear_oportunidad(
                    empresa_id  = cuenta.cliente.crm_empresa_id,
                    titulo      = render(d.plantilla_oportunidad, ctx),
                    valor       = d.valor_sugerido(ctx),
                    evidencia   = ctx["resumen"],
                    grafico_url = await generar_grafico(ctx),
                )
```

**Guardrail:** el `disparo_reciente` con ventana de 30 días es obligatorio. Sin eso, un cliente con mal mes genera 30 oportunidades duplicadas y tu equipo comercial deja de confiar en el sistema en una semana.

### Esfuerzo
6–8 días, **si el CRM ya está en pie**. Depende de tu otro proyecto.

---

## Ficha 7 — COPILOTO WhatsApp: el analista de guardia

### Qué hace
El cliente le escribe a un número de WhatsApp con tu marca y pregunta en lenguaje natural:

> *— ¿Cómo vamos este mes?*
> — Vas cerrando noviembre en 1.24M de alcance, 6% arriba de octubre. Proyección de cierre: 1.31M (±7%). El reel del 12 explicó el 30% del alcance del mes. ¿Te mando el detalle?
>
> *— ¿Y comparado con Banco Internacional?*
> — Ellos crecieron 2.1% en seguidores este mes, tú 3.4%. Al ritmo actual los alcanzas en 14 meses.

### Por qué esto y no un dashboard
Ecuador es WhatsApp-first. Tu contraparte en el cliente **no abre dashboards** — abre WhatsApp. La reportería más elegante del mundo no sirve si se consulta dos veces al año.

### Cómo se construye
Jelou (que ya conoces) → webhook a tu API → agente con MCP sobre el warehouse → respuesta. Text-to-SQL restringido a la capa semántica, con `cliente_id` forzado por el sistema, nunca por el mensaje.

**Seguridad — crítico:** el número de WhatsApp determina el cliente, y el filtro de `cliente_id` se inyecta en el servidor. El LLM nunca debe poder consultar data de otro cliente ni aunque se lo pidan explícitamente. Esto se prueba con un caso de test dedicado antes de salir a producción.

### Esfuerzo
6–8 días. Requiere el MCP del warehouse listo.

---

## Ficha 8 — PULSO: alertas que llegan antes que el reclamo

### Qué hace
El ejecutivo se entera de los problemas antes que el cliente. Siempre.

```
Slack #alertas-clientes

🔴 Banco Amazonas · Instagram
   Alcance -58% vs. esperado (14 nov)
   Causa probable: sin publicaciones desde el 9 nov
   → Ver detalle | Crear tarea

🟢 Dermage · Instagram
   Post del 14 nov va 4.2x sobre el promedio en 3 horas
   Ventana de amplificación: próximas 6 horas
   → Amplificar con pauta ($50 sugeridos)

🟡 Revital · Facebook
   Token expira en 7 días
   → Renovar acceso
```

Tres familias de alerta: **anomalía negativa** (caída fuera de banda), **oportunidad** (viral temprano), **operativa** (token, cuenta desconectada, sin publicar).

### La de detección temprana de virales merece atención aparte
Es un servicio facturable. *"Amplificación reactiva"*: presupuesto pre-aprobado por el cliente que se activa cuando un post orgánico despega. Detectas en 3 horas, amplificas en 6, capturas la ola. Hoy eso se pierde porque nadie está mirando.

### Esfuerzo
4–5 días.

---

## Ficha 9 — Health score de cartera

### Qué hace
Predice qué cliente está en riesgo de no renovar, cruzando señales que hoy nadie mira junto:

| Señal | Fuente | Peso |
|---|---|---|
| Tendencia de resultados últimos 3 meses | Warehouse | Alto |
| Frecuencia de contacto del ejecutivo | CRM | Alto |
| Tiempo desde la última reunión presencial | CRM | Medio |
| Aperturas del reporte mensual | Plataforma | **Alto** |
| Tono de los últimos correos | Gmail + LLM | Medio |
| Retraso en pagos | Contífico | Alto |

**El indicador más subestimado: si dejaron de abrir el reporte, ya se fueron mentalmente.** Ese dato hoy no lo tienes con Looker; con plataforma propia sí, porque tú controlas la analítica de uso.

### Uso
Es interno, para el jefe comercial. **Nunca se muestra al cliente.** Dispara una tarea de retención en el CRM con 60–90 días de anticipación.

### Esfuerzo
5–6 días. Requiere el CRM operando.

---

## Ficha 10 — Wrapped de marca

### Qué hace
El 20 de diciembre, cada cliente recibe un video de 60 segundos con su año en redes: crecimiento, mejor publicación, momento más viral, evolución vs. competencia. Generado automáticamente con Higgsfield.

### Por qué funciona
No es un reporte, es un regalo. Es contenido que **el propio cliente comparte en LinkedIn**, con tu marca al final. Costo marginal por cliente: centavos. Retorno en percepción de valor y en visibilidad: desproporcionado.

Y es el momento perfecto del año: llega justo cuando se están evaluando los presupuestos del año siguiente.

### Esfuerzo
4–5 días, una sola vez. Se reutiliza cada año.

---

# 11. Matriz de decisión

| # | Iniciativa | Pilar | Esfuerzo | Costo/mes | Requiere | Impacto |
|---|---|---|---|---|---|---|
| 4 | Pitch con data | Crecimiento | 3–4 d | $0 | Radar | ⭐⭐⭐⭐⭐ |
| 6 | Puente CRM | Ambos | 6–8 d | $0 | CRM | ⭐⭐⭐⭐⭐ |
| 1 | Radar | Crecimiento | 5–7 d | $15 | — | ⭐⭐⭐⭐⭐ |
| 8 | Pulso | Automatización | 4–5 d | $0 | 60 días data | ⭐⭐⭐⭐ |
| 7 | Copiloto WhatsApp | Automatización | 6–8 d | $25 | MCP | ⭐⭐⭐⭐ |
| 2 | Genoma | Crecimiento | 8–10 d | $5 | 6 meses data | ⭐⭐⭐⭐ |
| 10 | Wrapped | Crecimiento | 4–5 d | $10 | 12 meses data | ⭐⭐⭐ |
| 9 | Health score | Automatización | 5–6 d | $0 | CRM | ⭐⭐⭐ |
| 5 | Índice Geeks | Crecimiento | 2 d + editorial | $0 | Cláusula legal | ⭐⭐⭐ |
| 3 | Horizonte | Crecimiento | 10–12 d | $0 | 12 meses data | ⭐⭐⭐⭐ |

---

# 12. Paquetización comercial

Aquí es donde los pilares se vuelven dinero. Las capacidades se empaquetan en niveles de fee:

| Nivel | Incluye | Pilar dominante |
|---|---|---|
| **Base** | Dashboard propio + reporte mensual PDF + histórico | — |
| **Crecimiento** | + Radar competitivo + Genoma + brief creativo mensual | Crecimiento |
| **Automatización** | + Copiloto WhatsApp + Pulso + amplificación reactiva | Automatización |
| **Estratégico** | + Horizonte (simulador) + sesión anual de planificación | Ambos |

Cada nivel es un upsell natural sobre el anterior, con el argumento ya construido dentro de la propia plataforma. Y el Puente CRM es lo que detecta automáticamente cuándo un cliente está listo para subir de nivel.

---

# 13. Secuencia sugerida

**Ola 1 — mientras se acumula data (meses 1–4)**
Radar → Pitch con data → Pulso operativo

Ninguna requiere historia larga. Radar y Pitch empiezan a generar ingreso casi de inmediato, lo que financia el resto.

**Ola 2 — cuando el CRM esté en pie (meses 5–8)**
Puente CRM → Copiloto WhatsApp → Health score

Es la ola de automatización pura. Aquí se libera tiempo del equipo y se abre el canal de upsell.

**Ola 3 — con 6–12 meses de historia (meses 9–15)**
Genoma → Wrapped → Índice Geeks → Horizonte

La ola de inteligencia. Es donde la plataforma deja de ser reportería y se vuelve el diferencial de la agencia.

---

# 14. Lo que no haría (todavía)

- **Multi-tenant para vender a otras agencias.** Es el negocio más grande, pero construir para un tercero antes de que funcione perfecto para ti multiplica la complejidad y frena todo lo demás. Constrúyelo mono-tenant con el código limpio, y separa cuando Geeks lleve 12 meses operando sin fricción.
- **App móvil nativa.** El Copiloto de WhatsApp cubre el 90% del caso de uso móvil, a una fracción del costo.
- **Automatizar la publicación de contenido.** Es otro producto. No lo mezcles con este.
- **Auto-publicar narrativas sin revisión humana.** Mínimo 3 meses con aprobación del ejecutivo antes de siquiera evaluarlo.
