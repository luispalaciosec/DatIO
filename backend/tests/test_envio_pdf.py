"""B-4: el envío mensual y el PDF bajo demanda nunca entregan una pantalla de error."""

import logging
from datetime import date

import pytest

from api.pdf import render
from api.pdf.render import (
    TAMANO_MINIMO_PDF,
    EstadoImpresion,
    PdfInvalidoError,
    decidir_impresion,
    sin_token,
    validar_pdf,
)
from api.reportes import envio as envio_mod
from api.reportes.envio import enviar_reporte
from api.reportes.repositorio import RepositorioReportes
from tests.conftest import pdf_valido, requiere_db
from tests.test_estreno import _borrar_instancia, _instancia_de_prueba

LISTO = EstadoImpresion(lista=True, error=False, bloques_con_error=0, cargando=0, hojas=3)


# ---- decisión sobre el DOM de la vista de impresión (sin Chromium) ------------------------


def test_decidir_impresion_acepta_reporte_completo() -> None:
    assert decidir_impresion(LISTO) == 3


@pytest.mark.parametrize(
    "estado",
    [
        # la vista de impresión marcó error al cargar el reporte
        EstadoImpresion(lista=False, error=True, bloques_con_error=0, cargando=0, hojas=0),
        # aunque esté "lista", un error explícito manda
        EstadoImpresion(lista=True, error=True, bloques_con_error=0, cargando=0, hojas=3),
        # un bloque individual falló
        EstadoImpresion(lista=True, error=False, bloques_con_error=1, cargando=0, hojas=3),
        # quedó algo cargando
        EstadoImpresion(lista=True, error=False, bloques_con_error=0, cargando=2, hojas=3),
        # nunca se marcó lista
        EstadoImpresion(lista=False, error=False, bloques_con_error=0, cargando=0, hojas=3),
        # sin hojas con datos
        EstadoImpresion(lista=True, error=False, bloques_con_error=0, cargando=0, hojas=0),
    ],
)
def test_decidir_impresion_rechaza_errores(estado: EstadoImpresion) -> None:
    with pytest.raises(PdfInvalidoError):
        decidir_impresion(estado)


# ---- validación del archivo ---------------------------------------------------------------


@pytest.mark.parametrize(
    "contenido",
    [
        b"",
        b"<html>no es pdf</html>",
        b"%PDF-1.4" + b" " * 10,
        b"%PDF-1.7" + b"x" * TAMANO_MINIMO_PDF,
    ],
)
def test_validar_pdf_rechaza_vacio_ajeno_chico_o_danado(contenido: bytes) -> None:
    with pytest.raises(PdfInvalidoError):
        validar_pdf(contenido, 1)


def test_validar_pdf_exige_las_hojas_del_reporte() -> None:
    validar_pdf(pdf_valido(3), 3)
    with pytest.raises(PdfInvalidoError, match="1 página"):
        validar_pdf(pdf_valido(1), 3)


def test_motivo_y_logs_sin_token() -> None:
    assert sin_token("timeout abriendo https://x/imprimir?render=abc.def", "abc.def") == (
        "timeout abriendo https://x/imprimir?render=[token]"
    )
    assert "render" not in PdfInvalidoError("el reporte no terminó de cargar").motivo


# ---- envío mensual ------------------------------------------------------------------------


