"""Verificación de JWT emitidos por Supabase Auth (errata E-05).

Supabase puede firmar con HS256 (secreto legacy) o con claves asimétricas (ES256/RS256)
publicadas en /auth/v1/.well-known/jwks.json. Se decide por el `alg` del token, así un
proyecto que migra de un esquema al otro sigue funcionando sin tocar configuración.

El JWKS se descarga con httpx (certificados de certifi) y se cachea en memoria; si llega un
`kid` desconocido se vuelve a descargar una vez (rotación de claves).
"""

import threading
from typing import Any

import httpx
import jwt
from jwt import PyJWK, PyJWKSet

from api.config import Configuracion

AUDIENCIA = "authenticated"
ALGORITMOS_ASIMETRICOS = ["ES256", "RS256"]


class TokenInvalidoError(Exception):
    """Token ausente, inválido o expirado."""


class _CacheJWKS:
    def __init__(self) -> None:
        self._conjuntos: dict[str, PyJWKSet] = {}
        self._lock = threading.Lock()

    def _descargar(self, supabase_url: str) -> PyJWKSet:
        url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        respuesta = httpx.get(url, timeout=10)
        respuesta.raise_for_status()
        conjunto = PyJWKSet.from_dict(respuesta.json())
        with self._lock:
            self._conjuntos[supabase_url] = conjunto
        return conjunto

    def clave(self, supabase_url: str, kid: str | None) -> PyJWK:
        conjunto = self._conjuntos.get(supabase_url) or self._descargar(supabase_url)
        try:
            return _buscar(conjunto, kid)
        except KeyError:
            return _buscar(self._descargar(supabase_url), kid)


def _buscar(conjunto: PyJWKSet, kid: str | None) -> PyJWK:
    for clave in conjunto.keys:
        if kid is None or clave.key_id == kid:
            return clave
    raise KeyError(kid)


_jwks = _CacheJWKS()


# S-2: métodos de inicio de sesión de Supabase (claim `amr`) que prueban que quien entra
# controla el correo: enlace mágico / código por correo y OAuth (Google verifica el correo).
METODOS_QUE_VERIFICAN_CORREO = frozenset({"otp", "magiclink", "oauth"})


def correo_verificado(claims: dict[str, Any]) -> bool:
    """True si el token prueba que el correo del claim `email` está verificado.

    Supabase emite, según el método: `amr` con el método de login, `email_verified` en la raíz
    (versiones recientes) y `user_metadata.email_verified` (OAuth). Un usuario anónimo o un
    registro con contraseña sin confirmar no pasa."""
    if claims.get("is_anonymous") is True:
        return False
    if claims.get("email_verified") is True:
        return True
    metadatos = claims.get("user_metadata")
    if isinstance(metadatos, dict) and metadatos.get("email_verified") is True:
        return True
    amr = claims.get("amr")
    if isinstance(amr, list):
        metodos = {str(m.get("method")) for m in amr if isinstance(m, dict)}
        return bool(metodos & METODOS_QUE_VERIFICAN_CORREO)
    return False


def verificar_token(token: str, config: Configuracion) -> dict[str, Any]:
    try:
        cabecera = jwt.get_unverified_header(token)
        if cabecera.get("alg") == "HS256":
            if not config.supabase_jwt_secret:
                # El detalle (qué variable falta) va al log en deps.usuario_actual (B-11)
                raise TokenInvalidoError("Falta la configuración para validar tokens HS256")
            claims: dict[str, Any] = jwt.decode(
                token, config.supabase_jwt_secret, algorithms=["HS256"], audience=AUDIENCIA
            )
            return claims
        if not config.supabase_url:
            raise TokenInvalidoError("Falta la configuración para validar tokens firmados")
        clave = _jwks.clave(config.supabase_url, cabecera.get("kid"))
        claims = jwt.decode(token, clave.key, algorithms=ALGORITMOS_ASIMETRICOS, audience=AUDIENCIA)
        return claims
    except jwt.PyJWTError as e:
        raise TokenInvalidoError(f"Token inválido: {e}") from e
    except (httpx.HTTPError, KeyError) as e:
        raise TokenInvalidoError(f"No se pudo obtener la clave pública de Supabase: {e}") from e
