"""TikTok nativo (Login Kit + Display API): OAuth, renovación del token y normalización con
payloads fijos, sin tocar la red real."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from api.admin import conectar
from api.etl.conectores import tiktok as tk
from api.etl.conectores.tiktok import ConectorTikTok, ConectorTikTokPublicaciones, TikTokError
from api.etl.repositorio import Cuenta
from tests.semilla import mapeos_del_seed

F = Path(__file__).parent / "fixtures"


def _con(clase, config, repo=None):  # type: ignore[no-untyped-def]
    return clase(
        Cuenta(1, 1, "tiktok", "-000abcOPENID", None), repo, mapeos_del_seed()["tiktok"], config
    )


# ---- OAuth -----------------------------------------------------------------------------


def test_url_inicio_pide_solo_permisos_de_lectura(config) -> None:  # type: ignore[no-untyped-def]
    cfg = config.model_copy(update={"tiktok_client_key": "clave-app", "api_url": "https://api.x"})
    url = conectar.url_inicio(cfg, "tiktok", "estado-1")
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://www.tiktok.com/v2/auth/authorize/")
    assert q["client_key"] == ["clave-app"] and q["state"] == ["estado-1"]
    assert q["redirect_uri"] == ["https://api.x/admin/conectar/tiktok/retorno"]
    assert q["scope"] == ["user.info.basic,user.info.profile,user.info.stats,video.list"]
    assert "publish" not in url and "upload" not in url


def test_url_inicio_sin_clave_avisa(config) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(conectar.ConexionError, match="TIKTOK_CLIENT_KEY"):
        conectar.url_inicio(config.model_copy(update={"tiktok_client_key": ""}), "tiktok", "e")


def test_credencial_y_vencimiento() -> None:
    token = {
        "access_token": "act.1",
        "refresh_token": "rft.1",
        "expires_in": 86400,
        "refresh_expires_in": 31536000,
        "open_id": "-000abcOPENID",
        "scope": "user.info.basic,video.list",
    }
    cred = json.loads(conectar.credencial_para_guardar("tiktok", token))
    assert cred["access_token"] == "act.1" and cred["refresh_token"] == "rft.1"
    assert datetime.fromisoformat(cred["access_expira_en"]) > datetime.now(UTC) + timedelta(
        hours=23
    )
    vence = conectar.expiracion("tiktok", token)
    assert vence is not None and vence > datetime.now(UTC) + timedelta(days=360)
    with pytest.raises(conectar.ConexionError, match="refresh_token"):
        conectar.credencial_para_guardar("tiktok", {"access_token": "a"})


async def test_activos_tiktok_es_la_cuenta_que_inicio_sesion(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    cuerpo = json.loads((F / "tiktok_user.json").read_text())
    transporte = httpx.MockTransport(lambda req: httpx.Response(200, json=cuerpo))
    original = httpx.AsyncClient
    monkeypatch.setattr(conectar.httpx, "AsyncClient", lambda **kw: original(transport=transporte))
    activos = await conectar._activos_tiktok("act.1")
    assert [(a.plataforma, a.id_externo, a.nombre) for a in activos] == [
        ("tiktok", "-000abcOPENID", "@bancoprueba.ec · Banco de Prueba")
    ]


# ---- normalización -----------------------------------------------------------------------


def test_cuenta_guarda_la_foto_del_dia(config) -> None:  # type: ignore[no-untyped-def]
    c = _con(ConectorTikTok, config)
    usuario = json.loads((F / "tiktok_user.json").read_text())["data"]["user"]
    filas = {
        (f, m): v
        for f, m, v in c.normalizar([{"tipo": "cuenta", "fecha": "2026-11-18", "user": usuario}])
    }
    assert filas == {
        (date(2026, 11, 18), "seguidores"): Decimal(12840),
        (date(2026, 11, 18), "me_gusta_totales"): Decimal(98321),
        (date(2026, 11, 18), "publicaciones_totales"): Decimal(214),
    }
    assert not c.metricas_sin_mapeo


def test_publicaciones_con_metricas_y_ventana(config) -> None:  # type: ignore[no-untyped-def]
    c = _con(ConectorTikTokPublicaciones, config)
    videos = json.loads((F / "tiktok_videos.json").read_text())["data"]["videos"]
    pubs = c.normalizar_publicaciones([{"tipo": "videos", "videos": videos, "desde": "2026-10-21"}])
    assert [p.id_externo for p in pubs] == [
        "7310000000000000001",
        "7310000000000000002",
    ]  # el viejo no
    p1 = pubs[0]
    assert p1.tipo == "video" and p1.caption == "Ahorra con tu tarjeta"
    assert p1.publicado_en == datetime(2026, 11, 10, tzinfo=UTC)
    assert p1.metricas == {
        "reproducciones_video": Decimal(15400),
        "me_gusta": Decimal(320),
        "comentarios": Decimal(12),
        "compartidos": Decimal(9),
        "interacciones": Decimal(341),
    }
    assert pubs[1].caption == "Detrás de cámaras"  # sin título usa la descripción
    assert not c.metricas_sin_mapeo


# ---- renovación del token ----------------------------------------------------------------


class RepoCred:
    def __init__(self, cred: dict[str, Any] | None) -> None:
        self.cred = json.dumps(cred) if cred else None
        self.guardadas: list[dict[str, Any]] = []

    async def credencial(self, cuenta_id: int, clave: str) -> str | None:
        return self.cred

    async def guardar_credencial(self, cuenta_id: int, credencial: str, clave: str) -> None:
        self.guardadas.append(json.loads(credencial))
        self.cred = credencial


def _cfg(config):  # type: ignore[no-untyped-def]
    return config.model_copy(
        update={"clave_cifrado": "x", "tiktok_client_key": "ck", "tiktok_client_secret": "cs"}
    )


async def test_token_vigente_no_se_renueva(config) -> None:  # type: ignore[no-untyped-def]
    vigente = (datetime.now(UTC) + timedelta(hours=5)).isoformat()
    repo = RepoCred(
        {"access_token": "act.1", "refresh_token": "rft.1", "access_expira_en": vigente}
    )
    llamadas: list[httpx.Request] = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: llamadas.append(r) or httpx.Response(500))
    ) as http:
        assert await _con(ConectorTikTok, _cfg(config), repo)._token(http) == "act.1"
    assert llamadas == [] and repo.guardadas == []


async def test_token_vencido_se_renueva_y_guarda_el_refresh_rotado(config) -> None:  # type: ignore[no-untyped-def]
    vencido = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    repo = RepoCred(
        {
            "access_token": "act.1",
            "refresh_token": "rft.1",
            "access_expira_en": vencido,
            "open_id": "o",
        }
    )
    pedidos: list[dict[str, list[str]]] = []

    def responder(req: httpx.Request) -> httpx.Response:
        pedidos.append(parse_qs(req.content.decode()))
        return httpx.Response(
            200, json={"access_token": "act.2", "refresh_token": "rft.2", "expires_in": 86400}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as http:
        assert await _con(ConectorTikTok, _cfg(config), repo)._token(http) == "act.2"
    assert pedidos[0]["grant_type"] == ["refresh_token"] and pedidos[0]["refresh_token"] == [
        "rft.1"
    ]
    assert repo.guardadas[-1]["refresh_token"] == "rft.2" and repo.guardadas[-1]["open_id"] == "o"


async def test_sin_token_o_renovacion_rechazada_falla_claro(config) -> None:  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(400, json={"error": "invalid_grant"})
        )
    ) as http:
        with pytest.raises(TikTokError, match="no tiene token"):
            await _con(ConectorTikTok, _cfg(config), RepoCred(None))._token(http)
        vencido = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        repo = RepoCred({"access_token": "a", "refresh_token": "r", "access_expira_en": vencido})
        with pytest.raises(TikTokError, match="reconecta"):
            await _con(ConectorTikTok, _cfg(config), repo)._token(http)


def test_error_de_api_se_detecta() -> None:
    r = httpx.Response(
        200, json={"data": {}, "error": {"code": "scope_not_authorized", "message": "x"}}
    )
    with pytest.raises(TikTokError, match="scope_not_authorized"):
        tk._verificar(r, "user/info")
