"""PT-16: disparadores del puente CRM y adaptadores, sin tocar la red ni el CRM real."""

from datetime import date, timedelta
from typing import Any

import httpx
import pytest

from api.config import Configuracion
from api.puente import crm as crm_mod
from api.puente.crm import Accion, CrmError, CrmHubspot, CrmPrometio, ResultadoCrm
from api.puente.disparadores import correr_puente, evaluar_cliente


class RepoFalso:
    """Simula RepositorioPuente con datos en memoria."""

    def __init__(
        self,
        serie: dict[date, float],
        gasto: float | None,
        engagement: float | None,
        anuncios: list[dict[str, Any]] | None = None,
    ) -> None:
        self._serie = serie
        self._gasto = gasto
        self._engagement = engagement
        self._anuncios = anuncios or []
        self.disparos: list[tuple[Any, ...]] = []
        self.alertas: list[str] = []
        self.recientes: set[str] = set()

    async def clientes_con_crm(self, cliente_id: int | None = None) -> list[dict[str, Any]]:
        return [
            {
                "id": 1,
                "nombre": "Banco X",
                "slug": "banco-x",
                "sector": "banca",
                "crm_proveedor": "prometio",
                "crm_empresa_ref": "emp-1",
                "crm_contacto_ref": "con-1",
                "crm_config": {},
            }
        ]

    async def credencial_crm(self, cliente_id: int, clave: str) -> str | None:
        return None

    async def cuentas(self, cliente_id: int) -> list[dict[str, Any]]:
        return [{"id": 10, "plataforma": "meta_ig", "nombre_cuenta": "@bancox"}]

    async def serie(
        self, cuenta_id: int, metrica: str, desde: date, hasta: date
    ) -> dict[date, float]:
        return {f: v for f, v in self._serie.items() if desde <= f <= hasta}

    async def agregacion(self, metrica: str) -> str:
        return "suma"

    async def gasto_ads(self, cliente_id: int, dias: int) -> float | None:
        return self._gasto

    async def engagement_propio(self, cliente_id: int, n: int = 12) -> float | None:
        return self._engagement

    async def anuncios_nuevos_competencia(self, cliente_id: int, dias: int) -> list[dict[str, Any]]:
        return self._anuncios

    async def disparo_reciente(self, cliente_id: int, codigo: str, dias: int) -> bool:
        return codigo in self.recientes

    async def registrar_disparo(self, *args: Any) -> int:
        self.disparos.append(args)
        return len(self.disparos)

    async def crear_alerta(
        self, cuenta_id: int | None, titulo: str, detalle: dict[str, Any]
    ) -> None:
        self.alertas.append(titulo)


HOY = date(2026, 9, 20)


def serie_lineal(dias: int, nivel: float, desde_hace: int = 0) -> dict[date, float]:
    return {HOY - timedelta(days=desde_hace + i): nivel for i in range(1, dias + 1)}


async def test_bajo_meta_dispara_cuando_el_mes_va_muy_abajo() -> None:
    # Agosto a 1.000/día (31 días), septiembre a 300/día: proyección ≈ 9.000 vs 31.000 → < 60 %
    serie = {date(2026, 8, d): 1000.0 for d in range(1, 32)}
    serie.update({date(2026, 9, d): 300.0 for d in range(1, 20)})
    repo = RepoFalso(serie, gasto=1000.0, engagement=0.3)
    disparos = await evaluar_cliente(repo, (await repo.clientes_con_crm())[0], HOY)  # type: ignore[arg-type]
    codigos = [d.accion.codigo for d in disparos]
    assert "bajo_meta" in codigos
    d = next(x for x in disparos if x.accion.codigo == "bajo_meta")
    assert d.accion.tipo == "oportunidad" and d.accion.valor == 500.0  # 50 % del gasto de 28 días
    assert "Instagram" in d.accion.evidencia and "USD 1.000" in d.accion.evidencia
    assert "organico_sin_pauta" not in codigos  # engagement bajo y hay pauta


