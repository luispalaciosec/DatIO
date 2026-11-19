#!/usr/bin/env bash
# Lo ejecuta la imagen de Postgres al crear la base por primera vez (docker-entrypoint-initdb.d).
# Aplica el mismo SQL que CI con scripts/aplicar_sql.sh (B-2).
set -euo pipefail
/datio/scripts/aplicar_sql.sh "postgresql:///${POSTGRES_DB}?user=${POSTGRES_USER}"
