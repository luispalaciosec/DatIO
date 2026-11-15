"""Sentry para la API y el cron (Fase 4). Apagado si no hay SENTRY_DSN: no se inicializa nada.

Nunca se envían datos personales ni secretos: send_default_pii=False y antes de enviar se
limpian cabeceras de autorización y cookies, el token de render (query `render`/`token`),
cualquier valor con forma de JWT y los correos electrónicos.
"""

import re
from typing import Any

from api.config import Configuracion

CABECERAS_SENSIBLES = {"authorization", "cookie", "set-cookie", "x-cron-secret", "apikey"}
PARAMETROS_SENSIBLES = ("render", "token", "code", "state", "access_token")
RE_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
RE_CORREO = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RE_PARAM = re.compile(r"(?i)\b(" + "|".join(PARAMETROS_SENSIBLES) + r")=[^&\s\"']+")


def limpiar_texto(texto: str) -> str:
    texto = RE_PARAM.sub(lambda m: f"{m.group(1)}=[filtrado]", texto)
    texto = RE_JWT.sub("[jwt]", texto)
    return RE_CORREO.sub("[correo]", texto)


def _limpiar(valor: Any) -> Any:
    if isinstance(valor, str):
        return limpiar_texto(valor)
    if isinstance(valor, dict):
        return {
            k: "[filtrado]" if str(k).lower() in CABECERAS_SENSIBLES else _limpiar(v)
            for k, v in valor.items()
        }
    if isinstance(valor, list | tuple):
        return [_limpiar(v) for v in valor]
    return valor


def antes_de_enviar(evento: dict[str, Any], _pista: dict[str, Any]) -> dict[str, Any]:
    """before_send / before_breadcrumb: limpia todo el evento de secretos y correos."""
    limpio: dict[str, Any] = _limpiar(evento)
    peticion = limpio.get("request")
    if isinstance(peticion, dict):
        peticion.pop("cookies", None)
        peticion.pop("data", None)  # cuerpos (credenciales de cuentas, correos de invitación)
    limpio.pop("user", None)
    return limpio


def iniciar_sentry(config: Configuracion, componente: str) -> bool:
    """Inicializa Sentry si hay DSN. Devuelve True si quedó activo."""
    if not config.sentry_dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=config.sentry_dsn,
        environment=config.ambiente,
        server_name=componente,
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
        before_send=antes_de_enviar,  # type: ignore[arg-type]
        before_breadcrumb=antes_de_enviar,
    )
    sentry_sdk.set_tag("componente", componente)
    return True
