# Capa de presentación: cómo modelar y customizar los dashboards
### Complemento del plan de reportería propia — Geeks Ecuador

---

## 1. La decisión más importante: NO construyas un Looker

Mirando tus dashboards actuales (Banco Amazonas), la estructura es siempre la misma:

```
Cliente
 └── Red social (Facebook, Instagram, LinkedIn, YouTube, TikTok)
      ├── Métricas          → banner + 5 KPIs + evolutivo + distribución geográfica
      ├── Publicaciones     → tabla/grid de posts ordenados
      ├── Benchmark Seguidores    → grid de competidores
      └── Benchmark Publicaciones → comparativo de contenido
```

Eso se repite para todos tus clientes. Lo único que cambia entre Banco Amazonas y otro cliente es: **logo, colores, banner, cuentas conectadas, lista de competidores y algunos textos**.

Entonces el error caro sería construir un editor drag & drop tipo Looker. Eso son 6 meses de trabajo para resolver un problema que no tienes.

**Lo que sí necesitas: un sistema de plantillas + slots.**

| Nivel | Qué es | Quién lo toca |
|---|---|---|
| **Plantilla** | La estructura del reporte (páginas, bloques, orden) | El equipo, una vez |
| **Instancia** | Plantilla + cliente + sus cuentas + su tema | Al dar de alta un cliente (10 min) |
| **Render** | La página que ve el cliente | Automático |

Con 3 o 4 plantillas cubres el 95% de tu cartera. Un cliente nuevo se configura en minutos, no en un día de armar un Looker desde cero.

---

## 2. Modelo de datos de la capa de reporte

```sql
-- ============================================================
-- PLANTILLAS
-- ============================================================

CREATE TABLE reporte_plantillas (
    id          BIGSERIAL PRIMARY KEY,
    nombre      TEXT NOT NULL,           -- 'RRSS Full', 'Solo Meta', 'Pauta + Orgánico'
    descripcion TEXT,
    version     INT DEFAULT 1,
    activa      BOOLEAN DEFAULT TRUE
);

CREATE TABLE reporte_paginas (
    id           BIGSERIAL PRIMARY KEY,
    plantilla_id BIGINT REFERENCES reporte_plantillas(id) ON DELETE CASCADE,
    plataforma   TEXT REFERENCES plataformas(codigo),   -- NULL = página cross-network
    slug         TEXT NOT NULL,          -- 'metricas','publicaciones','benchmark-seguidores'
    titulo       TEXT NOT NULL,
    orden        INT NOT NULL,
    icono        TEXT,
    UNIQUE (plantilla_id, plataforma, slug)
);

-- El corazón: cada bloque es un componente + su configuración declarativa
CREATE TABLE reporte_bloques (
    id         BIGSERIAL PRIMARY KEY,
    pagina_id  BIGINT REFERENCES reporte_paginas(id) ON DELETE CASCADE,
    tipo       TEXT NOT NULL,            -- ver catálogo sección 3
    orden      INT  NOT NULL,
    ancho      INT  DEFAULT 12,          -- grid de 12 columnas
    config     JSONB NOT NULL DEFAULT '{}'
);

-- ============================================================
-- INSTANCIA POR CLIENTE
-- ============================================================

CREATE TABLE reporte_instancias (
    id             BIGSERIAL PRIMARY KEY,
    cliente_id     BIGINT REFERENCES clientes(id) ON DELETE CASCADE,
    plantilla_id   BIGINT REFERENCES reporte_plantillas(id),
    nombre_publico TEXT,                 -- 'Banco Amazonas - RRSS'
    slug_publico   TEXT UNIQUE,          -- reportes.geeksecuador.com/banco-amazonas
    activa         BOOLEAN DEFAULT TRUE,
    creada_en      TIMESTAMPTZ DEFAULT NOW()
);

-- Overrides puntuales: cliente que quiere un bloque distinto sin clonar la plantilla
CREATE TABLE reporte_overrides (
    instancia_id BIGINT REFERENCES reporte_instancias(id) ON DELETE CASCADE,
    bloque_id    BIGINT REFERENCES reporte_bloques(id) ON DELETE CASCADE,
    oculto       BOOLEAN DEFAULT FALSE,
    config_merge JSONB DEFAULT '{}',     -- se hace merge sobre config base
    PRIMARY KEY (instancia_id, bloque_id)
);

-- ============================================================
-- THEMING
-- ============================================================

CREATE TABLE cliente_tema (
    cliente_id       BIGINT PRIMARY KEY REFERENCES clientes(id) ON DELETE CASCADE,
    logo_url         TEXT,
    banner_url       TEXT,               -- el header de "Soluciones Financieras"
    color_primario   TEXT DEFAULT '#C8102E',
    color_secundario TEXT DEFAULT '#1F1F1F',
    color_acento     TEXT DEFAULT '#F5F5F5',
    fuente_titulos   TEXT DEFAULT 'Inter',
    fuente_cuerpo    TEXT DEFAULT 'Inter',
    modo_oscuro      BOOLEAN DEFAULT FALSE
);

-- Competidores para los bloques de benchmark
CREATE TABLE cliente_competidores (
    id           BIGSERIAL PRIMARY KEY,
    cliente_id   BIGINT REFERENCES clientes(id) ON DELETE CASCADE,
    plataforma   TEXT REFERENCES plataformas(codigo),
    nombre       TEXT NOT NULL,          -- 'Banco Internacional'
    handle       TEXT NOT NULL,          -- 'bancointernacional'
    logo_url     TEXT,
    orden        INT DEFAULT 0
);
```

