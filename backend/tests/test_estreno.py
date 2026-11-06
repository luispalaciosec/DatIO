# ruff: noqa: E501
"""Narrativa (hechos, redacción, validación de cifras), invitaciones, editor del reporte y envío mensual."""

from datetime import date

import httpx
import pytest

from api.main import crear_app
from api.narrativa.hechos import Hecho, Hechos, num, redactar_base, validar_cifras
from api.reportes import envio as envio_mod
from api.reportes.correo import html_invitacion, html_mensual
from api.reportes.envio import enviar_mensuales, enviar_reporte, limites, mes_anterior
from api.reportes.repositorio import RepositorioReportes
from tests.conftest import requiere_db, token_para


async def _instancia_de_prueba(pool, cliente_id: int) -> int:  # type: ignore[no-untyped-def]
    """Plantilla mínima (una página ga4 con título y KPIs) e instancia para el cliente."""
    plantilla = await pool.fetchval(
        "INSERT INTO reporte_plantillas (nombre) VALUES ($1) RETURNING id",
        f"estreno-{cliente_id}",
    )
    pagina = await pool.fetchval(
        "INSERT INTO reporte_paginas (plantilla_id, plataforma, slug, titulo, orden) VALUES ($1, 'ga4', 'metricas', 'Sitio web', 1) RETURNING id",
        plantilla,
    )
    await pool.execute(
        'INSERT INTO reporte_bloques (pagina_id, tipo, orden, ancho, config) VALUES ($1, \'titulo_seccion\', 10, 12, \'{"titulo": "KPIs"}\'), ($1, \'kpi_fila\', 20, 12, \'{"items": [{"metrica": "sesiones", "etiqueta": "Sesiones"}]}\')',
        pagina,
    )
    await pool.execute(
        "INSERT INTO reporte_instancias (cliente_id, plantilla_id, nombre_publico, slug_publico) VALUES ($1, $2, 'Prueba', $3)",
        cliente_id,
        plantilla,
        f"estreno-{cliente_id}",
    )
    return int(plantilla)


async def _borrar_instancia(pool, plantilla: int) -> None:  # type: ignore[no-untyped-def]
    await pool.execute("DELETE FROM reporte_instancias WHERE plantilla_id = $1", plantilla)
    await pool.execute("DELETE FROM reporte_plantillas WHERE id = $1", plantilla)


def _hechos() -> Hechos:
    h = Hechos("Instagram", date(2026, 10, 1), date(2026, 10, 31))
    h.kpis = [
        Hecho("alcance", "Alcance", 454934, 128400, 254.31),
        Hecho("interacciones", "Interacciones", 2102, 715, 193.99),
        Hecho("visitas_perfil", "Visitas al perfil", 900, 1000, -10.0),
        Hecho("seguidores", "Seguidores", 15140, None, None),
    ]
    h.mejor_dia = (date(2026, 10, 30), 129580, "Alcance")
    h.top_publicacion = {
        "tipo": "reel",
        "fecha": "2026-10-30",
        "valor": 218.0,
        "metrica": "interacciones",
        "texto": "x",
    }
    return h


def test_redaccion_por_reglas_solo_usa_cifras_de_los_hechos() -> None:
    h = _hechos()
    texto = redactar_base(h)
    assert "454.934" in texto and "254 % más" in texto and "30 de octubre" in texto
    assert "bajaron visitas al perfil (900, −10 %)" in texto
    assert "seguidores" not in texto.lower()  # sin delta no se narra como cambio
    assert validar_cifras(texto, h) == []
    assert redactar_base(Hechos("X", date(2026, 1, 1), date(2026, 1, 31))) == ""
    assert num(1234.5) == "1.234" and num(4.2) == "4,2" and num(12.34, "porcentaje") == "12,3 %"


