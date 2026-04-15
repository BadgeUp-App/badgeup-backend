#!/bin/sh
set -e

RUN_MIGRATIONS=${RUN_MIGRATIONS:-true}

if [ "$1" = "celery" ]; then
  RUN_MIGRATIONS="false"
fi

SUPABASE_OK=false
if [ -n "$DATABASE_URL" ]; then
  echo "Intentando BD remota (Supabase)..."
  TRIES=0
  MAX_TRIES=5
  while [ $TRIES -lt $MAX_TRIES ]; do
    if python -c "
import psycopg2, os
psycopg2.connect(os.environ['DATABASE_URL'], connect_timeout=5).close()
" 2>/dev/null; then
      SUPABASE_OK=true
      break
    fi
    TRIES=$((TRIES + 1))
    echo "  intento $TRIES/$MAX_TRIES..."
    sleep 2
  done
fi

if [ "$SUPABASE_OK" = "true" ]; then
  echo "Conectado a Supabase."
else
  if [ "$DATABASE_FALLBACK" = "true" ]; then
    echo "Supabase no disponible, usando BD local..."
    unset DATABASE_URL
    DB_HOST="${POSTGRES_HOST:-db}"
    DB_PORT="${POSTGRES_PORT:-5432}"
    echo "Esperando BD local ($DB_HOST:$DB_PORT)..."
    while ! nc -z "$DB_HOST" "$DB_PORT"; do
      sleep 1
    done
    echo "BD local conectada."
  else
    echo "Supabase no disponible y fallback desactivado."
    exit 1
  fi
fi

if [ "$RUN_MIGRATIONS" = "true" ]; then
  if [ -z "$DATABASE_URL" ]; then
    export PGPASSWORD="$POSTGRES_PASSWORD"
    psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" postgres -tc \
      "SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'" | grep -q 1 || \
      psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" postgres \
        -c "CREATE DATABASE \"${POSTGRES_DB}\"" >/dev/null 2>&1 || true
    unset PGPASSWORD
  fi

  echo "Aplicando migraciones..."
  python manage.py migrate --noinput

  python manage.py collectstatic --noinput >/dev/null 2>&1 || true
fi

if [ "$#" -eq 0 ] || [ "$1" = "gunicorn" ]; then
  set -- uvicorn badgeup.asgi:application --host 0.0.0.0 --port 8000 --ws websockets
fi

echo "Levantando: $*"
exec "$@"
