from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

from albums.routing import websocket_urlpatterns as album_websocket_urlpatterns
from users.middleware import JWTAuthMiddleware

websocket_urlpatterns = [*album_websocket_urlpatterns]

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})
