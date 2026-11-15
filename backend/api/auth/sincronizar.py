"""Crea en Supabase Auth a los usuarios activos de DatIO que todavía no existen allí (#12).

Correr UNA vez antes de publicar el frontend con shouldCreateUser:false, para que los
invitados que nunca entraron puedan pedir su enlace:

    python -m api.auth.sincronizar

Necesita DATABASE_URL, SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY. No envía correos ni genera
enlaces. Es idempotente: los que ya existen salen como 'existente'.
"""

import asyncio
import logging
from collections import Counter

from api.auth.admin_supabase import asegurar_usuario_auth
from api.config import obtener_config
from api.db import crear_pool


async def sincronizar() -> Counter[str]:
    config = obtener_config()
    pool = await crear_pool(config.database_url)
    try:
        correos = [
            str(f["email"])
            for f in await pool.fetch("SELECT email FROM usuarios WHERE activo ORDER BY email")
        ]
    finally:
        await pool.close()
    return Counter([await asegurar_usuario_auth(config, c) for c in correos])


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    resumen = asyncio.run(sincronizar())
    logging.getLogger(__name__).info("usuarios en Supabase Auth: %s", dict(resumen))
    return 0 if not (resumen["error_auth"] or resumen["sin_clave_auth"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
