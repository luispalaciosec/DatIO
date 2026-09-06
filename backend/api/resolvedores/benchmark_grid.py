"""benchmark_grid: el cliente frente a sus competidores (snapshots semanales del radar)."""

from api.resolvedores import Contexto, Resultado, delta_porcentual, registrar

METRICAS_POR_DEFECTO = ["seguidores", "publicaciones", "interacciones"]
ULTIMAS_PUBLICACIONES = 12


@registrar("benchmark_grid")
async def resolver(ctx: Contexto) -> Resultado:
    codigos = list(ctx.config.get("metricas", METRICAS_POR_DEFECTO))
    plataforma = ctx.config.get("plataforma")  # normalmente la de la página
    info = await ctx.repo.metricas_info(codigos)

    # El propio cliente: seguidores y publicaciones como último valor; interacciones sobre las
    # últimas N publicaciones para que sea comparable con lo que Apify devuelve del competidor.
    propio = await ctx.repo.agregar_metricas(ctx.cuentas, codigos, ctx.desde, ctx.hasta)
    valores_propio: dict[str, float | None] = {}
    for c in codigos:
        agregado = propio.get(c)
        valores_propio[c] = (
            float(agregado.valor) if agregado is not None and agregado.valor is not None else None
        )
    if "interacciones" in codigos:
        inter = await ctx.repo.interacciones_ultimas_publicaciones(
            ctx.cuentas, ULTIMAS_PUBLICACIONES
        )
        valores_propio["interacciones"] = float(inter) if inter is not None else None

    competidores = await ctx.repo.competidores_con_snapshots(ctx.cliente_id, plataforma, codigos)
    filas = [
        {
            "nombre": ctx.config.get("etiqueta_propio", "Tú"),
            "handle": None,
            "logo_url": None,
            "propio": True,
            "valores": valores_propio,
            "deltas": {},
            "fecha": ctx.hasta.isoformat(),
        }
    ]
    fechas = set()
    for k in competidores:
        actual = {c: (float(k["actual"][c]) if c in k["actual"] else None) for c in codigos}
        deltas = {c: delta_porcentual(k["actual"].get(c), k["anterior"].get(c)) for c in codigos}
        if k["fecha_actual"]:
            fechas.add(k["fecha_actual"].isoformat())
        filas.append(
            {
                "nombre": k["nombre"],
                "handle": k["handle"],
                "logo_url": k["logo_url"],
                "propio": False,
                "valores": actual,
                "deltas": deltas,
                "fecha": k["fecha_actual"].isoformat() if k["fecha_actual"] else None,
            }
        )
    return Resultado(
        filas,
        meta={
            "metricas": [
                {"metrica": c, "etiqueta": info.get(c, {}).get("nombre_es", c)} for c in codigos
            ],
            "ultimas_publicaciones": ULTIMAS_PUBLICACIONES,
            "snapshot": max(fechas) if fechas else None,
            "sin_competidores": len(competidores) == 0,
        },
    )
