"""Corrida del ETL desde línea de comandos (Railway Cron 06:00 Ecuador).

    python -m api.etl.cli [--plataforma ga4] [--hasta 2026-09-04]

Sale con código 1 si alguna cuenta falló, para que Railway marque la corrida en rojo.
"""

import argparse
import asyncio
import logging
import sys
from datetime import date

from api.config import obtener_config
from api.db import crear_pool
from api.etl.repositorio import RepositorioETL
from api.etl.runner import ResumenCorrida, correr_todos


async def ejecutar(plataforma: str | None, hasta: date | None) -> ResumenCorrida:
    config = obtener_config()
    pool = await crear_pool(config.database_url)
    try:
        return await correr_todos(RepositorioETL(pool), config, plataforma, hasta)
    finally:
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Captura diaria de DatIO")
    parser.add_argument("--plataforma", default=None, help="solo esta plataforma (ej. meta_ig)")
    parser.add_argument("--hasta", type=date.fromisoformat, default=None, help="último día")
    args = parser.parse_args(argv)

    resumen = asyncio.run(ejecutar(args.plataforma, args.hasta))
    for r in resumen.resultados:
        print(
            f"{r.conector:10s} cuenta={r.cuenta_id} {r.desde}→{r.hasta} "
            f"filas={r.filas_escritas} estado={r.estado}"
        )
    for cuenta_id, error in resumen.errores.items():
        print(f"ERROR cuenta={cuenta_id}: {error}", file=sys.stderr)
    if resumen.sin_conector:
        print(f"Sin conector todavía: cuentas {resumen.sin_conector}")
    print(f"Total filas escritas: {resumen.filas_escritas}")
    return 1 if resumen.errores else 0


if __name__ == "__main__":
    sys.exit(main())