async def test_no_dispara_con_mes_normal_ni_pocos_dias() -> None:
    serie = {date(2026, 8, d): 1000.0 for d in range(1, 32)}
    serie.update({date(2026, 9, d): 950.0 for d in range(1, 20)})
    repo = RepoFalso(serie, gasto=0.0, engagement=None)
    assert await evaluar_cliente(repo, (await repo.clientes_con_crm())[0], HOY) == []  # type: ignore[arg-type]
    # Con 5 días de mes no se proyecta aunque vaya mal
    corto = {date(2026, 8, d): 1000.0 for d in range(1, 32)}
    corto.update({date(2026, 9, d): 100.0 for d in range(1, 6)})
    repo2 = RepoFalso(corto, gasto=0.0, engagement=None)
    assert await evaluar_cliente(repo2, (await repo2.clientes_con_crm())[0], date(2026, 9, 6)) == []  # type: ignore[arg-type]


async def test_competencia_organico_y_caida_sostenida() -> None:
    # Tres ventanas de 28 días cayendo 20 % cada una
    serie: dict[date, float] = {}
    for k, nivel in enumerate((640.0, 800.0, 1000.0)):
        for i in range(28):
            serie[HOY - timedelta(days=1 + 28 * k + i)] = nivel
    repo = RepoFalso(
        serie,
        gasto=None,
        engagement=1.8,
        anuncios=[
            {"competidor_id": 7, "nombre": "Rival", "nuevos": 4, "activos_total": 30},
            {"competidor_id": 8, "nombre": "Otro", "nuevos": 1, "activos_total": 3},
        ],
    )
    disparos = await evaluar_cliente(repo, (await repo.clientes_con_crm())[0], HOY)  # type: ignore[arg-type]
    codigos = {d.accion.codigo for d in disparos}
    assert "caida_sostenida" in codigos and "competencia_pauta:7" in codigos
    assert "competencia_pauta:8" not in codigos and "organico_sin_pauta" in codigos
    org = next(d for d in disparos if d.accion.codigo == "organico_sin_pauta")
    assert "no hay cuenta de pauta" in org.accion.evidencia and "1.80 %" in org.accion.evidencia


class CrmFalso:
    proveedor = "prometio"

    def __init__(self) -> None:
        self.ejecutadas: list[Accion] = []
        self.fallar = False

    async def ejecutar(
        self, accion: Accion, empresa_ref: str, contacto_ref: str | None
    ) -> ResultadoCrm:
        if self.fallar:
            raise CrmError("CRM caído")
        self.ejecutadas.append(accion)
        return ResultadoCrm("op-1", "https://crm/op-1")


async def test_correr_puente_dedupe_y_errores(monkeypatch: pytest.MonkeyPatch) -> None:
    serie = {date(2026, 8, d): 1000.0 for d in range(1, 32)}
    serie.update({date(2026, 9, d): 300.0 for d in range(1, 20)})
    repo = RepoFalso(serie, gasto=1000.0, engagement=None)
    falso = CrmFalso()
    import api.puente.disparadores as mod

    monkeypatch.setattr(mod, "adaptador", lambda *a, **k: falso)
    cfg = Configuracion(clave_cifrado="")  # type: ignore[call-arg]

    simulado = await correr_puente(repo, cfg, HOY, simular=True)  # type: ignore[arg-type]
    assert [d.accion.codigo for d in simulado.disparos] == ["bajo_meta"] and repo.disparos == []

    real = await correr_puente(repo, cfg, HOY)  # type: ignore[arg-type]
    assert real.disparos[0].objeto_ref == "op-1" and len(falso.ejecutadas) == 1
    assert len(repo.disparos) == 1 and repo.alertas[0].startswith("✓ CRM")

    repo.recientes.add("bajo_meta")  # ventana de 30 días: no se repite
    otra = await correr_puente(repo, cfg, HOY)  # type: ignore[arg-type]
    assert otra.disparos == [] and len(falso.ejecutadas) == 1

    repo.recientes.clear()
    falso.fallar = True
    fallida = await correr_puente(repo, cfg, HOY)  # type: ignore[arg-type]
    assert fallida.disparos[0].error == "CRM caído" and repo.alertas[-1].startswith("✗ CRM")


def _transporte(
    respuestas: dict[str, tuple[int, Any]], vistas: list[httpx.Request]
) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        vistas.append(req)
        for clave, (estado, cuerpo) in respuestas.items():
            if clave in str(req.url):
                return httpx.Response(estado, json=cuerpo)
        return httpx.Response(404, json={"detail": "sin ruta"})

    return httpx.MockTransport(handler)


