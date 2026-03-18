from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()


class JWTAuthMiddleware:
    """
    Minimal JWT auth middleware for Channels that reads the access token
    from the query string (?token=...) and attaches the user to scope.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = query.get("token", [None])[0]

        scope["user"] = None

        if token:
            try:
                access = AccessToken(token)
                user = await database_sync_to_async(User.objects.get)(id=access["user_id"])
                scope["user"] = user
            except (InvalidToken, User.DoesNotExist):
                scope["user"] = None

        return await self.app(scope, receive, send)
