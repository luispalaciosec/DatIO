"""Bloques basados en fct_metrica_dimension y en publicaciones.

distribucion        barras por una dimensión (ciudad, país, canal, dispositivo, formato…)
demografia          edad y género de la audiencia
tabla_ranking       tabla de varias métricas por dimensión (consultas, páginas, canales)
top_publicaciones   cuadrícula de mejores publicaciones con miniatura
rendimiento_formato promedio por publicación según tipo (reel, imagen, carrusel)
mejor_dia           interacción promedio por día de la semana de publicación
"""

from api.resolvedores import Contexto, Resultado, registrar

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
GENEROS = {"F": "Mujeres", "M": "Hombres", "U": "Sin especificar"}


@registrar("distribucion")
async def distribucion(ctx: Contexto) -> Resultado:
    codigo = ctx.config.get("metrica", "seguidores")
    dimension = ctx.config.get("dimension", "ciudad")
    modo = ctx.config.get("modo", "ultimo" if codigo == "seguidores" else "suma")
    limite = int(ctx.config.get("limite", 10))
    filas = await ctx.repo.agregar_dimension(
        ctx.cuentas, codigo, dimension, ctx.desde, ctx.hasta, limite, modo
    )
    info = await ctx.repo.metricas_info([codigo])
    total = sum(f["valor"] for f in filas) or 0
    for f in filas:
        f["porcentaje"] = round(f["valor"] / total * 100, 1) if total else None
    return Resultado(
        filas,
        meta={
            "metrica": codigo,
            "etiqueta": info.get(codigo, {}).get("nombre_es", codigo),
            "dimension": dimension,
            "modo": modo,
            "estilo": ctx.config.get("estilo", "barras"),
        },
    )


@registrar("demografia")
async def demografia(ctx: Contexto) -> Resultado:
    codigo = ctx.config.get("metrica", "seguidores")
    edades = await ctx.repo.agregar_dimension(
        ctx.cuentas, codigo, "edad", ctx.desde, ctx.hasta, 20, "ultimo"
    )
    generos = await ctx.repo.agregar_dimension(
        ctx.cuentas, codigo, "genero", ctx.desde, ctx.hasta, 5, "ultimo"
    )
    total_g = sum(g["valor"] for g in generos) or 0
    return Resultado(
        {
            "edades": sorted(edades, key=lambda e: e["etiqueta"]),
            "generos": [
                {
                    "etiqueta": GENEROS.get(g["etiqueta"], g["etiqueta"]),
                    "valor": g["valor"],
                    "porcentaje": round(g["valor"] / total_g * 100, 1) if total_g else None,
                }
                for g in generos
            ],
        },
        meta={"metrica": codigo},
    )


@registrar("tabla_ranking")
async def tabla_ranking(ctx: Contexto) -> Resultado:
    dimension = ctx.config.get("dimension", "consulta")
    columnas = list(ctx.config.get("columnas", ["clics_busqueda", "impresiones_busqueda"]))
    orden = ctx.config.get("orden", columnas[0])
    limite = int(ctx.config.get("limite", 10))
    modo = ctx.config.get("modo", "suma")
    filas = await ctx.repo.tabla_dimension(
        ctx.cuentas, columnas, dimension, ctx.desde, ctx.hasta, orden, limite, modo
    )
    info = await ctx.repo.metricas_info(columnas)
    return Resultado(
        filas,
        meta={
            "dimension": dimension,
            "etiqueta_dimension": ctx.config.get("etiqueta_dimension", dimension.capitalize()),
            "columnas": [
                {
                    "metrica": c,
                    "etiqueta": info.get(c, {}).get("nombre_es", c),
                    "unidad": info.get(c, {}).get("unidad"),
                }
                for c in columnas
            ],
        },
    )


@registrar("top_publicaciones")
async def top_publicaciones(ctx: Contexto) -> Resultado:
    orden = ctx.config.get("orden", "interacciones")
    limite = int(ctx.config.get("limite", 6))
    metricas = list(
        ctx.config.get("metricas", ["alcance", "me_gusta", "comentarios", "interacciones"])
    )
    filas = await ctx.repo.publicaciones_top(ctx.cuentas, ctx.desde, ctx.hasta, orden, limite)
    info = await ctx.repo.metricas_info(metricas)
    datos = [
        {
            "id": f["id"],
            "tipo": f["tipo"],
            "publicado_en": f["publicado_en"].isoformat() if f["publicado_en"] else None,
            "permalink": f["permalink"],
            "caption": f["caption"],
            "thumbnail_url": f["thumbnail_url"],
            "metricas": {m: float(f["metricas"][m]) for m in metricas if m in f["metricas"]},
        }
        for f in filas
    ]
    return Resultado(
        datos,
        meta={
            "orden": orden,
            "metricas": [
                {"metrica": m, "etiqueta": info.get(m, {}).get("nombre_es", m)} for m in metricas
            ],
        },
    )


@registrar("rendimiento_formato")
async def rendimiento_formato(ctx: Contexto) -> Resultado:
    metricas = list(ctx.config.get("metricas", ["alcance", "interacciones"]))
    filas = await ctx.repo.rendimiento_por_tipo(ctx.cuentas, ctx.desde, ctx.hasta, metricas)
    info = await ctx.repo.metricas_info(metricas)
    return Resultado(
        filas,
        meta={
            "metricas": [
                {"metrica": m, "etiqueta": info.get(m, {}).get("nombre_es", m)} for m in metricas
            ]
        },
    )


@registrar("mejor_dia")
async def mejor_dia(ctx: Contexto) -> Resultado:
    filas = await ctx.repo.interacciones_por_dia_semana(ctx.cuentas, ctx.desde, ctx.hasta)
    por_dia = {f["dia"]: f for f in filas}
    datos = [
        {
            "dia": DIAS[i - 1],
            "publicaciones": por_dia.get(i, {}).get("publicaciones", 0),
            "promedio": por_dia.get(i, {}).get("promedio"),
        }
        for i in range(1, 8)
    ]
    mejor = max(
        (d for d in datos if d["promedio"] is not None), key=lambda d: d["promedio"], default=None
    )
    return Resultado(
        datos, meta={"mejor": mejor["dia"] if mejor else None, "metrica": "interacciones"}
    )
