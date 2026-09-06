"""SQL del módulo administrador. Todo el acceso a datos del admin vive aquí."""

import json
from typing import Any

import asyncpg

CAMPOS_TEMA = (
    "logo_url",
    "banner_url",
    "color_primario",
    "color_secundario",
    "color_acento",
    "fuente_titulos",
    "fuente_cuerpo",
    "modo_oscuro",
)


class RepositorioAdmin:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ---- clientes -----------------------------------------------------------

    async def clientes(self) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT c.id, c.nombre, c.slug, c.sector, c.activo, c.creado_en,
                   (SELECT count(*) FROM cuentas_conectadas x
                     WHERE x.cliente_id = c.id AND x.activo) AS cuentas,
                   (SELECT count(*) FROM usuarios u
                     WHERE u.cliente_id = c.id AND u.activo) AS usuarios,
                   (SELECT slug_publico FROM reporte_instancias i
                     WHERE i.cliente_id = c.id AND i.activa ORDER BY i.id LIMIT 1) AS slug_publico,
                   t.color_primario, t.logo_url
            FROM   clientes c LEFT JOIN cliente_tema t ON t.cliente_id = c.id
            ORDER  BY c.activo DESC, c.nombre
            """
        )
        return [dict(f) for f in filas]

    async def cliente(self, cliente_id: int) -> dict[str, Any] | None:
        f = await self._pool.fetchrow(
            "SELECT id, nombre, slug, sector, activo, creado_en FROM clientes WHERE id = $1",
            cliente_id,
        )
        return dict(f) if f else None

    async def crear_cliente(
        self, nombre: str, slug: str, sector: str | None, plantilla_id: int | None
    ) -> int:
        async with self._pool.acquire() as con, con.transaction():
            cliente_id = await con.fetchval(
                "INSERT INTO clientes (nombre, slug, sector) VALUES ($1, $2, $3) RETURNING id",
                nombre,
                slug,
                sector,
            )
            await con.execute("INSERT INTO cliente_tema (cliente_id) VALUES ($1)", cliente_id)
            if plantilla_id is None:
                plantilla_id = await con.fetchval(
                    "SELECT id FROM reporte_plantillas WHERE activa ORDER BY id LIMIT 1"
                )
            if plantilla_id is not None:
                await con.execute(
                    "INSERT INTO reporte_instancias (cliente_id, plantilla_id, nombre_publico, "
                    "slug_publico) VALUES ($1, $2, $3, $4)",
                    cliente_id,
                    plantilla_id,
                    f"{nombre} - RRSS",
                    slug,
                )
            return int(cliente_id)

    async def actualizar_cliente(self, cliente_id: int, cambios: dict[str, Any]) -> None:
        permitidos = {k: v for k, v in cambios.items() if k in {"nombre", "sector", "activo"}}
        if not permitidos:
            return
        asignaciones = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(permitidos))
        await self._pool.execute(
            f"UPDATE clientes SET {asignaciones} WHERE id = $1", cliente_id, *permitidos.values()
        )

    # ---- tema ---------------------------------------------------------------

    async def tema(self, cliente_id: int) -> dict[str, Any]:
        f = await self._pool.fetchrow(
            f"SELECT {', '.join(CAMPOS_TEMA)} FROM cliente_tema WHERE cliente_id = $1", cliente_id
        )
        if f is None:
            await self._pool.execute(
                "INSERT INTO cliente_tema (cliente_id) VALUES ($1)", cliente_id
            )
            return await self.tema(cliente_id)
        return dict(f)

    async def guardar_tema(self, cliente_id: int, cambios: dict[str, Any]) -> dict[str, Any]:
        permitidos = {k: v for k, v in cambios.items() if k in CAMPOS_TEMA}
        await self.tema(cliente_id)  # asegura la fila
        if permitidos:
            asignaciones = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(permitidos))
            await self._pool.execute(
                f"UPDATE cliente_tema SET {asignaciones} WHERE cliente_id = $1",
                cliente_id,
                *permitidos.values(),
            )
        return await self.tema(cliente_id)

    # ---- cuentas ------------------------------------------------------------

    async def cuentas(self, cliente_id: int) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT c.id, c.plataforma, p.nombre AS plataforma_nombre, c.id_externo,
                   c.nombre_cuenta, c.activo, c.creado_en,
                   c.credencial_cifrada IS NOT NULL AS tiene_credencial,
                   (SELECT max(iniciado_en) FROM jobs_ejecucion j
                     WHERE j.cuenta_id = c.id AND j.estado IN ('ok','parcial')) AS ultima_captura
            FROM   cuentas_conectadas c JOIN plataformas p ON p.codigo = c.plataforma
            WHERE  c.cliente_id = $1 ORDER BY c.plataforma, c.id
            """,
            cliente_id,
        )
        return [dict(f) for f in filas]

    async def crear_cuenta(
        self, cliente_id: int, plataforma: str, id_externo: str, nombre_cuenta: str | None
    ) -> int:
        cuenta_id = await self._pool.fetchval(
            "INSERT INTO cuentas_conectadas (cliente_id, plataforma, id_externo, nombre_cuenta) "
            "VALUES ($1, $2, $3, $4) RETURNING id",
            cliente_id,
            plataforma,
            id_externo,
            nombre_cuenta,
        )
        return int(cuenta_id)

    async def actualizar_cuenta(self, cuenta_id: int, cambios: dict[str, Any]) -> None:
        permitidos = {k: v for k, v in cambios.items() if k in {"nombre_cuenta", "activo"}}
        if not permitidos:
            return
        asignaciones = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(permitidos))
        await self._pool.execute(
            f"UPDATE cuentas_conectadas SET {asignaciones} WHERE id = $1",
            cuenta_id,
            *permitidos.values(),
        )

    async def guardar_credencial(self, cuenta_id: int, credencial: str, clave: str) -> None:
        await self._pool.execute(
            "UPDATE cuentas_conectadas SET credencial_cifrada = pgp_sym_encrypt($2, $3) "
            "WHERE id = $1",
            cuenta_id,
            credencial,
            clave,
        )

    async def cuenta_cliente(self, cuenta_id: int) -> int | None:
        v = await self._pool.fetchval(
            "SELECT cliente_id FROM cuentas_conectadas WHERE id = $1", cuenta_id
        )
        return int(v) if v is not None else None

    # ---- usuarios -----------------------------------------------------------

    async def usuarios(self, cliente_id: int | None = None) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT u.email, u.rol, u.cliente_id, c.nombre AS cliente_nombre, u.activo, u.creado_en
            FROM   usuarios u LEFT JOIN clientes c ON c.id = u.cliente_id
            WHERE  ($1::bigint IS NULL OR u.cliente_id = $1)
            ORDER  BY u.rol, u.email
            """,
            cliente_id,
        )
        return [dict(f) for f in filas]

    async def guardar_usuario(self, email: str, rol: str, cliente_id: int | None) -> None:
        await self._pool.execute(
            """
            INSERT INTO usuarios (email, rol, cliente_id, activo) VALUES ($1, $2, $3, TRUE)
            ON CONFLICT (email) DO UPDATE SET rol = EXCLUDED.rol, cliente_id = EXCLUDED.cliente_id,
                                              activo = TRUE
            """,
            email,
            rol,
            cliente_id,
        )

    async def desactivar_usuario(self, email: str) -> None:
        await self._pool.execute("UPDATE usuarios SET activo = FALSE WHERE email = $1", email)

    # ---- catálogos y capturas ------------------------------------------------

    async def plataformas(self) -> list[dict[str, Any]]:
        return [dict(f) for f in await self._pool.fetch("SELECT codigo, nombre FROM plataformas")]

    async def plantillas(self) -> list[dict[str, Any]]:
        return [
            dict(f)
            for f in await self._pool.fetch(
                "SELECT id, nombre, descripcion FROM reporte_plantillas WHERE activa ORDER BY id"
            )
        ]

    async def jobs_recientes(self, limite: int = 50) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT j.id, j.conector, j.cuenta_id, cl.nombre AS cliente, c.nombre_cuenta,
                   j.estado, j.filas_escritas, j.error_detalle, j.iniciado_en, j.finalizado_en
            FROM   jobs_ejecucion j
            LEFT   JOIN cuentas_conectadas c ON c.id = j.cuenta_id
            LEFT   JOIN clientes cl ON cl.id = c.cliente_id
            ORDER  BY j.id DESC LIMIT $1
            """,
            limite,
        )
        return [dict(f) for f in filas]

    # ---- conexiones OAuth ---------------------------------------------------

    async def crear_conexion(
        self,
        cliente_id: int,
        proveedor: str,
        creado_por: str,
        credencial: str,
        clave: str,
        expira_en: Any,
        activos: list[dict[str, Any]],
    ) -> int:
        cid = await self._pool.fetchval(
            """
            INSERT INTO conexiones_oauth
                   (cliente_id, proveedor, creado_por, token_cifrado, token_expira_en, activos)
            VALUES ($1, $2, $3, pgp_sym_encrypt($4, $5), $6, $7::jsonb) RETURNING id
            """,
            cliente_id,
            proveedor,
            creado_por,
            credencial,
            clave,
            expira_en,
            json.dumps(activos),
        )
        return int(cid)

    async def conexion(self, conexion_id: int) -> dict[str, Any] | None:
        f = await self._pool.fetchrow(
            "SELECT id, cliente_id, proveedor, creado_por, activos, estado, creado_en, "
            "token_expira_en FROM conexiones_oauth WHERE id = $1",
            conexion_id,
        )
        if f is None:
            return None
        d = dict(f)
        if isinstance(d["activos"], str):
            d["activos"] = json.loads(d["activos"])
        return d

    async def activar_conexion(
        self, conexion_id: int, elegidos: list[dict[str, Any]], clave: str
    ) -> list[int]:
        """Crea (o reactiva) cuentas_conectadas con el token de la conexión y la marca activada."""
        ids: list[int] = []
        async with self._pool.acquire() as con, con.transaction():
            fila = await con.fetchrow(
                "SELECT cliente_id, pgp_sym_decrypt(token_cifrado, $2) AS credencial, "
                "token_expira_en FROM conexiones_oauth WHERE id = $1 AND estado = 'pendiente'",
                conexion_id,
                clave,
            )
            if fila is None:
                raise LookupError("Conexión no encontrada o ya activada")
            for a in elegidos:
                cuenta_id = await con.fetchval(
                    """
                    INSERT INTO cuentas_conectadas
                           (cliente_id, plataforma, id_externo, nombre_cuenta, credencial_cifrada,
                            token_expira_en, activo)
                    VALUES ($1, $2, $3, $4, pgp_sym_encrypt($5, $6), $7, TRUE)
                    ON CONFLICT (plataforma, id_externo) DO UPDATE
                       SET cliente_id = EXCLUDED.cliente_id, nombre_cuenta = EXCLUDED.nombre_cuenta,
                           credencial_cifrada = EXCLUDED.credencial_cifrada,
                           token_expira_en = EXCLUDED.token_expira_en, activo = TRUE
                    RETURNING id
                    """,
                    fila["cliente_id"],
                    a["plataforma"],
                    a["id_externo"],
                    a.get("nombre"),
                    fila["credencial"],
                    clave,
                    fila["token_expira_en"],
                )
                ids.append(int(cuenta_id))
            await con.execute(
                "UPDATE conexiones_oauth SET estado = 'activada', token_cifrado = ''::bytea "
                "WHERE id = $1",
                conexion_id,
            )
        return ids
