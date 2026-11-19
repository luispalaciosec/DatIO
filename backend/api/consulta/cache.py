"""Cache en proceso de /consulta (PT-12).

Una entrada vive hasta `ttl_seg` o hasta que cambia la "generación": la última captura del
ETL cerrada (jobs_ejecucion.finalizado_en) más la versión de configuración (config_version,
sql/015, que suben triggers al editar reporte, tema, competidores, cuentas o clientes). Se
consulta como mucho cada 60 s, así que otro proceso ve un cambio en <= 60 s; el proceso que
hizo la edición lo ve en la petición siguiente porque el admin llama a vaciar() (B-7).
Los resultados provisionales no se cachean: cambian con cada captura live.
"""

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

Clave = tuple[int, int, str, str, str | None]


@dataclass
class CacheConsulta:
    ttl_seg: int = 900
    capacidad: int = 5000
    _entradas: OrderedDict[tuple[Clave, str], tuple[float, dict[str, Any]]] = field(
        default_factory=OrderedDict
    )
    _generacion: str = ""
    _generacion_vista_en: float = 0.0
    aciertos: int = 0
    fallos: int = 0

    def generacion_vigente(self, ahora: float | None = None) -> bool:
        """True si hace menos de 60 s que confirmamos la generación (no hace falta consultar)."""
        ahora = time.monotonic() if ahora is None else ahora
        return ahora - self._generacion_vista_en < 60

    def fijar_generacion(self, generacion: str, ahora: float | None = None) -> None:
        ahora = time.monotonic() if ahora is None else ahora
        if generacion != self._generacion:
            self._entradas.clear()
            self._generacion = generacion
        self._generacion_vista_en = ahora

    def obtener(self, clave: Clave, ahora: float | None = None) -> dict[str, Any] | None:
        ahora = time.monotonic() if ahora is None else ahora
        entrada = self._entradas.get((clave, self._generacion))
        if entrada is None or entrada[0] < ahora:
            self.fallos += 1
            self._entradas.pop((clave, self._generacion), None)
            return None
        self.aciertos += 1
        return entrada[1]

    def guardar(self, clave: Clave, respuesta: dict[str, Any], ahora: float | None = None) -> None:
        if respuesta.get("estado") == "provisional":
            return
        ahora = time.monotonic() if ahora is None else ahora
        self._entradas[(clave, self._generacion)] = (ahora + self.ttl_seg, respuesta)
        while len(self._entradas) > self.capacidad:
            self._entradas.popitem(last=False)

    def vaciar(self) -> None:
        """Borra todo y obliga a re-leer la generación en la próxima consulta."""
        self._entradas.clear()
        self._generacion_vista_en = 0.0
