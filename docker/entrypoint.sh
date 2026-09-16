#!/bin/sh
set -e

# Aplica as migrações antes de subir a API (desligue com RUN_MIGRATIONS=false)
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "==> alembic upgrade head"
    alembic upgrade head
fi

exec "$@"
