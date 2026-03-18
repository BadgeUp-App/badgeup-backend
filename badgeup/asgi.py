import os

import django
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "badgeup.settings")
django.setup()
from badgeup.routing import application  # noqa: E402,F401

# Exponer también la aplicación HTTP para compatibilidad con herramientas ASGI.
http_application = get_asgi_application()
