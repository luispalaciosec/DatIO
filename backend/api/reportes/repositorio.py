"""SQL de invitaciones, editor del reporte y envíos mensuales."""

import json
from datetime import date
from typing import Any

import asyncpg


class RepositorioReportes:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ---- cliente / instancia ---------------------------------------------------------

    async def instancia_de_cliente(self, cliente_id: int) -> dict[str, Any] | None:
        f = await self._pool.fetchrow(
            """
            SELECT i.id, i.plantilla_id, i.nombre_publico, i.slug_publico, c.nombre AS cliente,
                   c.id AS cliente_id, t.color_primario, t.logo_url
            FROM   reporte_instancias i JOIN clientes c ON c.id = i.cliente_id
            LEFT   JOIN cliente_tema t ON t.cliente_id = c.id
            WHERE  i.cliente_id = $1 AND i.activa ORDER BY i.id LIMIT 1
            """,
            cliente_id,
        )
        return dict(f) if f else None

    async def instancias_activas(self) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT i.id, i.slug_publico, i.cliente_id, c.nombre AS cliente, t.color_primario
            FROM   reporte_instancias i JOIN clientes c ON c.id = i.cliente_id
            LEFT   JOIN cliente_tema t ON t.cliente_id = c.id
            WHERE  i.activa AND c.activo ORDER BY c.nombre
            """
        )
        return [dict(f) for f in filas]

    async def correos_cliente(self, cliente_id: int) -> list[str]:
        filas = await self._pool.fetch(
            "SELECT email FROM usuarios WHERE cliente_id = $1 AND rol = 'cliente' AND activo "
            "ORDER BY email",
            cliente_id,
        )
        return [str(f["email"]) for f in filas]

    async def invitar(self, cliente_id: int, email: str) -> None:
        await self._pool.execute(
            """
            INSERT INTO usuarios (email, rol, cliente_id, activo, invitado_en)
            VALUES ($1, 'cliente', $2, TRUE, now())
            ON CONFLICT (email) DO UPDATE SET cliente_id = EXCLUDED.cliente_id, activo = TRUE,
                   invitado_en = now()
            WHERE usuarios.rol = 'cliente'
            """,
            email,
            cliente_id,
        )

    async def rol_de(self, email: str) -> str | None:
        v = await self._pool.fetchval("SELECT rol FROM usuarios WHERE email = $1", email)
        return str(v) if v else None

    # ---- editor del reporte ------------------------------------------------------------

    async def estructura(
        self, instancia_id: int, plantilla_id: int, cliente_id: int
    ) -> list[dict[str, Any]]:
        """Páginas de la plantilla con sus bloques, la config base, el override y si la red
        tiene cuentas conectadas."""
        filas = await self._pool.fetch(
            """
            SELECT p.id AS pagina_id, p.plataforma, p.slug, p.titulo, p.orden AS orden_pagina,
                   b.id AS bloque_id, b.tipo, b.orden, b.config,
                   COALESCE(o.oculto, FALSE) AS oculto,
                   COALESCE(o.config_merge, '{}'::jsonb) AS merge,
                   (SELECT count(*) FROM cuentas_conectadas c
                     WHERE c.cliente_id = $3 AND c.activo
                       AND c.plataforma = p.plataforma) AS cuentas
            FROM   reporte_paginas p
            JOIN   reporte_bloques b ON b.pagina_id = p.id
            LEFT   JOIN reporte_overrides o ON o.bloque_id = b.id AND o.instancia_id = $1
            WHERE  p.plantilla_id = $2
            ORDER  BY p.orden, b.orden
            """,
            instancia_id,
            plantilla_id,
            cliente_id,
        )
        paginas: dict[int, dict[str, Any]] = {}
        for f in filas:
            pag = paginas.setdefault(
                f["pagina_id"],
                {
                    "id": f["pagina_id"],
                    "plataforma": f["plataforma"],
                    "slug": f["slug"],
                    "titulo": f["titulo"],
                    "cuentas": int(f["cuentas"]),
                    "bloques": [],
                },
            )
            config = f["config"] if isinstance(f["config"], dict) else json.loads(f["config"])
            merge = f["merge"] if isinstance(f["merge"], dict) else json.loads(f["merge"])
            pag["bloques"].append(
                {
                    "id": f["bloque_id"],
                    "tipo": f["tipo"],
                    "orden": f["orden"],
                    "config": config,
                    "override": merge,
                    "oculto": bool(f["oculto"]),
                }
            )
        return list(paginas.values())

    async def bloque_pertenece(self, instancia_id: int, bloque_id: int) -> bool:
        return bool(
            await self._pool.fetchval(
                """
                SELECT 1 FROM reporte_bloques b JOIN reporte_paginas p ON p.id = b.pagina_id
                JOIN reporte_instancias i ON i.plantilla_id = p.plantilla_id
                WHERE i.id = $1 AND b.id = $2
                """,
                instancia_id,
                bloque_id,
            )
        )

    async def guardar_override(
        self, instancia_id: int, bloque_id: int, oculto: bool, merge: dict[str, Any]
    ) -> None:
        if not oculto and not merge:
            await self._pool.execute(
                "DELETE FROM reporte_overrides WHERE instancia_id = $1 AND bloque_id = $2",
                instancia_id,
                bloque_id,
            )
            return
        await self._pool.execute(
            """
            INSERT INTO reporte_overrides (instancia_id, bloque_id, oculto, config_merge)
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (instancia_id, bloque_id) DO UPDATE
            SET oculto = EXCLUDED.oculto, config_merge = EXCLUDED.config_merge
            """,
            instancia_id,
            bloque_id,
            oculto,
            json.dumps(merge),
        )

    async def ocultar_pagina(self, instancia_id: int, pagina_id: int, oculto: bool) -> int:
        """Oculta o muestra todos los bloques de una página conservando sus textos propios."""
        r = await self._pool.execute(
            """
            INSERT INTO reporte_overrides (instancia_id, bloque_id, oculto, config_merge)
            SELECT $1, b.id, $3, '{}'::jsonb FROM reporte_bloques b WHERE b.pagina_id = $2
            ON CONFLICT (instancia_id, bloque_id) DO UPDATE SET oculto = EXCLUDED.oculto
            """,
            instancia_id,
            pagina_id,
            oculto,
        )
        return int(r.split()[-1])

    # ---- envíos mensuales --------------------------------------------------------------

    async def ya_enviado(self, instancia_id: int, periodo: date) -> bool:
        return bool(
            await self._pool.fetchval(
                "SELECT 1 FROM envios_reporte WHERE instancia_id = $1 AND periodo = $2 "
                "AND automatico AND estado = 'enviado' LIMIT 1",
                instancia_id,
                periodo,
            )
        )

    async def registrar_envio(
        self,
        instancia_id: int,
        periodo: date,
        destinatarios: list[str],
        automatico: bool,
        estado: str,
        error: str | None,
    ) -> None:
        await self._pool.execute(
            "INSERT INTO envios_reporte (instancia_id, periodo, destinatarios, automatico, estado, "
            "error) VALUES ($1, $2, $3, $4, $5, $6)",
            instancia_id,
            periodo,
            destinatarios,
            automatico,
            estado,
            error,
        )

    async def envios(self, cliente_id: int, limite: int = 12) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT e.periodo, e.destinatarios, e.automatico, e.estado, e.error, e.enviado_en
            FROM   envios_reporte e JOIN reporte_instancias i ON i.id = e.instancia_id
            WHERE  i.cliente_id = $1 ORDER BY e.id DESC LIMIT $2
            """,
            cliente_id,
            limite,
        )
        return [dict(f) for f in filas]

    async def paginas_con_kpis(
        self, instancia_id: int, plantilla_id: int, cliente_id: int
    ) -> list[dict[str, Any]]:
        """Redes conectadas del cliente con los items de su primera fila de KPIs visible
        (lo que el correo mensual resume)."""
        filas = await self._pool.fetch(
            """
            SELECT DISTINCT ON (p.plataforma) p.plataforma, p.titulo,
                   (b.config || COALESCE(o.config_merge, '{}'::jsonb)) AS config
            FROM   reporte_paginas p
            JOIN   reporte_bloques b ON b.pagina_id = p.id AND b.tipo = 'kpi_fila'
            LEFT   JOIN reporte_overrides o ON o.bloque_id = b.id AND o.instancia_id = $1
            WHERE  p.plantilla_id = $2 AND p.slug IN ('metricas', 'busqueda')
              AND  NOT COALESCE(o.oculto, FALSE)
              AND  EXISTS (SELECT 1 FROM cuentas_conectadas c WHERE c.cliente_id = $3
                           AND c.activo AND c.plataforma = p.plataforma)
            ORDER  BY p.plataforma, p.orden, b.orden
            """,
            instancia_id,
            plantilla_id,
            cliente_id,
        )
        salida = []
        for f in filas:
            config = f["config"] if isinstance(f["config"], dict) else json.loads(f["config"])
            salida.append(
                {
                    "plataforma": f["plataforma"],
                    "titulo": f["titulo"],
                    "items": config.get("items", []),
                }
            )
        return salida
