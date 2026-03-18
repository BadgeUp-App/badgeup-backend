"""
Rutas websocket unificadas.

Se reexportan las rutas de `albums.routing` para que solo exista un origen
de verdad (chat y notificaciones autenticados por token en querystring).
"""

from albums.routing import websocket_urlpatterns  # noqa: F401