@pytest.fixture
async def envio_preparado(pool, cliente_a, config, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    plantilla = await _instancia_de_prueba(pool, cliente_a.id)
    repo = RepositorioReportes(pool)
    inst = await repo.instancia_de_cliente(cliente_a.id)
    assert inst is not None
    correo = f"gerente-{cliente_a.id}@cliente-prueba.com"
    await repo.invitar(cliente_a.id, correo)
    enviados: list[dict[str, object]] = []

    async def enviar_falso(cfg, para, asunto, html, adjunto=None):  # type: ignore[no-untyped-def]
        enviados.append({"para": list(para), "asunto": asunto, "adjunto": adjunto})
        return True, None

    async def equipo_falso(self):  # type: ignore[no-untyped-def]
        return ["equipo@geeks-prueba.com"]

    monkeypatch.setattr(envio_mod, "enviar", enviar_falso)
    monkeypatch.setattr(envio_mod.RepositorioAlertas, "correos_equipo", equipo_falso)
    cfg = config.model_copy(
        update={"resend_api_key": "re_test", "pdf_secret": "x" * 32, "llm_modelos": {}}
    )
    yield cfg, repo, inst, correo, enviados
    await pool.execute("DELETE FROM envios_reporte WHERE instancia_id = $1", inst["id"])
    await pool.execute("DELETE FROM usuarios WHERE email = $1", correo)
    await pool.execute("DELETE FROM narrativas WHERE cliente_id = $1", cliente_a.id)
    await _borrar_instancia(pool, plantilla)


async def _render_fallido(url: str, timeout_ms: int = 0) -> bytes:
    raise PdfInvalidoError("la vista de impresión no pudo cargar el reporte")


async def _render_basura(url: str, timeout_ms: int = 0) -> bytes:
    return b"%PDF-1.4 truncado"


@requiere_db
@pytest.mark.parametrize("render_falso", [_render_fallido, _render_basura])
async def test_pdf_invalido_no_llega_al_cliente(
    pool, cliente_a, envio_preparado, monkeypatch: pytest.MonkeyPatch, render_falso
) -> None:  # type: ignore[no-untyped-def]
    cfg, repo, inst, correo, enviados = envio_preparado
    monkeypatch.setattr(envio_mod.render, "generar_pdf", render_falso)

    r = await enviar_reporte(pool, cfg, cliente_a.id, date(2026, 10, 1), automatico=True)

    assert r.estado == "pdf_invalido" and r.error
    # Ningún correo al cliente; un único aviso al equipo, sin adjunto
    assert all(correo not in e["para"] for e in enviados)
    assert len(enviados) == 1 and enviados[0]["para"] == ["equipo@geeks-prueba.com"]
    assert enviados[0]["adjunto"] is None and "No se envió" in str(enviados[0]["asunto"])
    fila = await pool.fetchrow(
        "SELECT estado, error FROM envios_reporte WHERE instancia_id = $1", inst["id"]
    )
    assert fila["estado"] == "pdf_invalido"
    # No cuenta como enviado: el cron lo reintenta al día siguiente
    assert await repo.ya_enviado(inst["id"], date(2026, 10, 1)) is False


@requiere_db
async def test_falla_interna_registra_motivo_sin_token(
    pool, cliente_a, envio_preparado, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:  # type: ignore[no-untyped-def]
    cfg, repo, inst, correo, enviados = envio_preparado
    vistas: list[str] = []

    async def explota(url: str, timeout_ms: int = 0) -> bytes:
        vistas.append(url)
        raise RuntimeError(f"navegador caído abriendo {url}")

    monkeypatch.setattr(envio_mod.render, "generar_pdf", explota)
    with caplog.at_level(logging.ERROR):
        r = await enviar_reporte(pool, cfg, cliente_a.id, date(2026, 10, 1), automatico=True)

    token = vistas[0].split("render=")[1]
    assert r.estado == "error" and token not in (r.error or "")
    assert token not in caplog.text and "[token]" in caplog.text
    assert all(correo not in e["para"] for e in enviados)


@requiere_db
async def test_caso_feliz_un_solo_envio_al_cliente(
    pool, cliente_a, envio_preparado, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    cfg, repo, inst, correo, enviados = envio_preparado

    async def bien(url: str, timeout_ms: int = 0) -> bytes:
        return pdf_valido(2)

    monkeypatch.setattr(envio_mod.render, "generar_pdf", bien)
    r = await enviar_reporte(pool, cfg, cliente_a.id, date(2026, 10, 1), automatico=True)
    assert r.estado == "enviado"
    assert len(enviados) == 1 and correo in enviados[0]["para"] and enviados[0]["adjunto"]
    assert await repo.ya_enviado(inst["id"], date(2026, 10, 1)) is True


@requiere_db
async def test_envio_manual_fallido_no_avisa_al_equipo_y_responde_motivo(
    pool, cliente_a, envio_preparado, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    cfg, repo, inst, correo, enviados = envio_preparado
    monkeypatch.setattr(envio_mod.render, "generar_pdf", _render_fallido)
    r = await enviar_reporte(
        pool, cfg, cliente_a.id, date(2026, 10, 1), ["yo@geeks-prueba.com"], automatico=False
    )
    assert r.estado == "pdf_invalido"
    assert r.error == "la vista de impresión no pudo cargar el reporte"
    assert enviados == []  # quien lo pidió ve el motivo en la respuesta (502)


def test_render_expone_lo_necesario() -> None:
    assert callable(render.generar_pdf) and callable(render.validar_pdf)
