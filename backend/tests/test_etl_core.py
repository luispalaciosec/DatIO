"""PT-03: ConectorDemo de punta a punta, idempotencia, raw antes de normalizar, errores."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from api.etl.conector_base import ConectorBase, Fila
from api.etl.conectores.demo import ConectorDemo
from tests.conftest import requiere_db

HASTA = date(2026, 9, 1)


class ConectorQueFalla(ConectorDemo):
    codigo = "falla"

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        raise ConnectionError("API caída")


class ConectorSinMapeo(ConectorDemo):
    codigo = "sin_mapeo"

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        return [{"fecha": hasta.isoformat(), "metricas": {"sessions": 5, "metricaInventada": 9}}]


@requiere_db
async def test_demo_escribe_28_dias_en_fct_metrica_diaria(repo, cliente_a, config) -> None:  # type: ignore[no-untyped-def]
    mapeo = await repo.mapeo_plataforma("ga4")
    conector = ConectorDemo(cliente_a.cuenta, repo, mapeo, config)
    resultado = await conector.correr(hasta=HASTA)

    dias = config.ventana_resync_dias + 1  # ventana inclusiva: hasta − 28 … hasta
    assert resultado.desde == HASTA - timedelta(days=28)
    assert resultado.estado == "ok"
    assert resultado.filas_escritas == dias * len(ConectorDemo.METRICAS_NATIVAS)

    filas = await repo.metricas_actuales(cliente_a.cuenta.id, resultado.desde, HASTA)
    assert len(filas) == resultado.filas_escritas
    codigos = {f["metrica_codigo"] for f in filas}
    assert codigos == {"sesiones", "usuarios_activos", "tasa_rebote"}
    rebote = next(f for f in filas if f["metrica_codigo"] == "tasa_rebote")
    assert 30 <= rebote["valor"] <= 40  # 0.3x × 100 → porcentaje

    job = await repo.job(resultado.job_id)
    assert job is not None and job["estado"] == "ok" and job["finalizado_en"] is not None
    assert await repo.contar_raw(cliente_a.cuenta.id) == 1


@requiere_db
async def test_correr_dos_veces_es_idempotente(repo, cliente_a, config) -> None:  # type: ignore[no-untyped-def]
    mapeo = await repo.mapeo_plataforma("ga4")
    conector = ConectorDemo(cliente_a.cuenta, repo, mapeo, config)
    r1 = await conector.correr(hasta=HASTA)
    estado_1 = await repo.metricas_actuales(cliente_a.cuenta.id, r1.desde, HASTA)
    r2 = await conector.correr(hasta=HASTA)
    estado_2 = await repo.metricas_actuales(cliente_a.cuenta.id, r2.desde, HASTA)

    assert estado_1 == estado_2
    assert await repo.contar_metricas(cliente_a.cuenta.id) == r1.filas_escritas
    assert await repo.contar_raw(cliente_a.cuenta.id) == 2  # el raw es append-only


@requiere_db
async def test_error_en_extraer_cierra_job_en_error_y_no_escribe(repo, cliente_a, config) -> None:  # type: ignore[no-untyped-def]
    conector = ConectorQueFalla(cliente_a.cuenta, repo, {}, config)
    with pytest.raises(ConnectionError):
        await conector.correr(hasta=HASTA)
    assert await repo.contar_raw(cliente_a.cuenta.id) == 0
    assert await repo.contar_metricas(cliente_a.cuenta.id) == 0
    job = await repo._pool.fetchrow(
        "SELECT estado, error_detalle FROM jobs_ejecucion WHERE cuenta_id = $1", cliente_a.cuenta.id
    )
    assert job["estado"] == "error" and "API caída" in job["error_detalle"]


@requiere_db
async def test_metrica_sin_mapeo_se_ignora_y_el_job_queda_parcial(repo, cliente_a, config) -> None:  # type: ignore[no-untyped-def]
    mapeo = await repo.mapeo_plataforma("ga4")
    conector = ConectorSinMapeo(cliente_a.cuenta, repo, mapeo, config)
    r = await conector.correr(hasta=HASTA)
    assert r.estado == "parcial"
    assert r.metricas_sin_mapeo == {"metricaInventada"}
    assert r.filas_escritas == 1


@requiere_db
async def test_credencial_cifrada_ida_y_vuelta(repo, cliente_a, config) -> None:  # type: ignore[no-untyped-def]
    await repo.guardar_credencial(cliente_a.cuenta.id, '{"secreto": 1}', config.clave_cifrado)
    assert await repo.credencial(cliente_a.cuenta.id, config.clave_cifrado) == '{"secreto": 1}'
    crudo = await repo._pool.fetchval(
        "SELECT credencial_cifrada FROM cuentas_conectadas WHERE id = $1", cliente_a.cuenta.id
    )
    assert b"secreto" not in crudo


def test_mapear_aplica_factor_y_reporta_sin_mapeo(config) -> None:  # type: ignore[no-untyped-def]
    class Nulo(ConectorBase):
        codigo = "nulo"
        plataforma = "ga4"

        async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
            return []

        def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
            return []

    from api.etl.repositorio import Cuenta

    c = Nulo(
        Cuenta(1, 1, "ga4", "x", None), None, {"bounceRate": ("tasa_rebote", Decimal(100))}, config
    )  # type: ignore[arg-type]
    assert c.mapear("bounceRate", "0.25") == ("tasa_rebote", Decimal("25.00"))
    assert c.mapear("otra", 1) is None
    assert c.metricas_sin_mapeo == {"otra"}
