"""Pool de conexiones asyncpg. Único punto de creación de conexiones."""

import asyncpg


async def crear_pool(database_url: str) -> asyncpg.Pool:
    # statement_cache_size=0: compatible con el pooler de Supabase en modo transaction.
    return await asyncpg.create_pool(
        database_url, min_size=1, max_size=5, statement_cache_size=0, command_timeout=60
    )
