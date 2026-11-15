#!/usr/bin/env bash
# Aplica TODO el SQL del repo a una base Postgres limpia, en orden: migraciones numeradas
# (excepto las que dependen de los esquemas auth/storage de Supabase) y luego los seeds.
# Lo usan CI y docker-compose para que no vuelvan a separarse del esquema real.
#
# Uso: scripts/aplicar_sql.sh "$DATABASE_URL"   (o DATABASE_URL en el entorno)
#
# Una migración nueva que dependa de auth./storage. de Supabase debe:
#   1) decirlo en su cabecera ("Depende del esquema storage/auth de Supabase"), y
#   2) agregarse a EXCLUIR aquí.
set -euo pipefail

URL="${1:-${DATABASE_URL:-}}"
if [[ -z "$URL" ]]; then
  echo "Falta la URL de la base (argumento o DATABASE_URL)" >&2
  exit 1
fi
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Dependen de auth/storage de Supabase: no existen en un Postgres vanilla.
EXCLUIR=(
  003_storage_marcas.sql
  011_endurecer_acceso.sql
  015_storage_marcas_sin_svg.sql
)

# Orden de los seeds: métricas primero; la plantilla base antes que sus extensiones;
# narrativa al final porque agrega un bloque a todas las páginas existentes.
SEEDS=(
  metricas.sql
  plantilla_rrss.sql
  plantilla_rrss_extras.sql
  plantilla_pacing.sql
  plantilla_benchmark.sql
  plantilla_radar_pauta.sql
  plantilla_apps_crm.sql
  plantilla_zoho_negocio.sql
  plantilla_narrativa.sql
)

aplicar() {
  echo "→ $1"
  psql "$URL" -q -v ON_ERROR_STOP=1 -f "$1" >/dev/null
}

excluida() {
  local nombre="$1" e
  for e in "${EXCLUIR[@]}"; do [[ "$e" == "$nombre" ]] && return 0; done
  return 1
}

for f in $(ls "$RAIZ"/sql/0*.sql | sort); do
  nombre="$(basename "$f")"
  if excluida "$nombre"; then
    echo "  (omitida, depende de Supabase) $nombre"
    continue
  fi
  aplicar "$f"
done

# Un seed nuevo que no esté en la lista hace fallar el script: hay que ubicarlo a propósito.
for f in "$RAIZ"/sql/seeds/*.sql; do
  nombre="$(basename "$f")"
  [[ " ${SEEDS[*]} " == *" $nombre "* ]] || { echo "Seed sin orden asignado: $nombre (agrégalo a SEEDS)" >&2; exit 1; }
done
for s in "${SEEDS[@]}"; do
  aplicar "$RAIZ/sql/seeds/$s"
done
echo "SQL aplicado."