def test_validador_rechaza_cifras_inventadas_por_el_llm() -> None:
    h = _hechos()
    bueno = "En octubre el alcance llegó a 454.934, un 254 % más. Las interacciones fueron 2.102."
    assert validar_cifras(bueno, h) == []
    inventado = "El alcance fue 454.934 y se proyecta llegar a 600.000 en noviembre, con 35 % de engagement."
    ajenas = validar_cifras(inventado, h)
    assert "600.000" in ajenas and "35" in ajenas and "454.934" not in ajenas


def test_correos_y_periodos() -> None:
    assert mes_anterior(date(2026, 11, 3)) == (date(2026, 10, 1), date(2026, 10, 31))
    assert mes_anterior(date(2027, 1, 1)) == (date(2026, 12, 1), date(2026, 12, 31))
    assert limites(date(2026, 2, 10)) == (date(2026, 2, 1), date(2026, 2, 28))
    inv = html_invitacion("Banco <X>", "https://d/banco", "#c8102e")
    assert (
        "Banco &lt;X&gt;" in inv and "https://d/banco" in inv and "No necesitas contraseña" in inv
    )
    men = html_mensual(
        "Banco",
        "octubre de 2026",
        "https://d/b",
        "#000",
        [{"titulo": "Instagram", "texto": "Subió."}, {"titulo": "Vacía", "texto": ""}],
    )
    assert "Reporte de octubre de 2026" in men and "Subió." in men and "Vacía" not in men


@requiere_db
async def test_invitar_editor_y_aislamiento(
    pool, cliente_a, cliente_b, usuario_equipo, config
) -> None:  # type: ignore[no-untyped-def]
    plantilla = await _instancia_de_prueba(pool, cliente_a.id)
    app = crear_app(config)
    equipo = {"Authorization": f"Bearer {token_para(usuario_equipo)}"}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            # Un usuario cliente no puede usar el admin
            r = await http.get(
                f"/admin/clientes/{cliente_b.id}/reporte",
                headers={"Authorization": f"Bearer {token_para(cliente_a.email)}"},
            )
            assert r.status_code == 403
            # Invitar: habilita al usuario; sin RESEND el correo no sale y se dice
            correo = f"nuevo-{cliente_a.id}@cliente-prueba.com"
            del_equipo = f"equipo-{cliente_a.id}@geeks-prueba.com"
            await pool.execute(
                "INSERT INTO usuarios (email, cliente_id, rol) VALUES ($1, NULL, 'equipo')",
                del_equipo,
            )
            r = await http.post(
                f"/admin/clientes/{cliente_a.id}/invitar",
                json={"emails": [correo, del_equipo]},
                headers=equipo,
            )
            assert r.status_code == 200
            por = {x["email"]: x for x in r.json()["resultados"]}
            assert por[correo]["estado"] in ("invitado", "habilitado_sin_correo")
            assert por[del_equipo]["estado"] == "omitido"  # nunca degrada a alguien del equipo
            fila = await pool.fetchrow(
                "SELECT rol, cliente_id, invitado_en FROM usuarios WHERE email = $1", correo
            )
            assert (
                fila["rol"] == "cliente"
                and fila["cliente_id"] == cliente_a.id
                and fila["invitado_en"] is not None
            )
            assert (
                await pool.fetchval("SELECT rol FROM usuarios WHERE email = $1", del_equipo)
                == "equipo"
            )

            # Editor: estructura, ocultar un bloque, texto propio, campo no editable
            r = await http.get(f"/admin/clientes/{cliente_a.id}/reporte", headers=equipo)
            assert r.status_code == 200
            est = r.json()
            bloque = next(
                b for p in est["paginas"] for b in p["bloques"] if b["tipo"] == "titulo_seccion"
            )
            r = await http.put(
                f"/admin/clientes/{cliente_a.id}/reporte/bloques/{bloque['id']}",
                json={"oculto": False, "config": {"titulo": "Título del cliente"}},
                headers=equipo,
            )
            assert r.status_code == 200
            r = await http.put(
                f"/admin/clientes/{cliente_a.id}/reporte/bloques/{bloque['id']}",
                json={"oculto": False, "config": {"metrica": "inversion"}},
                headers=equipo,
            )
            assert r.status_code == 400  # solo la lista blanca
            est2 = (
                await http.get(f"/admin/clientes/{cliente_a.id}/reporte", headers=equipo)
            ).json()
            b2 = next(b for p in est2["paginas"] for b in p["bloques"] if b["id"] == bloque["id"])
            assert b2["override"] == {"titulo": "Título del cliente"}
            # El override no toca a otro cliente
            assert (
                await pool.fetchval(
                    "SELECT count(*) FROM reporte_overrides WHERE bloque_id = $1", bloque["id"]
                )
                == 1
            )
            await pool.execute(
                "DELETE FROM reporte_overrides WHERE instancia_id = $1", est["instancia_id"]
            )
    await pool.execute("DELETE FROM usuarios WHERE email = $1", correo)
    await pool.execute("DELETE FROM usuarios WHERE email = $1", del_equipo)
    await _borrar_instancia(pool, plantilla)


