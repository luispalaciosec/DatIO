"""serie_temporal: líneas multi-métrica por día/semana/mes con notas descriptivas."""

from api.resolvedores import Contexto, Resultado, registrar


@registrar("serie_temporal")
async def resolver(ctx: Contexto) -> Resultado:
    series = ctx.config.get("series", [])
    codigos = [s["metrica"] for s in series]
    granularidad = ctx.config.get("granularidad", "dia")
    filas = await ctx.repo.serie_metricas(ctx.cuentas, codigos, ctx.desde, ctx.hasta, granularidad)
    info = await ctx.repo.metricas_info(codigos)

    por_periodo: dict[str, dict[str, float | None]] = {}
    provisional = False
    for f in filas:
        clave = f["periodo"].isoformat()
        por_periodo.setdefault(clave, {})[f["metrica_codigo"]] = (
            float(f["valor"]) if f["valor"] is not None else None
        )
        provisional = provisional or bool(f["provisional"])

    puntos = [{"periodo": p, **valores} for p, valores in sorted(por_periodo.items())]
    leyenda = [
        {
            "metrica": s["metrica"],
            "etiqueta": s.get("etiqueta") or info.get(s["metrica"], {}).get("nombre_es"),
            "color": s.get("color"),
            "nota": s.get("nota"),
            "unidad": info.get(s["metrica"], {}).get("unidad"),
        }
        for s in series
    ]
    return Resultado(
        {"puntos": puntos, "series": leyenda},
        "provisional" if provisional else "consolidado",
        {"granularidad": granularidad, "mostrar_notas": ctx.config.get("mostrar_notas", True)},
    )
