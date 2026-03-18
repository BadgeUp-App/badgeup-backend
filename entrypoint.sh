#!/bin/sh
set -e

RUN_MIGRATIONS=${RUN_MIGRATIONS:-true}

if [ "$1" = "celery" ]; then
  RUN_MIGRATIONS="false"
fi

echo "Esperando a la base de datos…"
while ! nc -z "$POSTGRES_HOST" "$POSTGRES_PORT"; do
  sleep 1
done
echo "Base conectada."

if [ "$RUN_MIGRATIONS" = "true" ]; then
  export PGPASSWORD="$POSTGRES_PASSWORD"
  psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" postgres -tc "SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'" | grep -q 1 || \
    psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" postgres -c "CREATE DATABASE \"${POSTGRES_DB}\"" >/dev/null 2>&1 || true
  unset PGPASSWORD

  echo "Aplicando migraciones..."
  python manage.py migrate --noinput

echo "Creando superusuario por defecto si no existe..."
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
