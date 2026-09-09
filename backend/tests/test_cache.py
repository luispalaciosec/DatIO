"""PT-12: cache en proceso de /consulta."""

from api.consulta.cache import CacheConsulta

CLAVE = (1, 2, "2026-08-01", "2026-08-28", None)


def test_cache_acierta_y_expira() -> None:
    c = CacheConsulta(ttl_seg=100)
    c.fijar_generacion("g1", ahora=0)
    assert c.obtener(CLAVE, ahora=1) is None
    c.guardar(CLAVE, {"datos": [1], "estado": "consolidado", "meta": {}}, ahora=1)
    assert c.obtener(CLAVE, ahora=50) == {"datos": [1], "estado": "consolidado", "meta": {}}
    assert c.obtener(CLAVE, ahora=200) is None  # expiró por TTL
    assert c.aciertos == 1 and c.fallos == 2


def test_cache_se_invalida_al_cambiar_generacion() -> None:
    c = CacheConsulta(ttl_seg=1000)
    c.fijar_generacion("g1", ahora=0)
    c.guardar(CLAVE, {"datos": 1, "estado": "consolidado", "meta": {}}, ahora=0)
    assert c.generacion_vigente(ahora=30) and not c.generacion_vigente(ahora=61)
    c.fijar_generacion("g1", ahora=61)  # misma generación: se conserva
    assert c.obtener(CLAVE, ahora=62) is not None
    c.fijar_generacion("g2", ahora=70)  # el ETL escribió: todo fuera
    assert c.obtener(CLAVE, ahora=71) is None


def test_cache_no_guarda_provisionales_y_respeta_capacidad() -> None:
    c = CacheConsulta(ttl_seg=1000, capacidad=2)
    c.fijar_generacion("g", ahora=0)
    c.guardar(CLAVE, {"datos": 1, "estado": "provisional", "meta": {}}, ahora=0)
    assert c.obtener(CLAVE, ahora=1) is None
    for i in range(3):
        c.guardar(
            (i, 0, "a", "b", None), {"datos": i, "estado": "consolidado", "meta": {}}, ahora=0
        )
    assert c.obtener((0, 0, "a", "b", None), ahora=1) is None  # el más viejo salió
    assert c.obtener((2, 0, "a", "b", None), ahora=1) == {
        "datos": 2,
        "estado": "consolidado",
        "meta": {},
    }
