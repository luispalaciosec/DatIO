"""Middlewares de seguridad de la API: cabeceras defensivas y límite de peticiones por IP.

El límite es en memoria y por proceso (una réplica en Railway): basta para frenar fuerza
bruta o scraping de las rutas públicas (/radar/imagen, retornos OAuth, /consulta). Si algún
día hay varias réplicas, este límite se vuelve por réplica; con Redis (PT-12) pasaría a global.
"""

import time
from collections import deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

CABECERAS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Cache-Control": "no-store",
}
# Respuestas que sí se pueden cachear (imágenes públicas del radar, PDF)
CACHEABLES = ("/radar/imagen/",)


class CabecerasSeguridad(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        respuesta = await call_next(request)
        for k, v in CABECERAS.items():
            if k == "Cache-Control" and (
                request.url.path.startswith(CACHEABLES) or "Cache-Control" in respuesta.headers
            ):
                continue
            respuesta.headers.setdefault(k, v)
        return respuesta


def ip_cliente(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


class LimiteVentana:
    """Ventana deslizante: máximo N peticiones por IP en S segundos."""

    def __init__(self, maximo: int, segundos: float) -> None:
        self.maximo = maximo
        self.segundos = segundos
        self._por_ip: dict[str, deque[float]] = {}

    def permitir(self, ip: str, ahora: float | None = None) -> bool:
        t = ahora if ahora is not None else time.monotonic()
        cola = self._por_ip.setdefault(ip, deque())
        while cola and t - cola[0] > self.segundos:
            cola.popleft()
        if len(cola) >= self.maximo:
            return False
        cola.append(t)
        if len(self._por_ip) > 10_000:  # no crecer sin límite con IPs de un solo uso
            for k in [k for k, c in self._por_ip.items() if not c or t - c[-1] > self.segundos]:
                self._por_ip.pop(k, None)
        return True


class LimitePeticiones(BaseHTTPMiddleware):
    def __init__(self, app: object, maximo: int = 600, segundos: float = 60.0) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.limite = LimiteVentana(maximo, segundos)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path == "/health" or request.method == "OPTIONS":
            return await call_next(request)
        if not self.limite.permitir(ip_cliente(request)):
            return JSONResponse(
                {"detail": "Demasiadas peticiones, intenta en un minuto"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
