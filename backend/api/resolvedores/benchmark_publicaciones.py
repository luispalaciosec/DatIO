"""benchmark_publicaciones: las publicaciones de la competencia con más interacciones,
tal como las capturó el radar (últimas 12 por competidor). Sirve para ver qué les funciona."""

from typing import Any

from api.resolvedores import Contexto, Resultado, registrar


@registrar("benchmark_publicaciones")
async def resolver(ctx: Contexto) -> Resultado:
    plataforma = ctx.config.get("plataforma")
    limite = int(ctx.config.get("limite", 8))
    dias = ctx.config.get("dias")  # None = todas las guardadas
    filas = await ctx.repo.publicaciones_competencia(
        ctx.cliente_id, plataforma, limite, int(dias) if dias else None
    )
    datos: list[dict[str, Any]] = []
    for f in filas:
        datos.append(
            {
                "id": f"{f['competidor_id']}:{f['id_externo']}",
                "competidor": f["nombre"],
                "handle": f["handle"],
                "logo_url": f["logo_url"],
                "tipo": f["tipo"],
                "publicado_en": f["publicado_en"].isoformat() if f["publicado_en"] else None,
                "permalink": f["permalink"],
                "caption": f["caption"],
                "thumbnail_url": f["thumbnail_url"],
                "metricas": {
                    "me_gusta": float(f["me_gusta"]) if f["me_gusta"] is not None else None,
                    "comentarios": (
                        float(f["comentarios"]) if f["comentarios"] is not None else None
                    ),
                    "reproducciones": (
                        float(f["reproducciones"]) if f["reproducciones"] is not None else None
                    ),
                    "interacciones": float(f["interacciones"]),
                },
            }
        )
    return Resultado(
        datos,
        meta={
            "metricas": [
                {"metrica": "interacciones", "etiqueta": "Interacciones"},
                {"metrica": "me_gusta", "etiqueta": "Me gusta"},
                {"metrica": "comentarios", "etiqueta": "Comentarios"},
                {"metrica": "reproducciones", "etiqueta": "Reproducciones"},
            ],
            "sin_datos": len(datos) == 0,
        },
    )
