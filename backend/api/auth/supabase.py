"""Verificación de JWT emitidos por Supabase Auth (errata E-05).

Supabase puede firmar con HS256 (secreto legacy) o con claves asimétricas (ES256/RS256)
publicadas en /auth/v1/.well-known/jwks.json. Se decide por el `alg` del token, así un
proyecto que migra de un esquema al otro sigue funcionando sin tocar configuración.
"""

from functools import lru_cache
from typing import Any

import jwt

from api.config import Configuracion

AUDIENCIA = "authenticated"
ALGORITMOS_ASIMETRICOS = ["ES256", "RS256"]


class TokenInvalidoError(Exception):
    """Token ausente, inválido o expirado."""


@lru_cache(maxsize=4)
def _cliente_jwks(supabase_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def verificar_token(token: str, config: Configuracion) -> dict[str, Any]:
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            if not config.supabase_jwt_secret:
                raise TokenInvalidoError("Token HS256 pero SUPABASE_JWT_SECRET no está configurado")
            claims: dict[str, Any] = jwt.decode(
                token, config.supabase_jwt_secret, algorithms=["HS256"], audience=AUDIENCIA
            )
            return claims
        if not config.supabase_url:
            raise TokenInvalidoError("SUPABASE_URL no está configurado")
        clave = _cliente_jwks(config.supabase_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, clave.key, algorithms=ALGORITMOS_ASIMETRICOS, audience=AUDIENCIA)
        return claims
    except jwt.PyJWTError as e:
        raise TokenInvalidoError(f"Token inválido: {e}") from e