@requiere_db
async def test_envio_mensual_idempotente(
    pool, cliente_a, config, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    plantilla = await _instancia_de_prueba(pool, cliente_a.id)
    repo = RepositorioReportes(pool)
    inst = await repo.instancia_de_cliente(cliente_a.id)
    assert inst is not None
    enviados: list[tuple[list[str], str, bool]] = []

    async def pdf_falso(url: str, timeout_ms: int = 0) -> bytes:
        return b"%PDF-1.4 falso"

    async def enviar_falso(cfg, para, asunto, html, adjunto=None):  # type: ignore[no-untyped-def]
        enviados.append((para, asunto, adjunto is not None))
        return True, None

    monkeypatch.setattr(envio_mod.render, "generar_pdf", pdf_falso)
    monkeypatch.setattr(envio_mod, "enviar", enviar_falso)
    cfg = config.model_copy(
        update={"resend_api_key": "re_test", "pdf_secret": "x" * 32, "llm_modelos": {}}
    )
    correo = f"gerente-{cliente_a.id}@cliente-prueba.com"

    # Sin usuarios cliente el cron no envía ni registra error
    await pool.execute("UPDATE usuarios SET activo = FALSE WHERE cliente_id = $1", cliente_a.id)
    sin = await enviar_reporte(pool, cfg, cliente_a.id, date(2026, 10, 1), automatico=True)
    assert sin.estado == "sin_destinatarios"
    await repo.invitar(cliente_a.id, correo)
    r = await enviar_reporte(pool, cfg, cliente_a.id, date(2026, 10, 1), automatico=True)
    assert r.estado == "enviado" and r.destinatarios == [correo]
    assert enviados[-1][2] is True and "Reporte de octubre de 2026" in enviados[-1][1]
    # Segunda corrida del cron el mismo mes: no reenvía
    assert (
        await enviar_reporte(pool, cfg, cliente_a.id, date(2026, 10, 1), automatico=True)
    ).estado == "ya_enviado"
    # Fuera de los primeros días del mes el cron no hace nada
    assert await enviar_mensuales(pool, cfg, date(2026, 11, 20)) == []
    # Manual a otro correo: siempre sale
    r2 = await enviar_reporte(
        pool, cfg, cliente_a.id, date(2026, 10, 1), ["yo@geeks-prueba.com"], automatico=False
    )
    assert r2.estado == "enviado" and len(enviados) == 2
    await pool.execute("DELETE FROM envios_reporte WHERE instancia_id = $1", inst["id"])
    await pool.execute("DELETE FROM usuarios WHERE email = $1", correo)
    await pool.execute("DELETE FROM narrativas WHERE cliente_id = $1", cliente_a.id)
    await _borrar_instancia(pool, plantilla)
