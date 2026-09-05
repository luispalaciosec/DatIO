"""Lectura estática del seed de métricas para tests que no necesitan base de datos."""

import re
from decimal import Decimal
from pathlib import Path

RUTA_SEED = Path(__file__).resolve().parents[2] / "sql" / "seeds" / "metricas.sql"

_RE_METRICA = re.compile(r"^\('([a-z_]+)',\s*'[^']*',\s*'[a-z]+',", re.M)
_RE_MAPEO = re.compile(r"\('([a-z_0-9]+)',\s*'([A-Za-z0-9_.]+)',\s*'([a-z_]+)',\s*([0-9.]+)\)")


def metricas_del_seed() -> set[str]:
    return set(_RE_METRICA.findall(RUTA_SEED.read_text(encoding="utf-8")))


def mapeos_del_seed() -> dict[str, dict[str, tuple[str, Decimal]]]:
    salida: dict[str, dict[str, tuple[str, Decimal]]] = {}
    for plataforma, nativa, codigo, factor in _RE_MAPEO.findall(
        RUTA_SEED.read_text(encoding="utf-8")
    ):
        salida.setdefault(plataforma, {})[nativa] = (codigo, Decimal(factor))
    return salida