---

## 3. Catálogo de bloques

Cada bloque es **un componente React + un contrato de datos**. Esta lista cubre todo lo que hoy tienes en Looker:

| `tipo` | Qué renderiza | Equivalente en tu Looker actual |
|---|---|---|
| `hero_banner` | Imagen de cabecera + logo cliente + selector de fechas | El header de "Soluciones Financieras" |
| `titulo_seccion` | Título + bajada descriptiva | "KPIs claves del mes:" |
| `kpi_fila` | Fila de N scorecards con valor, delta vs. período anterior y sparkline | Los 5 cuadros vacíos |
| `serie_temporal` | Líneas/áreas multi-métrica con leyenda descriptiva | "Evolutivo de los KPIs más importantes" |
| `distribucion_geo` | Barras horizontales o mapa por ciudad/país | "Distribución de seguidores por ciudad" |
| `tabla_publicaciones` | Grid de posts con thumbnail, caption, métricas, link | Página "Publicaciones" |
| `benchmark_grid` | Grid de competidores: logo + métricas por competidor | "Benchmark - Seguidores" |
| `benchmark_tabla` | Tabla comparativa cliente vs. competencia | "Análisis de biografía y categoría" |
| `demografia` | Barras de edad/género | — (mejora sobre lo actual) |
| `texto_rico` | Markdown editable — **comentario del analista** | — (mejora fuerte, ver §6) |
| `separador` | Línea divisoria con color de marca | Las líneas rojas |

Empieza con `hero_banner`, `titulo_seccion`, `kpi_fila`, `serie_temporal`, `tabla_publicaciones` y `separador`. Con esos 6 ya reproduces la página "Métricas" completa.

---

## 4. La pieza clave: configuración declarativa de datos

Ningún bloque escribe SQL. Cada bloque **declara qué quiere** y un solo endpoint lo resuelve contra `fct_metrica_diaria`.

Ejemplo — la fila de 5 KPIs de la página Métricas de Facebook:

```json
{
  "tipo": "kpi_fila",
  "ancho": 12,
  "config": {
    "items": [
      { "metrica": "alcance",       "etiqueta": "Alcance",       "formato": "entero",     "comparar": "periodo_anterior" },
      { "metrica": "impresiones",   "etiqueta": "Impresiones",   "formato": "entero",     "comparar": "periodo_anterior" },
      { "metrica": "interacciones", "etiqueta": "Interacciones", "formato": "entero",     "comparar": "periodo_anterior" },
      { "metrica": "seguidores",    "etiqueta": "Seguidores",    "formato": "entero",     "agregacion": "ultimo" },
      { "metrica": "tasa_engagement","etiqueta": "Engagement",   "formato": "porcentaje", "decimales": 2 }
    ]
  }
}
```

Y el evolutivo:

