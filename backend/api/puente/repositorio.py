"""SQL del puente CRM (PT-16). Los disparadores no escriben SQL."""

import json
from datetime import date, datetime, timedelta
from typing import Any

import asyncpg

METRICA_PRINCIPAL = {
    "meta_ig": "alcance",
    "meta_fb": "alcance",
    "ga4": "sesiones",
    "linkedin": "impresiones",
    "tiktok": "visualizaciones",
}


class RepositorioPuente:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def clientes_con_crm(self, cliente_id: int | None = None) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT id, nombre, slug, sector, crm_proveedor, crm_empresa_ref, crm_contacto_ref,
                   crm_config
            FROM   clientes
            WHERE  activo AND crm_proveedor IS NOT NULL AND crm_empresa_ref IS NOT NULL
              AND  ($1::bigint IS NULL OR id = $1)
            ORDER  BY nombre
            """,
            cliente_id,
        )
        salida = []
        for f in filas:
            d = dict(f)
            if isinstance(d["crm_config"], str):
                d["crm_config"] = json.loads(d["crm_config"])
            salida.append(d)
        return salida

    async def credencial_crm(self, cliente_id: int, clave: str) -> str | None:
        v = await self._pool.fetchval(
            "SELECT pgp_sym_decrypt(crm_credencial_cifrada, $2) FROM clientes "
            "WHERE id = $1 AND crm_credencial_cifrada IS NOT NULL",
            cliente_id,
            clave,
        )
        return str(v) if v is not None else None

    async def guardar_crm(
        self,
        cliente_id: int,
        proveedor: str | None,
        empresa_ref: str | None,
        contacto_ref: str | None,
        config: dict[str, Any] | None,
        credencial: str | None,
        clave: str,
    ) -> None:
        await self._pool.execute(
            """
            UPDATE clientes SET crm_proveedor = $2, crm_empresa_ref = $3, crm_contacto_ref = $4,
                   crm_config = COALESCE($5::jsonb, crm_config)
            WHERE  id = $1
            """,
            cliente_id,
            proveedor,
            empresa_ref,
            contacto_ref,
            json.dumps(config) if config is not None else None,
        )
        if credencial:
            await self._pool.execute(
                "UPDATE clientes SET crm_credencial_cifrada = pgp_sym_encrypt($2, $3) "
                "WHERE id = $1",
                cliente_id,
                credencial,
                clave,
            )

    async def cuentas(self, cliente_id: int) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            "SELECT id, plataforma, nombre_cuenta FROM cuentas_conectadas "
            "WHERE cliente_id = $1 AND activo ORDER BY plataforma",
            cliente_id,
        )
        return [dict(f) for f in filas]

    async def serie(
        self, cuenta_id: int, metrica: str, desde: date, hasta: date
    ) -> dict[date, float]:
        filas = await self._pool.fetch(
            "SELECT fecha, valor FROM v_metrica_actual "
            "WHERE cuenta_id = $1 AND metrica_codigo = $2 AND fecha BETWEEN $3 AND $4",
            cuenta_id,
            metrica,
            desde,
            hasta,
        )
        return {f["fecha"]: float(f["valor"]) for f in filas}

    async def agregacion(self, metrica: str) -> str:
        v = await self._pool.fetchval(
            "SELECT agregacion FROM dim_metrica WHERE codigo = $1", metrica
        )
        return str(v or "suma")

    async def gasto_ads(self, cliente_id: int, dias: int) -> float | None:
        """Gasto en Meta Ads de los últimos N días; None si no hay cuenta de pauta."""
        f = await self._pool.fetchrow(
            """
            SELECT count(c.*) AS cuentas,
                   COALESCE(sum(v.valor), 0) AS gasto
            FROM   cuentas_conectadas c
            LEFT   JOIN v_metrica_actual v ON v.cuenta_id = c.id AND v.metrica_codigo = 'gasto'
                   AND v.fecha >= current_date - $2::int
            WHERE  c.cliente_id = $1 AND c.activo AND c.plataforma IN ('meta_ads', 'google_ads')
            """,
            cliente_id,
            dias,
        )
        if f is None or not f["cuentas"]:
            return None
        return float(f["gasto"])

    async def engagement_propio(self, cliente_id: int, n: int = 12) -> float | None:
        """Interacciones promedio de las últimas N publicaciones de Instagram / seguidores × 100."""
        f = await self._pool.fetchrow(
            """
            WITH cta AS (SELECT id FROM cuentas_conectadas
                         WHERE cliente_id = $1 AND activo AND plataforma = 'meta_ig'),
            recientes AS (
                SELECT id FROM dim_publicacion WHERE cuenta_id IN (SELECT id FROM cta)
                ORDER BY publicado_en DESC NULLS LAST LIMIT $2),
            inter AS (
                SELECT DISTINCT ON (publicacion_id) publicacion_id, valor
                FROM fct_publicacion_diaria
                WHERE publicacion_id IN (SELECT id FROM recientes)
                  AND metrica_codigo = 'interacciones'
                ORDER BY publicacion_id, fecha_snapshot DESC),
            seg AS (
                SELECT valor FROM v_metrica_actual WHERE cuenta_id IN (SELECT id FROM cta)
                AND metrica_codigo = 'seguidores' ORDER BY fecha DESC LIMIT 1)
            SELECT (SELECT avg(valor) FROM inter) AS inter, (SELECT valor FROM seg) AS seguidores
            """,
            cliente_id,
            n,
        )
        if f is None or f["inter"] is None or not f["seguidores"]:
            return None
        return float(f["inter"]) / float(f["seguidores"]) * 100

    async def anuncios_nuevos_competencia(self, cliente_id: int, dias: int) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT k.id AS competidor_id, k.nombre, count(a.*) AS nuevos,
                   count(a.*) FILTER (WHERE a.activo) AS activos_total
            FROM   cliente_competidores k
            JOIN   dim_anuncio_competencia a ON a.competidor_id = k.id
            WHERE  k.cliente_id = $1 AND a.primera_vez_visto >= current_date - $2::int
            GROUP  BY k.id ORDER BY nuevos DESC
            """,
            cliente_id,
            dias,
        )
        return [dict(f) for f in filas]

    async def disparo_reciente(self, cliente_id: int, codigo: str, dias: int) -> bool:
        return bool(
            await self._pool.fetchval(
                "SELECT 1 FROM disparos_crm WHERE cliente_id = $1 AND codigo = $2 "
                "AND disparado_en > now() - ($3::int || ' days')::interval "
                "AND error IS NULL LIMIT 1",
                cliente_id,
                codigo,
                dias,
            )
        )

    async def registrar_disparo(
        self,
        cliente_id: int,
        cuenta_id: int | None,
        codigo: str,
        titulo: str,
        contexto: dict[str, Any],
        objeto_ref: str | None,
        error: str | None,
    ) -> int:
        v = await self._pool.fetchval(
            """
            INSERT INTO disparos_crm
                   (cliente_id, cuenta_id, codigo, titulo, contexto, crm_objeto_ref, error)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7) RETURNING id
            """,
            cliente_id,
            cuenta_id,
            codigo,
            titulo,
            json.dumps(contexto, default=str),
            objeto_ref,
            error,
        )
        return int(v)

    async def disparos(
        self, limite: int = 100, cliente_id: int | None = None
    ) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT d.id, d.cliente_id, c.nombre AS cliente, c.crm_proveedor, d.codigo, d.titulo,
                   d.contexto, d.crm_objeto_ref, d.error, d.disparado_en
            FROM   disparos_crm d LEFT JOIN clientes c ON c.id = d.cliente_id
            WHERE  ($2::bigint IS NULL OR d.cliente_id = $2)
            ORDER  BY d.id DESC LIMIT $1
            """,
            limite,
            cliente_id,
        )
        salida = []
        for f in filas:
            d = dict(f)
            if isinstance(d["contexto"], str):
                d["contexto"] = json.loads(d["contexto"])
            salida.append(d)
        return salida

    async def crear_alerta(
        self, cuenta_id: int | None, titulo: str, detalle: dict[str, Any]
    ) -> None:
        await self._pool.execute(
            "INSERT INTO alertas (cuenta_id, tipo, severidad, titulo, detalle) "
            "VALUES ($1, 'comercial', 'media', $2, $3::jsonb)",
            cuenta_id,
            titulo,
            json.dumps(detalle, default=str),
        )

    @staticmethod
    def hace(dias: int) -> datetime:
        return datetime.now() - timedelta(days=dias)
