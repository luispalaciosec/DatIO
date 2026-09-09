"""benchmark_serie: evolución de una métrica (seguidores por defecto) del cliente y de cada
competidor. El cliente aporta su serie diaria; los competidores, sus snapshots semanales.
La línea de cada competidor crece con cada corrida del radar."""

from typing import Any

from api.resolvedores import Contexto, Resultado, registrar


@registrar("benchmark_serie")
async def resolver(ctx: Contexto) -> Resultado:
    metrica = str(ctx.config.get("metrica", "seguidores"))
    plataforma = ctx.config.get("plataforma")
    tema = await ctx.repo.tema(ctx.cliente_id)
    etiqueta_propio = str(ctx.config.get("etiqueta_propio") or tema.get("nombre") or "Tu marca")
    info = await ctx.repo.metricas_info([metrica])

    por_fecha: dict[str, dict[str, Any]] = {}
    series: list[dict[str, Any]] = [{"clave": etiqueta_propio, "propio": True}]
    propia = await ctx.repo.serie_metricas(ctx.cuentas, [metrica], ctx.desde, ctx.hasta, "dia")
    for p in propia:
        if p["valor"] is not None:
            por_fecha.setdefault(p["periodo"].isoformat(), {})[etiqueta_propio] = float(p["valor"])

    filas = await ctx.repo.serie_competidores(ctx.cliente_id, plataforma, metrica)
    vistos: dict[int, str] = {}
    for f in filas:
        nombre = str(f["nombre"])
        if f["competidor_id"] not in vistos:
            vistos[int(f["competidor_id"])] = nombre
            series.append({"clave": nombre, "propio": False})
        por_fecha.setdefault(f["fecha_snapshot"].isoformat(), {})[nombre] = float(f["valor"])

    puntos = [{"fecha": fecha, **valores} for fecha, valores in sorted(por_fecha.items())]
    snapshots = len({f["fecha_snapshot"] for f in filas})
    return Resultado(
        {"puntos": puntos, "series": series},
        meta={
            "metrica": metrica,
            "etiqueta": info.get(metrica, {}).get("nombre_es", metrica),
            "snapshots": snapshots,
            "sin_competidores": len(vistos) == 0,
        },
    )
