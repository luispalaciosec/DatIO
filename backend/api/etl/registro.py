"""Registro de conectores: plataforma → clase. El runner despacha por aquí."""

from api.etl.conector_base import ConectorBase

REGISTRO: dict[str, type[ConectorBase]] = {}


def registrar(cls: type[ConectorBase]) -> type[ConectorBase]:
    """Decorador. Registra el conector para la plataforma que declara."""
    REGISTRO[cls.plataforma] = cls
    return cls


# Conectores de publicaciones (métricas por post), también por plataforma.
REGISTRO_PUBLICACIONES: dict[str, type[ConectorBase]] = {}


def registrar_publicaciones(cls: type[ConectorBase]) -> type[ConectorBase]:
    REGISTRO_PUBLICACIONES[cls.plataforma] = cls
    return cls
