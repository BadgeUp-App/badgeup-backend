#!/bin/sh
set -e

RUN_MIGRATIONS=${RUN_MIGRATIONS:-true}

if [ "$1" = "celery" ]; then
  RUN_MIGRATIONS="false"
fi

if [ -n "$DATABASE_URL" ]; then
  echo "Conectando a BD remota (Supabase)..."
  until python -c "
import dj_database_url, psycopg2
cfg = dj_database_url.parse('$DATABASE_URL')
psycopg2.connect(host=cfg['HOST'], port=cfg['PORT'], dbname=cfg['NAME'], user=cfg['USER'], password=cfg['PASSWORD']).close()
" 2>/dev/null; do
    echo "  esperando..."
    sleep 2
  done
else
  DB_HOST="${POSTGRES_HOST:-db}"
  DB_PORT="${POSTGRES_PORT:-5432}"
  echo "Esperando BD local ($DB_HOST:$DB_PORT)..."
  while ! nc -z "$DB_HOST" "$DB_PORT"; do
    sleep 1
  done
fi
echo "Base conectada."

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

  echo "Verificando superusuarios..."
  python manage.py shell <<'PY'
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username="admin").exists():
    User.objects.create_superuser("admin", "admin@example.com", "admin")
if not User.objects.filter(username="adminfc").exists():
    User.objects.create_superuser("adminfc", "adminfc@example.com", "admin")
PY

  python manage.py collectstatic --noinput >/dev/null 2>&1 || true
fi

if [ "$#" -eq 0 ] || [ "$1" = "gunicorn" ]; then
  set -- uvicorn badgeup.asgi:application --host 0.0.0.0 --port 8000 --ws websockets
fi

echo "Levantando: $*"
exec "$@"