```json
{
  "tipo": "serie_temporal",
  "ancho": 12,
  "config": {
    "granularidad": "dia",
    "series": [
      { "metrica": "alcance",       "color": "#4285F4", "nota": "Personas diferentes a las que se les mostró una publicación" },
      { "metrica": "impresiones",   "color": "#34A853", "nota": "Cantidad de veces que apareció en pantalla una publicación" },
      { "metrica": "interacciones", "color": "#FBBC04", "nota": "Interacciones totales: pasivas + activas" }
    ],
    "mostrar_notas": true
  }
}
```

Fíjate que las notas explicativas que hoy pones a mano en cada Looker quedan **dentro de la plantilla**. Se escriben una vez y salen igual en los 40 clientes.

### El resolvedor único

```python
# api/consulta.py
@router.post("/consulta")
async def resolver_bloque(req: ConsultaBloque, db=Depends(get_db)):
    """
    Un solo endpoint resuelve todos los bloques.
    req: { instancia_id, bloque_id, desde, hasta, comparar }
    """
    bloque    = await db.bloque_con_overrides(req.instancia_id, req.bloque_id)
    cuentas   = await db.cuentas_de_pagina(req.instancia_id, bloque.pagina_id)
    resolvedor = RESOLVEDORES[bloque.tipo]
    return await resolvedor(db, cuentas, bloque.config, req.desde, req.hasta, req.comparar)
```

```python
# resolvedores/kpi_fila.py
async def resolver(db, cuentas, config, desde, hasta, comparar):
    codigos = [i["metrica"] for i in config["items"]]
    actual  = await db.agregar_metricas(cuentas, codigos, desde, hasta)

    anterior = {}
    if comparar == "periodo_anterior":
        dias = (hasta - desde).days + 1
        anterior = await db.agregar_metricas(
            cuentas, codigos, desde - timedelta(days=dias), desde - timedelta(days=1)
        )

    return [{
        "etiqueta": i["etiqueta"],
        "valor":    actual.get(i["metrica"], 0),
        "delta":    calcular_delta(actual.get(i["metrica"]), anterior.get(i["metrica"])),
        "formato":  i.get("formato", "entero"),
    } for i in config["items"]]
```

**Ventaja:** agregar un bloque nuevo = escribir un componente React + un resolvedor de ~30 líneas. No tocas nada más del sistema.

---

## 5. Theming: tokens CSS desde la base

El renderer inyecta variables CSS y todos los componentes las consumen. Cero código por cliente.

```tsx
// components/TemaProvider.tsx
export function TemaProvider({ tema, children }: Props) {
  const vars = {
    "--color-primario":   tema.color_primario,
    "--color-secundario": tema.color_secundario,
    "--color-acento":     tema.color_acento,
    "--fuente-titulos":   tema.fuente_titulos,
    "--fuente-cuerpo":    tema.fuente_cuerpo,
  } as React.CSSProperties;

  return (
    <div style={vars} data-modo={tema.modo_oscuro ? "oscuro" : "claro"}>
      {children}
    </div>
  );
}
```

```tsx
// components/bloques/TituloSeccion.tsx
export function TituloSeccion({ titulo, bajada }: Props) {
  return (
    <div className="relative pl-6 mb-6">
      <div className="absolute left-0 top-0 h-full w-1"
           style={{ background: "var(--color-primario)" }} />
      <h2 className="text-3xl font-semibold"
          style={{ color: "var(--color-primario)",
                   fontFamily: "var(--fuente-titulos)" }}>
        {titulo}
      </h2>
      {bajada && <p className="text-sm text-neutral-600 mt-1">{bajada}</p>}
    </div>
  );
}
```

Para Banco Amazonas cargas `#C8102E` y su logo → sale idéntico a lo que tienes hoy. Para el siguiente cliente cambias dos campos en una tabla.

---

## 6. Las 4 cosas donde vas a superar a Looker (y hay que aprovecharlas)

### 6.1 Comentario del analista incrustado
Hoy el insight lo mandas por WhatsApp o en un PPT aparte. Con el bloque `texto_rico`, el ejecutivo escribe el análisis del mes **dentro del reporte**, y queda versionado por período. Eso solo ya justifica el proyecto ante el cliente.

