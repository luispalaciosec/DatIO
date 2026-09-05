"""PT-02: la capa semántica es consistente y cubre lo que usan los conectores."""

from decimal import Decimal

from api.etl.conectores.demo import ConectorDemo
from api.etl.conectores.ga4 import ConectorGA4
from api.etl.conectores.gsc import ConectorGSC
from api.etl.conectores.meta_ads import ConectorMetaAds
from api.etl.conectores.meta_fb import ConectorMetaFB
from api.etl.conectores.meta_ig import ConectorMetaIG
from tests.conftest import requiere_db
from tests.semilla import mapeos_del_seed, metricas_del_seed

CONECTORES = [
    ConectorDemo,
    ConectorGA4,
    ConectorGSC,
    ConectorMetaFB,
    ConectorMetaIG,
    ConectorMetaAds,
]
PLATAFORMAS = {
    "meta_ig",
    "meta_fb",
    "meta_ads",
    "tiktok",
    "linkedin",
    "youtube",
    "ga4",
    "gsc",
    "google_ads",
}


def test_seed_tiene_metricas_y_mapeos_para_las_9_plataformas() -> None:
    metricas = metricas_del_seed()
    mapeos = mapeos_del_seed()
    assert len(metricas) >= 40
    assert set(mapeos) == PLATAFORMAS


def test_todo_mapeo_apunta_a_metrica_existente() -> None:
    metricas = metricas_del_seed()
    for plataforma, mapa in mapeos_del_seed().items():
        for nativa, (codigo, _factor) in mapa.items():
            assert codigo in metricas, f"{plataforma}.{nativa} → {codigo} no existe en dim_metrica"


def test_toda_metrica_nativa_de_conector_esta_mapeada() -> None:
    mapeos = mapeos_del_seed()
    for conector in CONECTORES:
        faltantes = set(conector.METRICAS_NATIVAS) - set(mapeos[conector.plataforma])
        assert not faltantes, f"{conector.codigo}: sin mapeo {faltantes}"


def test_ratios_0_a_1_se_normalizan_a_porcentaje() -> None:
    mapeos = mapeos_del_seed()
    assert mapeos["ga4"]["bounceRate"] == ("tasa_rebote", 100)
    assert mapeos["gsc"]["ctr"] == ("ctr_busqueda", 100)
    assert mapeos["google_ads"]["metrics.cost_micros"][1] == Decimal("0.000001")  # micros → USD


@requiere_db
async def test_seed_aplicado_en_base_coincide_con_archivo(repo) -> None:  # type: ignore[no-untyped-def]
    for plataforma, mapa in mapeos_del_seed().items():
        en_base = await repo.mapeo_plataforma(plataforma)
        assert set(en_base) == set(mapa), f"{plataforma}: la base no coincide con el seed"
