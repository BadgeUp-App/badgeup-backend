from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken


User = get_user_model()


class JwtAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        scope["user"] = AnonymousUser()
        query_string = scope.get("query_string", b"").decode()
        params = parse_qs(query_string)
        token = params.get("token", [None])[0]
        if token:
            user = await self._get_user(token)
            if user:
                scope["user"] = user
        return await self.inner(scope, receive, send)

    @database_sync_to_async
    def _get_user(self, raw_token: str):
        try:
            validated = AccessToken(raw_token)
            user_id = validated.get("user_id")
            return User.objects.get(pk=user_id)
        except Exception:
            return None


def JwtAuthMiddlewareStack(inner):
    return JwtAuthMiddleware(inner)
