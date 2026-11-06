"""narrativa: párrafo que explica el período de la red en lenguaje humano. Las métricas a
narrar vienen en config.items (mismo formato que kpi_fila). Ver api/narrativa/."""

from api.narrativa.servicio import narrar
from api.resolvedores import Contexto, Resultado, registrar


@registrar("narrativa")
async def resolver(ctx: Contexto) -> Resultado:
    r = await narrar(
        ctx.repo,
        ctx.app,
        ctx.cliente_id,
        ctx.cuentas,
        str(ctx.config.get("plataforma") or ""),
        list(ctx.config.get("items", [])),
        ctx.desde,
        ctx.hasta,
        usar_ia=bool(ctx.config.get("ia", True)),
    )
    return Resultado(
        {"texto": r["texto"]}, meta={"fuente": r["fuente"], "sin_datos": not r["texto"]}
    )
