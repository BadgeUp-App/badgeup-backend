from django.urls import path

from .consumers import NotificationConsumer, ChatConsumer

websocket_urlpatterns = [
    path("ws/notifications/", NotificationConsumer.as_asgi()),
    path("ws/chat/<int:room_id>/", ChatConsumer.as_asgi()),
]
