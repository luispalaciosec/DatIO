"""SQL de la capa LLM: sector del cliente y registro en llm_uso."""

from decimal import Decimal

import asyncpg


class RepositorioLLM:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def sector_cliente(self, cliente_id: int) -> str | None:
        valor = await self._pool.fetchval("SELECT sector FROM clientes WHERE id = $1", cliente_id)
        return str(valor) if valor else None

    async def registrar_uso(
        self,
        tarea: str,
        proveedor: str,
        modelo: str,
        cliente_id: int | None,
        tokens_entrada: int,
        tokens_salida: int,
        costo_usd: Decimal | None,
        latencia_ms: int,
        exito: bool,
        error_detalle: str | None = None,
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO llm_uso (tarea, proveedor, modelo, cliente_id, tokens_entrada,
                                 tokens_salida, costo_usd, latencia_ms, exito, error_detalle)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            tarea,
            proveedor,
            modelo,
            cliente_id,
            tokens_entrada,
            tokens_salida,
            costo_usd,
            latencia_ms,
            exito,
            error_detalle,
        )
