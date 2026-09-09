"""Corrida del ETL desde línea de comandos (Railway Cron 06:00 Ecuador).

    python -m api.etl.cli [--plataforma ga4] [--hasta 2026-09-04] [--live]

--live (PT-12): captura hasta hoy, marca hoy y ayer como provisionales, sin radar ni
publicaciones. Pensado para un cron intradía (p. ej. cada 3 horas) sobre Meta.

Sale con código 1 si alguna cuenta falló, para que Railway marque la corrida en rojo.
"""

import argparse
import asyncio
import logging
import sys
from datetime import date

from api.config import obtener_config
from api.db import crear_pool
from api.etl.radar import ResumenRadar, correr_radar
from api.etl.repositorio import RepositorioETL
from api.etl.runner import ResumenCorrida, correr_todos


async def ejecutar(
    plataforma: str | None,
    hasta: date | None,
    radar: bool = True,
    forzar_radar: bool = False,
    live: bool = False,
) -> tuple[ResumenCorrida, ResumenRadar | None]:
    config = obtener_config()
    pool = await crear_pool(config.database_url)
    try:
        repo = RepositorioETL(pool)
        resumen = await correr_todos(repo, config, plataforma, hasta, live=live)
        radar_resumen = None
        if radar and plataforma is None and not live:
            radar_resumen = await correr_radar(
                repo, config, forzar=forzar_radar, dias_minimos=config.radar_dias_minimos
            )
        return resumen, radar_resumen
    finally:
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Captura diaria de DatIO")
    parser.add_argument("--plataforma", default=None, help="solo esta plataforma (ej. meta_ig)")
    parser.add_argument("--hasta", type=date.fromisoformat, default=None, help="último día")
    parser.add_argument("--sin-radar", action="store_true", help="no correr el radar competitivo")
    parser.add_argument("--forzar-radar", action="store_true", help="radar aunque no toque")
    parser.add_argument("--live", action="store_true", help="captura intradía provisional")
    args = parser.parse_args(argv)

    resumen, radar = asyncio.run(
        ejecutar(args.plataforma, args.hasta, not args.sin_radar, args.forzar_radar, args.live)
    )
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
    if radar is not None:
        print(
            f"radar: {radar.competidores} competidores, {radar.snapshots} valores, "
            f"USD {radar.costo_usd:.4f}, errores={radar.errores}, omitidos={radar.omitidos}"
        )
    return 1 if resumen.errores else 0


if __name__ == "__main__":
    sys.exit(main())
