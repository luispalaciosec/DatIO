"""tabla_publicaciones: grid de posts con thumbnail, caption, métricas y link."""

from api.resolvedores import Contexto, Resultado, registrar


@registrar("tabla_publicaciones")
async def resolver(ctx: Contexto) -> Resultado:
    columnas = ctx.config.get("columnas", ["alcance", "impresiones", "interacciones"])
    orden = ctx.config.get("orden", columnas[0] if columnas else "interacciones")
    limite = int(ctx.config.get("limite", 20))
    filas = await ctx.repo.publicaciones(ctx.cuentas, ctx.desde, ctx.hasta, orden, limite)
    info = await ctx.repo.metricas_info(columnas)
    datos = [
        {
            "id": f["id"],
            "tipo": f["tipo"],
            "publicado_en": f["publicado_en"].isoformat() if f["publicado_en"] else None,
            "permalink": f["permalink"],
            "caption": f["caption"],
            "thumbnail_url": f["thumbnail_url"],
            "metricas": {c: float(f["metricas"][c]) for c in columnas if c in f["metricas"]},
        }
        for f in filas
    ]
    return Resultado(
        datos,
        meta={
            "columnas": [
                {"metrica": c, "etiqueta": info.get(c, {}).get("nombre_es", c)} for c in columnas
            ],
            "orden": orden,
        },
    )