Bonus: el borrador lo puede generar la IA con los datos del período y el ejecutivo lo edita.

### 6.2 Comparativos históricos reales
Looker + Supermetrics no puede darte "agosto 2026 vs. agosto 2025" en orgánico. Tú sí, porque tienes la bodega. Es el argumento de renovación de fee más fuerte que vas a tener.

### 6.3 Velocidad
Looker vuelve a consultar las APIs cada vez que alguien abre el reporte. Tú lees Postgres pre-agregado: **milisegundos**, no 40 segundos de spinner. El cliente lo nota inmediatamente.

### 6.4 PDF idéntico al dashboard
Un solo código fuente para la vista web y el PDF:

```python
# export/pdf.py
async def generar_pdf(instancia_slug: str, desde: str, hasta: str) -> bytes:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1400, "height": 2000})
        await page.goto(
            f"{BASE}/r/{instancia_slug}?desde={desde}&hasta={hasta}&modo=print",
            wait_until="networkidle"
        )
        pdf = await page.pdf(format="A4", print_background=True,
                             margin={"top": "12mm", "bottom": "12mm"})
        await browser.close()
        return pdf
```

Adiós al armado manual de PDFs a fin de mes.

---

## 7. Alerta: el benchmark de competencia es el bloque más difícil

Tus páginas "Benchmark - Seguidores" y "Benchmark - Publicaciones" **no salen de la API de Meta**. Meta ya no expone `fan_count` ni `talking_about_count` de páginas de terceros para apps externas. Supermetrics te lo entrega por otra vía.

Tienes tres caminos:

| Opción | Costo | Riesgo | Comentario |
|---|---|---|---|
| **Apify** (actors de scraping IG/FB/TikTok) | ~$0.01–0.05 por perfil/día | Bajo-medio | Ya tienes Apify conectado. Para 40 clientes × 6 competidores × 30 días ≈ **$70–100/mes**. La opción práctica |
| **Metricool API** (competitor tracking) | Incluido en tu plan | Bajo | Cobertura más limitada, pero cero desarrollo |
| **Scraper propio** | Solo dev | Alto | Se rompe seguido, hay que mantenerlo. No lo recomiendo al inicio |

**Recomendación:** Apify para el benchmark, ingiriendo al mismo esquema con un snapshot diario. Y ojo con esto: guardando ese snapshot vas a tener **la evolución histórica de la competencia**, que hoy ni Supermetrics te da. Es un bloque nuevo vendible: "así creció tu competencia vs. tú en los últimos 12 meses".

Presupuestando Apify, la operación mensual pasa de ~$60 a ~$150. Sigue siendo la mitad de lo que pagas hoy.

---

## 8. Cómo se da de alta un cliente nuevo (flujo objetivo)

1. Crear cliente → nombre, slug
2. Subir logo y banner, elegir 2 colores
3. Conectar cuentas (OAuth por red)
4. Elegir plantilla: *RRSS Full* / *Solo Meta* / *Pauta + Orgánico*
5. Cargar lista de competidores
6. Publicar → `reportes.geeksecuador.com/cliente`

**Meta: 15 minutos.** Hoy eso es una tarde entera duplicando y recableando un Looker.

---

## 9. Ajuste al roadmap (Fase 3 desglosada)

| Semana | Entregable |
|---|---|
| 8 | DDL de plantillas + endpoint `/consulta` + resolvedores de `kpi_fila` y `serie_temporal` |
| 9 | Renderer React + TemaProvider + 6 bloques base → **página Métricas de Facebook completa para Banco Amazonas** |
| 10 | `tabla_publicaciones` + `distribucion_geo` + `texto_rico`; replicar a Instagram, LinkedIn, YouTube, TikTok |
| 11 | Benchmark vía Apify + `benchmark_grid` + export PDF + auth por cliente |
| 12 | Migrar los 3 clientes más grandes y cuadrar contra Looker |

---

## 10. Regla de oro

> Todo lo que hoy configuras **por cliente** en Looker, en tu sistema debe ser **un campo en la base**.
> Todo lo que hoy repites **igual en todos los clientes**, debe ser **la plantilla**.

Si te encuentras escribiendo código específico para un cliente, algo se modeló mal.
