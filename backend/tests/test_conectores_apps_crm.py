"""App Store, Google Play, PrometIO y HubSpot normalizan payloads fijos sin tocar la red."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from api.etl.conectores.app_store import ConectorAppStore, leer_informe_ventas, token_app_store
from api.etl.conectores.crm import ConectorHubspot, ConectorPrometio
from api.etl.conectores.google_negocio import ConectorGoogleNegocio
from api.etl.conectores.google_play import ConectorGooglePlay, leer_csv_play, meses
from api.etl.conectores.linkedin import ConectorLinkedIn, ConectorLinkedInPublicaciones, intervalo
from api.etl.conectores.zoho import ConectorZoho, etapa_es
from api.etl.repositorio import Cuenta
from tests.semilla import mapeos_del_seed

F = Path(__file__).parent / "fixtures"


def _con(clase, plataforma, id_externo, config):  # type: ignore[no-untyped-def]
    return clase(
        Cuenta(1, 1, plataforma, id_externo, None), None, mapeos_del_seed()[plataforma], config
    )


def test_app_store_ventas_resenas_y_pais(config) -> None:  # type: ignore[no-untyped-def]
    c = _con(ConectorAppStore, "app_store", "123456", config)
    filas_tsv = leer_informe_ventas((F / "app_store_sales_20260901.tsv.gz").read_bytes())
    assert len(filas_tsv) == 5
    payload = [
        {"tipo": "ventas", "fecha": "2026-09-01", "filas": filas_tsv},
        {"tipo": "ventas", "fecha": "2026-09-02", "filas": []},  # día sin ventas (404 de Apple)
        {"tipo": "resenas", **json.loads((F / "app_store_reviews.json").read_text())},
    ]
    v = {(f, m): x for f, m, x in c.normalizar(payload)}
    assert v[(date(2026, 9, 1), "descargas")] == Decimal(
        125
    )  # 120 EC + 5 US; la otra app no cuenta
    assert v[(date(2026, 9, 1), "actualizaciones_app")] == Decimal(340)
    assert v[(date(2026, 9, 1), "compras_in_app")] == Decimal(3)
    assert v[(date(2026, 9, 1), "ingresos_app")] == Decimal("6.3")  # 3 × 2.1 de proceeds
    assert v[(date(2026, 9, 2), "descargas")] == Decimal(0)
    assert v[(date(2026, 9, 1), "calificaciones")] == Decimal(2)
    assert v[(date(2026, 9, 1), "calificacion_promedio")] == Decimal(4)
    assert v[(date(2026, 9, 2), "calificacion_promedio")] == Decimal(1)
    dims = {(f, d, k): x for f, m, d, k, x in c.normalizar_dimensiones(payload)}
    assert dims[(date(2026, 9, 1), "pais", "EC")] == Decimal(120)
    assert dims[(date(2026, 9, 1), "pais", "US")] == Decimal(5)
    assert not c.metricas_sin_mapeo


def test_app_store_token_es256() -> None:
    clave = ec.generate_private_key(ec.SECP256R1())
    pem = (
        clave.private_key_bytes
        if False
        else clave.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
    )
    import time

    t = token_app_store("issuer-1", "KEY1", pem, ahora=time.time())
    cab = jwt.get_unverified_header(t)
    cuerpo = jwt.decode(t, clave.public_key(), algorithms=["ES256"], audience="appstoreconnect-v1")
    assert cab["kid"] == "KEY1" and cab["alg"] == "ES256"
    assert cuerpo["iss"] == "issuer-1" and cuerpo["exp"] - cuerpo["iat"] == 1200


def test_google_play_csv_utf16_metricas_y_pais(config) -> None:  # type: ignore[no-untyped-def]
    c = _con(ConectorGooglePlay, "google_play", "com.banco.app", config)
    payload = [
        {
            "informe": "installs",
            "mes": "202609",
            "filas": leer_csv_play((F / "google_play_installs_overview.csv").read_bytes()),
        },
        {
            "informe": "ratings",
            "mes": "202609",
            "filas": leer_csv_play((F / "google_play_ratings_overview.csv").read_bytes()),
        },
        {
            "informe": "installs_pais",
            "mes": "202609",
            "filas": leer_csv_play((F / "google_play_installs_country.csv").read_bytes()),
        },
    ]
    v = {(f, m): x for f, m, x in c.normalizar(payload)}
    assert v[(date(2026, 9, 1), "descargas")] == Decimal(210)
    assert v[(date(2026, 9, 1), "desinstalaciones")] == Decimal(40)
    assert v[(date(2026, 9, 2), "dispositivos_activos")] == Decimal(31340)
    assert v[(date(2026, 9, 1), "calificacion_promedio")] == Decimal("4.20")
    assert (date(2026, 9, 2), "calificacion_promedio") not in v  # celda vacía no se inventa
    dims = {(f, d, k): x for f, m, d, k, x in c.normalizar_dimensiones(payload)}
    assert dims[(date(2026, 9, 1), "pais", "EC")] == Decimal(200)
    assert meses(date(2026, 11, 20), date(2027, 1, 3)) == ["202611", "202612", "202701"]
    assert leer_csv_play(b"\xff\xfe") == []  # archivo vacío/corrupto no rompe


def test_prometio_metricas_diarias_y_pipeline(config) -> None:  # type: ignore[no-untyped-def]
    c = _con(ConectorPrometio, "prometio", "geeks", config)
    datos = json.loads((F / "prometio_crm.json").read_text())
    payload = [{"desde": "2026-09-01", "hasta": "2026-09-02", **datos}]
    v = {(f, m): x for f, m, x in c.normalizar(payload)}
    assert v[(date(2026, 9, 1), "contactos_nuevos")] == Decimal(2)
    assert v[(date(2026, 9, 2), "contactos_nuevos")] == Decimal(0)  # relleno a cero
    assert v[(date(2026, 9, 2), "oportunidades_creadas")] == Decimal(2)
    assert v[(date(2026, 9, 1), "oportunidades_ganadas")] == Decimal(1)
    assert v[(date(2026, 9, 1), "valor_ganado")] == Decimal(
        1500
    )  # cotizado manda sobre referencial
    assert v[(date(2026, 9, 2), "oportunidades_perdidas")] == Decimal(1)
    assert v[(date(2026, 9, 2), "oportunidades_abiertas")] == Decimal(
        1
    )  # o2; o4 inactiva no cuenta
    assert v[(date(2026, 9, 2), "valor_pipeline")] == Decimal(800)
    assert (date(2026, 9, 1), "oportunidades_abiertas") not in v  # nivel solo al día hasta
    assert not c.metricas_sin_mapeo


def test_hubspot_deals_y_contactos(config) -> None:  # type: ignore[no-untyped-def]
    c = _con(ConectorHubspot, "hubspot", "portal-1", config)
    datos = json.loads((F / "hubspot_search.json").read_text())
    payload = [{"desde": "2026-09-01", "hasta": "2026-09-02", **datos}]
    v = {(f, m): x for f, m, x in c.normalizar(payload)}
    assert v[(date(2026, 9, 1), "oportunidades_creadas")] == Decimal(1)
    assert v[(date(2026, 9, 2), "oportunidades_ganadas")] == Decimal(1)
    assert v[(date(2026, 9, 2), "valor_ganado")] == Decimal(2500)
    assert v[(date(2026, 9, 1), "oportunidades_perdidas")] == Decimal(1)
    assert v[(date(2026, 9, 2), "oportunidades_abiertas")] == Decimal(1)
    assert v[(date(2026, 9, 2), "valor_pipeline")] == Decimal(700)
    assert v[(date(2026, 9, 2), "contactos_nuevos")] == Decimal(1)  # epoch ms


async def test_credenciales_faltantes_fallan_claro(config) -> None:  # type: ignore[no-untyped-def]
    class RepoSinCred:
        async def credencial(self, cuenta_id: int, clave: str) -> None:
            return None

    cfg = config.model_copy(update={"clave_cifrado": "x"})
    for clase, plataforma in ((ConectorAppStore, "app_store"), (ConectorHubspot, "hubspot")):
        c = clase(
            Cuenta(1, 1, plataforma, "id", None), RepoSinCred(), mapeos_del_seed()[plataforma], cfg
        )  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="no tiene"):
            await c.extraer(date(2026, 9, 1), date(2026, 9, 2))


def test_zoho_etapas_y_metricas(config) -> None:  # type: ignore[no-untyped-def]
    c = _con(ConectorZoho, "zoho", "org-1", config)
    datos = json.loads((F / "zoho_crm.json").read_text())
    payload = [{"desde": "2026-09-01", "hasta": "2026-09-02", **datos}]
    v = {(f, m): x for f, m, x in c.normalizar(payload)}
    assert v[(date(2026, 9, 1), "oportunidades_ganadas")] == Decimal(1)
    assert v[(date(2026, 9, 1), "valor_ganado")] == Decimal(1200)
    assert v[(date(2026, 9, 2), "oportunidades_perdidas")] == Decimal(1)
    assert v[(date(2026, 9, 2), "oportunidades_creadas")] == Decimal(2)
    assert v[(date(2026, 9, 2), "oportunidades_abiertas")] == Decimal(
        2
    )  # negotiation + qualification
    assert v[(date(2026, 9, 2), "valor_pipeline")] == Decimal(500)  # Amount None cuenta 0
    assert v[(date(2026, 9, 1), "contactos_nuevos")] == Decimal(1)
    # Etapas en español o personalizadas
    assert etapa_es("Ganado", ("ganad",), None) and etapa_es("Cerrado perdido", ("perdid",), None)
    assert etapa_es("Firmado", (), ["Firmado"]) and not etapa_es("Closed Won", (), ["Firmado"])


def test_google_negocio_metricas_y_resenas(config) -> None:  # type: ignore[no-untyped-def]
    c = _con(ConectorGoogleNegocio, "google_negocio", "accounts/1/locations/9", config)
    assert c._ficha() == "locations/9"
    payload = [
        {"tipo": "metricas", **json.loads((F / "google_negocio_metricas.json").read_text())},
        {"tipo": "resenas", **json.loads((F / "google_negocio_resenas.json").read_text())},
    ]
    filas = c.normalizar(payload)
    v: dict[tuple[date, str], Decimal] = {}
    for f, m, x in filas:  # dos nativas (desktop+mobile) suman en la misma canónica
        v[(f, m)] = v.get((f, m), Decimal(0)) + x
    assert v[(date(2026, 9, 1), "vistas_maps")] == Decimal(300)
    assert v[(date(2026, 9, 2), "vistas_maps")] == Decimal(35)  # valor ausente = 0
    assert v[(date(2026, 9, 1), "llamadas")] == Decimal(7)
    assert v[(date(2026, 9, 1), "clics_sitio_web")] == Decimal(12)
    assert v[(date(2026, 9, 1), "calificaciones")] == Decimal(2)
    assert v[(date(2026, 9, 1), "calificacion_promedio")] == Decimal("3.5")
    assert v[(date(2026, 9, 2), "calificacion_promedio")] == Decimal(4)
    assert not c.metricas_sin_mapeo


def test_linkedin_estadisticas_de_pagina(config) -> None:  # type: ignore[no-untyped-def]
    c = _con(ConectorLinkedIn, "linkedin", "urn:li:organization:1", config)
    d = json.loads((F / "linkedin_stats.json").read_text())
    payload = [
        {"tipo": "seguidores_total", "fecha": "2026-10-02", **d["red"]},
        {"tipo": "seguidores", **d["seguidores"]},
        {"tipo": "compartidos", **d["compartidos"]},
        {"tipo": "pagina", **d["pagina"]},
    ]
    v = {(f, m): x for f, m, x in c.normalizar(payload)}
    assert v[(date(2026, 10, 2), "seguidores")] == Decimal(3400)
    assert v[(date(2026, 10, 1), "seguidores_nuevos")] == Decimal(6)
    assert v[(date(2026, 10, 2), "seguidores_nuevos")] == Decimal(-2)
    assert v[(date(2026, 10, 1), "impresiones")] == Decimal(1200)
    assert v[(date(2026, 10, 1), "alcance")] == Decimal(900)
    assert v[(date(2026, 10, 1), "interacciones")] == Decimal(86)  # 30+4+2+50
    assert v[(date(2026, 10, 1), "tasa_engagement")] == Decimal("7.17")
    assert v[(date(2026, 10, 1), "visualizaciones_pagina")] == Decimal(75)
    assert not c.metricas_sin_mapeo
    assert intervalo(date(2026, 10, 1), date(2026, 10, 2)).startswith("(timeRange:(start:")


def test_linkedin_publicaciones(config) -> None:  # type: ignore[no-untyped-def]
    c = _con(ConectorLinkedInPublicaciones, "linkedin", "urn:li:organization:1", config)
    d = json.loads((F / "linkedin_posts.json").read_text())
    pubs = c.normalizar_publicaciones([{"tipo": "posts", **d}])
    assert [p.id_externo for p in pubs] == [
        "urn:li:share:7001",
        "urn:li:share:7002",
        "urn:li:share:6999",
    ]
    assert pubs[0].tipo == "imagen" and pubs[1].tipo == "articulo" and pubs[2].tipo == "texto"
    assert pubs[0].metricas["impresiones"] == Decimal(500)
    assert pubs[0].metricas["interacciones"] == Decimal(33)
    assert pubs[1].metricas == {}  # sin estadísticas: no se inventa
    assert pubs[0].permalink.endswith("urn:li:share:7001")
