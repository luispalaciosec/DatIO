"""Runner (PT-03): despacha todos los conectores activos. Un fallo no detiene a los demás."""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from api.config import Configuracion
from api.etl import conectores  # noqa: F401 — importa y registra los conectores
from api.etl.conector_base import ResultadoCorrida, hoy_en
from api.etl.registro import REGISTRO, REGISTRO_PUBLICACIONES
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
    live: bool = False,
) -> ResumenCorrida:
    """live=True (PT-12): captura hasta HOY y marca hoy y ayer como provisionales.
    Solo corre los conectores de métricas diarias (no publicaciones)."""
    resumen = ResumenCorrida([], {}, [])
    provisional_desde: date | None = None
    if live:
        hoy = hoy_en(config.zona_horaria)
        hasta = hoy
        provisional_desde = hoy - timedelta(days=1)
    mapeos: dict[str, dict[str, tuple[str, object]]] = {}

    for cuenta in await repo.cuentas_activas(plataforma):
        clases = [
            c
            for c in (
                REGISTRO.get(cuenta.plataforma),
                None if live else REGISTRO_PUBLICACIONES.get(cuenta.plataforma),
            )
            if c
        ]
        if not clases:
            resumen.sin_conector.append(cuenta.id)
            continue
        if cuenta.plataforma not in mapeos:
            mapeos[cuenta.plataforma] = dict(await repo.mapeo_plataforma(cuenta.plataforma))
        for clase in clases:
            conector = clase(cuenta, repo, mapeos[cuenta.plataforma], config)  # type: ignore[arg-type]
            try:
                resumen.resultados.append(await conector.correr(hasta, provisional_desde))
            except Exception as e:
                log.exception("Conector %s falló para cuenta %s", clase.codigo, cuenta.id)
                resumen.errores[cuenta.id] = f"{clase.codigo}: {type(e).__name__}: {e}"
    return resumen
