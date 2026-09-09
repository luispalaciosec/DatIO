"""Radar de pauta (PT-15b): qué anuncios corre la competencia ahora mismo.

radar_anuncios_activos  → grid de creatividades con días activos (config: limite, orden)
radar_longevidad        → los anuncios más antiguos aún activos (los que funcionan)
radar_share_of_voice    → cuántos anuncios corre cada competidor, antigüedad y formatos
"""

from typing import Any

from api.resolvedores import Contexto, Resultado, registrar


def _anuncio(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f["id"],
        "competidor": f["competidor"],
        "handle": f["handle"],
        "logo_url": f["logo_url"],
        "ad_archive_id": f["ad_archive_id"],
        "primera_vez_visto": f["primera_vez_visto"].isoformat(),
        "ultima_vez_visto": f["ultima_vez_visto"].isoformat(),
        "dias_activo": int(f["dias_activo"] or 0),
        "plataformas": list(f["plataformas"] or []),
        "creatividad_url": f["creatividad_url"],
        "copy_texto": f["copy_texto"],
        "formato": f["formato"],
        "cta": f["oferta"],
        "titulo": f["titulo"],
        "enlace": f["enlace"],
        "url_biblioteca": f["url_biblioteca"],
        "activo": bool(f["activo"]),
    }


async def _grid(ctx: Contexto, orden: str, limite_defecto: int) -> Resultado:
    limite = int(ctx.config.get("limite", limite_defecto))
    filas = await ctx.repo.anuncios_competencia(
        ctx.cliente_id,
        solo_activos=bool(ctx.config.get("solo_activos", True)),
        orden=str(ctx.config.get("orden", orden)),
        limite=limite,
    )
    resumen = await ctx.repo.resumen_pauta_competencia(ctx.cliente_id)
    datos = [_anuncio(f) for f in filas]
    return Resultado(
        datos,
        meta={
            "sin_competidores": len(resumen) == 0,
            "sin_datos": len(datos) == 0,
            "total_activos": sum(int(r["activos"] or 0) for r in resumen),
            "ultima_captura": max(
                (r["ultima_captura"].isoformat() for r in resumen if r["ultima_captura"]),
                default=None,
            ),
            "competidores": [{"id": r["competidor_id"], "nombre": r["nombre"]} for r in resumen],
        },
    )


@registrar("radar_anuncios_activos")
async def anuncios_activos(ctx: Contexto) -> Resultado:
    return await _grid(ctx, "recientes", 24)


@registrar("radar_longevidad")
async def longevidad(ctx: Contexto) -> Resultado:
    return await _grid(ctx, "longevidad", 8)


@registrar("radar_share_of_voice")
async def share_of_voice(ctx: Contexto) -> Resultado:
    resumen = await ctx.repo.resumen_pauta_competencia(ctx.cliente_id)
    total = sum(int(r["activos"] or 0) for r in resumen)
    datos = [
        {
            "competidor_id": r["competidor_id"],
            "nombre": r["nombre"],
            "handle": r["handle"],
            "logo_url": r["logo_url"],
            "activos": int(r["activos"] or 0),
            "historicos": int(r["historicos"] or 0),
            "share": (int(r["activos"] or 0) / total * 100) if total else None,
            "dias_promedio": float(r["dias_promedio"]) if r["dias_promedio"] is not None else None,
            "dias_maximo": int(r["dias_maximo"]) if r["dias_maximo"] is not None else None,
            "veteranos": int(r["veteranos"] or 0),
            "formatos": {k: int(v) for k, v in (r["formatos"] or {}).items()},
            "plataformas": {k: int(v) for k, v in (r["plataformas"] or {}).items()},
            "ultima_captura": r["ultima_captura"].isoformat() if r["ultima_captura"] else None,
        }
        for r in resumen
    ]
    return Resultado(
        datos,
        meta={"sin_competidores": len(datos) == 0, "total_activos": total},
    )
