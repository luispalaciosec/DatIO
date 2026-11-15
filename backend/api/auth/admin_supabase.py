"""Alta de usuarios en Supabase Auth desde el servidor (checklist #12).

El frontend pide el enlace mágico con shouldCreateUser:false: solo entran correos que ya
existen en Supabase Auth. Por eso, al habilitar a alguien en DatIO (/invitar, alta de usuario)
la API lo crea en Auth con la Admin API y el correo ya confirmado. Nunca se generan ni se
devuelven enlaces ni tokens: la persona entra pidiendo su enlace en la pantalla de acceso.

Necesita SUPABASE_SERVICE_ROLE_KEY (solo en el servidor). Sin ella no se crea nada y se
informa: el equipo verá 'sin_clave_auth' en el resultado de la invitación.
"""

import logging

import httpx

from api.config import Configuracion

log = logging.getLogger(__name__)


async def asegurar_usuario_auth(
    config: Configuracion, email: str, http: httpx.AsyncClient | None = None
) -> str:
    """Devuelve 'creado' | 'existente' | 'sin_clave_auth' | 'error_auth'."""
    if not config.supabase_service_role_key or not config.supabase_url:
        log.warning("SUPABASE_SERVICE_ROLE_KEY no configurada: %s no se creó en Auth", email)
        return "sin_clave_auth"
    clave = config.supabase_service_role_key
    propio = http is None
    cliente = http or httpx.AsyncClient(timeout=15)
    try:
        r = await cliente.post(
            f"{config.supabase_url.rstrip('/')}/auth/v1/admin/users",
            headers={"apikey": clave, "Authorization": f"Bearer {clave}"},
            json={"email": email, "email_confirm": True},
        )
    except httpx.HTTPError as e:
        log.error("Supabase Auth no respondió al crear %s: %s", email, type(e).__name__)
        return "error_auth"
    finally:
        if propio:
            await cliente.aclose()
    if r.status_code in (200, 201):
        return "creado"
    cuerpo = r.text.lower()
    if r.status_code in (409, 422) and ("already" in cuerpo or "exists" in cuerpo):
        return "existente"
    log.error("Supabase Auth rechazó crear %s: HTTP %s", email, r.status_code)
    return "error_auth"
