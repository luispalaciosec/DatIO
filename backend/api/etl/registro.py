"""Registro de conectores: plataforma → clase. El runner despacha por aquí."""

from api.etl.conector_base import ConectorBase

REGISTRO: dict[str, type[ConectorBase]] = {}


def registrar(cls: type[ConectorBase]) -> type[ConectorBase]:
    """Decorador. Registra el conector para la plataforma que declara."""
    REGISTRO[cls.plataforma] = cls
    return cls
