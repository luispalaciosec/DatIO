"""Router multi-proveedor (spec/07 §5). Proveedor y modelo se resuelven por configuración.

Reglas:
  * nunca hardcodear un modelo: viene de Configuracion.llm_modelos (LLM_MODELOS)
  * clientes del sector financiero → variante `<tarea>_regulado` (host occidental)
  * cada llamada se registra en llm_uso, también las fallidas
  * el LLM nunca genera cifras; eso lo valida quien consume la salida (PT-17/18)
"""

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from api.config import Configuracion
from api.llm.repositorio import RepositorioLLM

SECTORES_REGULADOS = frozenset({"banca", "financiero", "finanzas", "seguros", "fintech"})


@dataclass(frozen=True)
class ConfigModelo:
    tarea: str
    proveedor: str
    modelo: str
    batch: bool = False

    @property
    def nombre_litellm(self) -> str:
        return f"{self.proveedor}/{self.modelo}"


def resolver_config(tarea: str, config: Configuracion, sector: str | None = None) -> ConfigModelo:
    """Elige la fila de configuración. Sector regulado fuerza la variante `_regulado`."""
    modelos = config.llm_modelos
    clave = tarea
    if sector and sector.lower() in SECTORES_REGULADOS and f"{tarea}_regulado" in modelos:
        clave = f"{tarea}_regulado"
    if clave not in modelos:
        raise KeyError(f"Tarea LLM sin configuración: {tarea}")
    fila = modelos[clave]
    return ConfigModelo(clave, fila["proveedor"], fila["modelo"], bool(fila.get("batch", False)))


async def completar(
    tarea: str,
    mensajes: list[dict[str, Any]],
    config: Configuracion,
    repo: RepositorioLLM,
    cliente_id: int | None = None,
) -> str:
    sector = await repo.sector_cliente(cliente_id) if cliente_id is not None else None
    cfg = resolver_config(tarea, config, sector)

    import litellm  # import perezoso: es pesado y solo hace falta al llamar

    inicio = time.perf_counter()
    try:
        respuesta = await litellm.acompletion(model=cfg.nombre_litellm, messages=mensajes)
    except Exception as e:
        await repo.registrar_uso(
            cfg.tarea,
            cfg.proveedor,
            cfg.modelo,
            cliente_id,
            0,
            0,
            None,
            int((time.perf_counter() - inicio) * 1000),
            False,
            f"{type(e).__name__}: {e}",
        )
        raise

    uso = getattr(respuesta, "usage", None)
    try:
        costo: Decimal | None = Decimal(str(litellm.completion_cost(respuesta)))
    except Exception:
        costo = None
    await repo.registrar_uso(
        cfg.tarea,
        cfg.proveedor,
        cfg.modelo,
        cliente_id,
        int(getattr(uso, "prompt_tokens", 0) or 0),
        int(getattr(uso, "completion_tokens", 0) or 0),
        costo,
        int((time.perf_counter() - inicio) * 1000),
        True,
    )
    contenido = respuesta.choices[0].message.content
    return str(contenido or "")
