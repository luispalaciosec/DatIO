"""kpi_fila: N scorecards con valor, delta vs período anterior y sparkline."""

from api.resolvedores import Contexto, Resultado, delta_porcentual, periodo_anterior, registrar


@registrar("kpi_fila")
async def resolver(ctx: Contexto) -> Resultado:
    items = ctx.config.get("items", [])
    codigos = [i["metrica"] for i in items]
    actual = await ctx.repo.agregar_metricas(ctx.cuentas, codigos, ctx.desde, ctx.hasta)
    info = await ctx.repo.metricas_info(codigos)

    # Cada item puede fijar su propio `comparar`; si no lo trae, hereda el del request.
    comparables = [
        i["metrica"] for i in items if i.get("comparar", ctx.comparar) == "periodo_anterior"
    ]
    anterior = {}
    if comparables:
        d0, d1 = periodo_anterior(ctx.desde, ctx.hasta)
        anterior = await ctx.repo.agregar_metricas(ctx.cuentas, comparables, d0, d1)

    serie = await ctx.repo.serie_metricas(ctx.cuentas, codigos, ctx.desde, ctx.hasta, "dia")
    sparklines: dict[str, list[float]] = {c: [] for c in codigos}
    for punto in serie:
        if punto["valor"] is not None:
            sparklines[punto["metrica_codigo"]].append(float(punto["valor"]))

    provisional = any(a.provisional for a in actual.values())
    datos = []
    for item in items:
        codigo = item["metrica"]
        act = actual.get(codigo)
        ant = anterior.get(codigo)
        datos.append(
            {
                "metrica": codigo,
                "etiqueta": item.get("etiqueta") or info.get(codigo, {}).get("nombre_es", codigo),
                "valor": float(act.valor) if act and act.valor is not None else None,
                "anterior": float(ant.valor) if ant and ant.valor is not None else None,
                "delta": delta_porcentual(act.valor if act else None, ant.valor if ant else None),
                "formato": item.get("formato", "entero"),
                "decimales": item.get("decimales", 0),
                "unidad": info.get(codigo, {}).get("unidad"),
                "sparkline": sparklines[codigo],
            }
        )
    return Resultado(datos, "provisional" if provisional else "consolidado")
