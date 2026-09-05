"""Runner (PT-03): despacha todos los conectores activos. Un fallo no detiene a los demás."""

import logging
from dataclasses import dataclass
from datetime import date

from api.config import Configuracion
from api.etl import conectores  # noqa: F401 — importa y registra los conectores
from api.etl.conector_base import ResultadoCorrida
from api.etl.registro import REGISTRO
from api.etl.repositorio import RepositorioETL

log = logging.getLogger(__name__)


@dataclass
class ResumenCorrida:
    resultados: list[ResultadoCorrida]
    errores: dict[int, str]  # cuenta_id → error
    sin_conector: list[int]  # cuentas cuya plataforma aún no tiene conector

    @property
    def filas_escritas(self) -> int:
        return sum(r.filas_escritas for r in self.resultados)


async def correr_todos(
    repo: RepositorioETL,
    config: Configuracion,
    plataforma: str | None = None,
    hasta: date | None = None,
) -> ResumenCorrida:
    resumen = ResumenCorrida([], {}, [])
    mapeos: dict[str, dict[str, tuple[str, object]]] = {}

    for cuenta in await repo.cuentas_activas(plataforma):
        clase = REGISTRO.get(cuenta.plataforma)
        if clase is None:
            resumen.sin_conector.append(cuenta.id)
            continue
        if clase.plataforma not in mapeos:
            mapeos[clase.plataforma] = dict(await repo.mapeo_plataforma(clase.plataforma))
        conector = clase(cuenta, repo, mapeos[clase.plataforma], config)  # type: ignore[arg-type]
        try:
            resumen.resultados.append(await conector.correr(hasta))
        except Exception as e:
            log.exception("Conector %s falló para cuenta %s", clase.codigo, cuenta.id)
            resumen.errores[cuenta.id] = f"{type(e).__name__}: {e}"
    return resumen
