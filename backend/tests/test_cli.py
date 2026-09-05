"""El comando de cron corre el ETL y devuelve 1 si alguna cuenta falló."""

from api.etl import cli
from api.etl.runner import ResumenCorrida


async def _resumen(errores: dict[int, str]) -> ResumenCorrida:
    return ResumenCorrida([], errores, [])


def test_cli_sale_0_sin_errores(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cli, "ejecutar", lambda p, h: _resumen({}))
    assert cli.main(["--plataforma", "ga4"]) == 0


def test_cli_sale_1_con_errores(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cli, "ejecutar", lambda p, h: _resumen({7: "API caída"}))
    assert cli.main([]) == 1
