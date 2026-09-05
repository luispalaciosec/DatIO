"""Repositorio de usuarios, clientes y cuentas (PT-07). Único lugar con SQL de este dominio."""

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class Usuario:
    email: str
    rol: str
    cliente_id: int | None


@dataclass(frozen=True)
class Cliente:
    id: int
    nombre: str
    slug: str
    sector: str | None


@dataclass(frozen=True)
class CuentaResumen:
    id: int
    plataforma: str
    id_externo: str
    nombre_cuenta: str | None
    activo: bool


class RepositorioAuth:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def usuario_por_email(self, email: str) -> Usuario | None:
        fila = await self._pool.fetchrow(
            "SELECT email, rol, cliente_id FROM usuarios WHERE email = $1 AND activo", email
        )
        return Usuario(fila["email"], fila["rol"], fila["cliente_id"]) if fila else None

    async def cliente_por_slug(self, slug: str) -> Cliente | None:
        fila = await self._pool.fetchrow(
            "SELECT id, nombre, slug, sector FROM clientes WHERE slug = $1 AND activo", slug
        )
        return Cliente(fila["id"], fila["nombre"], fila["slug"], fila["sector"]) if fila else None

    async def cliente_por_id(self, cliente_id: int) -> Cliente | None:
        fila = await self._pool.fetchrow(
            "SELECT id, nombre, slug, sector FROM clientes WHERE id = $1", cliente_id
        )
        return Cliente(fila["id"], fila["nombre"], fila["slug"], fila["sector"]) if fila else None

    async def cuentas_de_cliente(self, cliente_id: int) -> list[CuentaResumen]:
        filas = await self._pool.fetch(
            """
            SELECT id, plataforma, id_externo, nombre_cuenta, activo
            FROM   cuentas_conectadas
            WHERE  cliente_id = $1
            ORDER  BY plataforma, id
            """,
            cliente_id,
        )
        return [
            CuentaResumen(
                f["id"], f["plataforma"], f["id_externo"], f["nombre_cuenta"], f["activo"]
            )
            for f in filas
        ]