async def test_adaptador_prometio_login_oportunidad_y_actividad(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vistas: list[httpx.Request] = []
    transporte = _transporte(
        {
            "/auth/v1/token": (200, {"access_token": "jwt-1", "expires_in": 3600}),
            "/oportunidades": (201, {"id": "op-uuid"}),
            "/actividades": (201, {"id": "act-uuid"}),
        },
        vistas,
    )
    original = httpx.AsyncClient
    monkeypatch.setattr(
        crm_mod.httpx, "AsyncClient", lambda *a, **k: original(transport=transporte, **k)
    )
    cfg = Configuracion(  # type: ignore[call-arg]
        prometio_url="https://crm.test",
        prometio_supabase_url="https://sb.test",
        prometio_supabase_anon_key="anon",
        prometio_email="datio@geeks.test",
        prometio_password="x",
        prometio_frontend_url="https://app.crm.test",
    )
    crm = CrmPrometio(cfg)
    r = await crm.ejecutar(
        Accion("bajo_meta", "oportunidad", "Refuerzo", "evidencia", valor=500.0), "emp-1", "con-1"
    )
    assert r.objeto_ref == "op-uuid" and r.url == "https://app.crm.test/oportunidades/op-uuid"
    rutas = [str(v.url.path) for v in vistas]
    assert rutas == ["/auth/v1/token", "/oportunidades", "/actividades"]
    assert vistas[1].headers["authorization"] == "Bearer jwt-1"
    import json

    cuerpo = json.loads(vistas[1].content)
    assert cuerpo == {"contacto_id": "con-1", "empresa_id": "emp-1", "valor_referencial": 500.0}
    actividad = json.loads(vistas[2].content)
    assert actividad["tipo"] == "tarea_interna" and actividad["oportunidad_id"] == "op-uuid"
    # Segunda llamada reutiliza el JWT (no vuelve a /auth)
    await crm.ejecutar(Accion("x", "tarea", "T", "e"), "emp-1", "con-1")
    assert [str(v.url.path) for v in vistas].count("/auth/v1/token") == 1
    with pytest.raises(CrmError):
        await crm.ejecutar(Accion("x", "oportunidad", "T", "e"), "emp-1", None)


async def test_adaptador_hubspot_deal_y_task(monkeypatch: pytest.MonkeyPatch) -> None:
    vistas: list[httpx.Request] = []
    transporte = _transporte(
        {"/objects/deals": (201, {"id": "123"}), "/objects/tasks": (201, {"id": "456"})}, vistas
    )
    original = httpx.AsyncClient
    monkeypatch.setattr(
        crm_mod.httpx, "AsyncClient", lambda *a, **k: original(transport=transporte, **k)
    )
    crm = CrmHubspot("tok", {"dealstage": "qualifiedtobuy", "portal_id": "99"})
    r = await crm.ejecutar(
        Accion("bajo_meta", "oportunidad", "Refuerzo", "ev", valor=750.0), "c-1", None
    )
    assert r.objeto_ref == "123" and r.url == "https://app.hubspot.com/contacts/99/deal/123"
    import json

    deal = json.loads(vistas[0].content)
    assert (
        deal["properties"]["amount"] == "750.0"
        and deal["properties"]["dealstage"] == "qualifiedtobuy"
    )
    assert deal["associations"][0]["to"] == {"id": "c-1"}
    t = await crm.ejecutar(
        Accion("caida_sostenida", "tarea", "Riesgo", "ev", prioridad="alta"), "c-1", None
    )
    assert t.objeto_ref == "456"
    tarea = json.loads(vistas[1].content)
    assert tarea["properties"]["hs_task_priority"] == "HIGH"
    # Token rechazado → CrmError con el detalle de HubSpot
    vistas.clear()
    rechazo = _transporte({"/objects/deals": (401, {"message": "token inválido"})}, vistas)
    monkeypatch.setattr(
        crm_mod.httpx, "AsyncClient", lambda *a, **k: original(transport=rechazo, **k)
    )
    with pytest.raises(CrmError, match="401"):
        await CrmHubspot("malo").ejecutar(Accion("x", "oportunidad", "T", "e"), "c-1", None)
