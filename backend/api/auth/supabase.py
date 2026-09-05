"""Verificación de JWT emitidos por Supabase Auth (errata E-05).

Soporta los dos esquemas de firma de Supabase:
  * legacy: HS256 con SUPABASE_JWT_SECRET
  * actual: claves asimétricas publicadas en /auth/v1/.well-known/jwks.json
"""

from functools import lru_cache
from typing import Any

import jwt

from api.config import Configuracion

AUDIENCIA = "authenticated"


class TokenInvalidoError(Exception):
    """Token ausente, inválido o expirado."""


@lru_cache(maxsize=4)
def _cliente_jwks(supabase_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def verificar_token(token: str, config: Configuracion) -> dict[str, Any]:
    try:
        if config.supabase_jwt_secret:
            claims: dict[str, Any] = jwt.decode(
                token, config.supabase_jwt_secret, algorithms=["HS256"], audience=AUDIENCIA
            )
            return claims
        if not config.supabase_url:
            raise TokenInvalidoError("Supabase Auth no está configurado")
        clave = _cliente_jwks(config.supabase_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, clave.key, algorithms=["ES256", "RS256"], audience=AUDIENCIA)
        return claims
    except jwt.PyJWTError as e:
        raise TokenInvalidoError(f"Token inválido: {e}") from e
