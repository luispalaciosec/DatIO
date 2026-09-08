"""Descarga y reducción de imágenes de la competencia (radar). Sin secretos nuevos: las imágenes
se guardan en Postgres (competidor_imagenes) y las sirve la API."""

import io
import logging

import httpx
from PIL import Image

log = logging.getLogger(__name__)

LADO_MAXIMO = 640
BYTES_MAXIMOS_ORIGEN = 8 * 1024 * 1024


def reducir(contenido: bytes, lado_maximo: int = LADO_MAXIMO) -> tuple[bytes, str]:
    """Reduce la imagen a lado_maximo px como JPEG (calidad 82). Devuelve (bytes, mime)."""
    with Image.open(io.BytesIO(contenido)) as origen:
        rgb = origen.convert("RGB")
    rgb.thumbnail((lado_maximo, lado_maximo))
    salida = io.BytesIO()
    rgb.save(salida, format="JPEG", quality=82, optimize=True)
    return salida.getvalue(), "image/jpeg"


async def descargar_reducida(
    http: httpx.AsyncClient, url: str, lado_maximo: int = LADO_MAXIMO
) -> tuple[bytes, str] | None:
    """Descarga una imagen pública y la reduce. None si falla (la llamada sigue sin imagen)."""
    try:
        r = await http.get(url, follow_redirects=True)
        r.raise_for_status()
        if len(r.content) > BYTES_MAXIMOS_ORIGEN:
            return None
        return reducir(r.content, lado_maximo)
    except Exception as e:  # red, formato no soportado, etc.
        log.warning("No se pudo guardar la imagen %s: %s", url[:80], e)
        return None
