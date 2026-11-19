"""Sentry: apagado sin DSN y sin secretos ni correos en lo que se envía."""

from api.observabilidad import antes_de_enviar, iniciar_sentry, limpiar_texto


def test_sin_dsn_no_inicializa(config) -> None:  # type: ignore[no-untyped-def]
    assert iniciar_sentry(config.model_copy(update={"sentry_dsn": ""}), "api") is False


def test_limpia_tokens_correos_y_cabeceras() -> None:
    jwt_falso = "eyJhbGciOi.eyJzdWIiOi.firmaFalsa_123"
    evento = {
        "message": f"fallo abriendo https://x/imprimir?desde=1&render={jwt_falso} para a@b.com",
        "request": {
            "url": "https://api/x?token=secreto&otro=1",
            "headers": {"Authorization": f"Bearer {jwt_falso}", "Cookie": "s=1", "Accept": "*/*"},
            "cookies": {"s": "1"},
            "data": {"credencial": "x"},
        },
        "user": {"email": "a@b.com"},
        "extra": {"lista": [f"Bearer {jwt_falso}"]},
    }
    limpio = antes_de_enviar(evento, {})
    texto = str(limpio)
    assert jwt_falso not in texto and "a@b.com" not in texto and "secreto" not in texto
    assert limpio["request"]["headers"]["Authorization"] == "[filtrado]"
    assert limpio["request"]["headers"]["Accept"] == "*/*"
    assert "cookies" not in limpio["request"] and "data" not in limpio["request"]
    assert "user" not in limpio
    assert "otro=1" in limpio["request"]["url"]


def test_limpiar_texto() -> None:
    assert limpiar_texto("state=abc&code=xyz") == "state=[filtrado]&code=[filtrado]"


def test_error_de_conector_no_guarda_tokens() -> None:
    """Logs sin secretos: lo que llega a jobs_ejecucion y al log del cron se limpia."""
    texto = limpiar_texto(
        "ReadTimeout: https://graph.facebook.com/v21.0/123/insights?access_token=EAAB123&metric=x"
    )
    assert "EAAB123" not in texto and "metric=x" in texto
