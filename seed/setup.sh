#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$(dirname "$DIR")"

echo "Copiando imagenes a media/..."
mkdir -p "$BACKEND/media/stickers" "$BACKEND/media/covers"
cp "$DIR/media/stickers/"*.png "$BACKEND/media/stickers/"
cp "$DIR/media/covers/"*.png "$BACKEND/media/covers/"
echo "  $(ls "$BACKEND/media/stickers/" | wc -l | xargs) stickers"
echo "  $(ls "$BACKEND/media/covers/" | wc -l | xargs) covers"

echo ""
echo "Cargando fixtures..."
python manage.py loaddata "$DIR/fixture_users.json"
python manage.py loaddata "$DIR/fixture_albums.json"

echo ""
echo "Asignando passwords por defecto..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
for u in User.objects.all():
    if not u.has_usable_password():
        u.set_password('test1234')
        u.save()
        print(f'  Password set: {u.username}')
"

echo ""
echo "Listo. Usuarios disponibles:"
python manage.py shell -c "
from django.contrib.auth import get_user_model
for u in get_user_model().objects.all():
    role = 'admin' if u.is_staff else 'user'
    print(f'  {u.username} ({u.email}) [{role}]')
"
echo ""
echo "Password por defecto: test1234"
