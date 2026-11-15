"""GET /reportes/{slug}/pdf → PDF del reporte completo para el período."""

import logging
from datetime import date
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.config import Configuracion
from api.consulta.repositorio import RepositorioConsulta
from api.deps import UsuarioActual, obtener_config_app, obtener_pool, usuario_actual
from api.pdf import render

router = APIRouter(tags=["pdf"])
log = logging.getLogger(__name__)
MENSAJE_FALLO = "No se pudo generar el PDF, intenta de nuevo"


@router.get("/reportes/{slug_publico}/pdf")
async def pdf_reporte(
    slug_publico: str,
    desde: date,
    hasta: date,
    usuario: Annotated[UsuarioActual, Depends(usuario_actual)],
    config: Annotated[Configuracion, Depends(obtener_config_app)],
    pool: Annotated[asyncpg.Pool, Depends(obtener_pool)],
) -> Response:
    if hasta < desde:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El rango de fechas es inválido")
    if not config.pdf_secret or not config.frontend_url:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Export PDF no configurado")

    instancia = await RepositorioConsulta(pool).instancia_por_slug(slug_publico)
    if instancia is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reporte no encontrado")
    if not usuario.es_equipo and usuario.cliente_id != instancia.cliente_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin acceso a este reporte")

    token = render.emitir_token_render(config, instancia.cliente_id, instancia.id)
    url = render.url_impresion(config, slug_publico, desde.isoformat(), hasta.isoformat(), token)
    try:
        contenido = await render.generar_pdf(url)
        render.validar_pdf(contenido, 1)
    except render.PdfInvalidoError as e:
        log.warning("PDF de %s descartado: %s", slug_publico, e.motivo)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, MENSAJE_FALLO) from e
    except Exception as e:  # Playwright: navegador ausente, red, etc.
        # Al cliente, mensaje genérico; el detalle al log y sin el token de render.
        log.error(
            "PDF de %s falló: %s: %s",
            slug_publico,
            type(e).__name__,
            render.sin_token(str(e), token),
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, MENSAJE_FALLO) from e

    nombre = f"{slug_publico}_{desde.isoformat()}_{hasta.isoformat()}.pdf"
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
