import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg
import jwt
import pytest

# Valores de prueba: deben existir ANTES de importar api.config.
os.environ.setdefault("SUPABASE_JWT_SECRET", "secreto-jwt-solo-para-tests-con-largo-suficiente-32b")
os.environ.setdefault("SUPABASE_URL", "https://tests.supabase.co")
os.environ.setdefault("CLAVE_CIFRADO", "clave-cifrado-solo-para-tests")
os.environ.setdefault("CRON_SECRET", "cron-solo-para-tests")
os.environ.setdefault("AMBIENTE", "test")
os.environ.setdefault("PDF_SECRET", "pdf-secreto-solo-para-tests")
os.environ.setdefault("FRONTEND_URL", "http://front.test")
os.environ.setdefault("LINKEDIN_CLIENT_ID", "linkedin-cliente-de-prueba")
HAY_DB = bool(os.environ.get("DATABASE_URL"))
os.environ.setdefault("DATABASE_URL", "postgresql://sin-base")

from api.config import Configuracion, obtener_config  # noqa: E402
from api.db import crear_pool  # noqa: E402
from api.etl.repositorio import Cuenta, RepositorioETL  # noqa: E402

# Los tests nunca leen backend/.env: si lo hicieran, claves reales (Resend, LLM, OAuth)
# entrarían a la suite y un test podría mandar correos o llamar APIs de verdad.
Configuracion.model_config["env_file"] = None
obtener_config.cache_clear()
requiere_db = pytest.mark.skipif(not HAY_DB, reason="DATABASE_URL no definido")


@pytest.fixture(scope="session")
def config() -> Configuracion:
    return obtener_config()


@pytest.fixture
async def pool(config: Configuracion) -> AsyncIterator[asyncpg.Pool]:
    if not HAY_DB:
        pytest.skip("DATABASE_URL no definido")
    p = await crear_pool(config.database_url)
    yield p
    await p.close()


@dataclass
class ClientePrueba:
    id: int
    slug: str
    cuenta: Cuenta
    email: str


@pytest.fixture
async def repo(pool: asyncpg.Pool) -> RepositorioETL:
    return RepositorioETL(pool)


async def _crear_cliente(
    pool: asyncpg.Pool, plataforma: str = "ga4", sector: str | None = None
) -> ClientePrueba:
    sufijo = uuid.uuid4().hex[:8]
    slug = f"test-{sufijo}"
    cliente_id = await pool.fetchval(
        "INSERT INTO clientes (nombre, slug, sector) VALUES ($1, $2, $3) RETURNING id",
        f"Cliente prueba {sufijo}",
        slug,
        sector,
    )
    cuenta_id = await pool.fetchval(
        "INSERT INTO cuentas_conectadas (cliente_id, plataforma, id_externo, nombre_cuenta) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        cliente_id,
        plataforma,
        f"ext-{sufijo}",
        "Cuenta prueba",
    )
    email = f"usuario-{sufijo}@prueba.test"
    await pool.execute(
        "INSERT INTO usuarios (email, cliente_id, rol) VALUES ($1, $2, 'cliente')",
        email,
        cliente_id,
    )
    return ClientePrueba(
        int(cliente_id),
        slug,
        Cuenta(int(cuenta_id), int(cliente_id), plataforma, f"ext-{sufijo}", "Cuenta prueba"),
        email,
    )


async def _borrar_cliente(pool: asyncpg.Pool, cliente_id: int) -> None:
    # Las tablas de hechos y raw no tienen ON DELETE CASCADE (append-only): limpiar en orden.
    await pool.execute(
        "DELETE FROM fct_metrica_diaria WHERE cuenta_id IN "
        "(SELECT id FROM cuentas_conectadas WHERE cliente_id = $1)",
        cliente_id,
    )
    await pool.execute(
        "DELETE FROM fct_metrica_dimension WHERE cuenta_id IN "
        "(SELECT id FROM cuentas_conectadas WHERE cliente_id = $1)",
        cliente_id,
    )
    await pool.execute(
        "DELETE FROM dim_publicacion WHERE cuenta_id IN "
        "(SELECT id FROM cuentas_conectadas WHERE cliente_id = $1)",
        cliente_id,
    )
    await pool.execute(
        "DELETE FROM raw_payloads WHERE cuenta_id IN "
        "(SELECT id FROM cuentas_conectadas WHERE cliente_id = $1)",
        cliente_id,
    )
    # Otras corridas (alertas, proyecciones) pueden haber escrito sobre las cuentas de prueba;
    # sin esto el borrado del cliente falla por FK y deja basura en la base.
    for tabla in ("alertas", "fct_proyeccion"):
        await pool.execute(
            f"DELETE FROM {tabla} WHERE cuenta_id IN "
            "(SELECT id FROM cuentas_conectadas WHERE cliente_id = $1)",
            cliente_id,
        )
    await pool.execute(
        "DELETE FROM jobs_ejecucion WHERE cuenta_id IN "
        "(SELECT id FROM cuentas_conectadas WHERE cliente_id = $1)",
        cliente_id,
    )
    await pool.execute("DELETE FROM llm_uso WHERE cliente_id = $1", cliente_id)
    await pool.execute("DELETE FROM clientes WHERE id = $1", cliente_id)


@pytest.fixture
async def cliente_a(pool: asyncpg.Pool) -> AsyncIterator[ClientePrueba]:
    c = await _crear_cliente(pool)
    yield c
    await _borrar_cliente(pool, c.id)


@pytest.fixture
async def cliente_b(pool: asyncpg.Pool) -> AsyncIterator[ClientePrueba]:
    c = await _crear_cliente(pool, plataforma="gsc")
    yield c
    await _borrar_cliente(pool, c.id)


@pytest.fixture
async def usuario_equipo(pool: asyncpg.Pool) -> AsyncIterator[str]:
    email = f"equipo-{uuid.uuid4().hex[:8]}@geeks.test"
    await pool.execute(
        "INSERT INTO usuarios (email, cliente_id, rol) VALUES ($1, NULL, 'equipo')", email
    )
    yield email
    await pool.execute("DELETE FROM usuarios WHERE email = $1", email)


def token_para(
    email: str, expirado: bool = False, metodo: str | None = "otp", **extra: object
) -> str:
    """Token como los de Supabase. `metodo` va en `amr` (otp = enlace mágico); None = sin amr."""
    ahora = datetime.now(UTC)
    exp = ahora - timedelta(hours=1) if expirado else ahora + timedelta(hours=1)
    amr = [{"method": metodo, "timestamp": int(ahora.timestamp())}] if metodo else None
    return jwt.encode(
        {
            "sub": uuid.uuid4().hex,
            "email": email,
            "aud": "authenticated",
            "role": "authenticated",
            "iat": ahora,
            "exp": exp,
            **({"amr": amr} if amr else {}),
            **extra,
        },
        os.environ["SUPABASE_JWT_SECRET"],
        algorithm="HS256",
    )


def pdf_valido(paginas: int = 1) -> bytes:
    """PDF real y legible por pypdf, con tamaño por encima del mínimo de render.validar_pdf."""
    import io

    from pypdf import PdfWriter

    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=842, height=595)
    escritor.add_metadata({"/Subject": "reporte de prueba " + "·" * 600})
    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()
