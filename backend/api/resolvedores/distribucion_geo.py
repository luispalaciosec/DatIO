"""distribucion_geo: barras por ciudad/país. Las dimensiones geográficas llegan con los
conectores de audiencia (Ola 2, demografía); hasta entonces devuelve vacío con aviso."""

from api.resolvedores import Contexto, Resultado, registrar


@registrar("distribucion_geo")
async def resolver(ctx: Contexto) -> Resultado:
    return Resultado(
        [],
        meta={
            "dimension": ctx.config.get("dimension", "ciudad"),
            "aviso": "Distribución geográfica disponible cuando el conector de audiencia capture "
            "dimensiones por ciudad/país.",
        },
    )
