import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from achievements.models import UserSticker

from .serializers import (
    AdminUserManageSerializer,
    PublicUserProfileSerializer,
    RegisterSerializer,
    UserSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        headers = self.get_success_headers(serializer.data)
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class BadgeupTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        token["email"] = user.email
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class BadgeupTokenObtainPairView(TokenObtainPairView):
    serializer_class = BadgeupTokenObtainPairSerializer


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class LeaderboardView(generics.ListAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        limit = int(self.request.query_params.get("limit", 20))
        limit = max(1, min(limit, 100))
        return (
            User.objects.order_by("-points")
            .prefetch_related("user_stickers")[:limit]
        )


class GoogleLoginStartView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        client_id = settings.GOOGLE_CLIENT_ID
        redirect_uri = settings.GOOGLE_REDIRECT_URI
        scope = "openid email profile"

        auth_url = (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?response_type=code"
            f"&client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scope}"
            f"&access_type=offline"
            f"&prompt=consent"
        )

        return redirect(auth_url)


class GoogleCallbackView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        code = request.query_params.get("code")
        if not code:
            return redirect(f"{settings.FRONTEND_URL}/login?error=google_no_code")

        token_data = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        token_resp = requests.post("https://oauth2.googleapis.com/token", data=token_data)
        if token_resp.status_code != 200:
            return redirect(f"{settings.FRONTEND_URL}/login?error=google_token")

        token_json = token_resp.json()
        access_token = token_json.get("access_token")
        if not access_token:
            return redirect(f"{settings.FRONTEND_URL}/login?error=google_no_access")

        userinfo_resp = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            return redirect(f"{settings.FRONTEND_URL}/login?error=google_userinfo")

        profile = userinfo_resp.json()
        email = profile.get("email")
        given_name = profile.get("given_name") or ""
        family_name = profile.get("family_name") or ""
        picture = profile.get("picture")

        if not email:
            return redirect(f"{settings.FRONTEND_URL}/login?error=google_no_email")

        username = email.split("@")[0]

        user, _ = User.objects.get_or_create(
            email=email.lower(),
            defaults={
                "username": username,
                "first_name": given_name,
                "last_name": family_name,
            },
        )
        if picture:
            user.avatar = picture
            user.save(update_fields=["avatar"])

        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        frontend_login_url = (
            f"{settings.FRONTEND_URL}/login"
            f"?google=1"
            f"&access={access}"
            f"&refresh={refresh}"
        )
        return redirect(frontend_login_url)


class PublicUserProfileView(generics.RetrieveAPIView):
    serializer_class = PublicUserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = User.objects.all().prefetch_related("user_stickers")

    def get_object(self):
        obj = super().get_object()
        obj.stickers_captured = UserSticker.objects.filter(
            user=obj, status=UserSticker.STATUS_APPROVED
        ).count()
        return obj


class AdminUserManageView(generics.UpdateAPIView):
    serializer_class = AdminUserManageSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.all()


class AdminUserDeleteView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.all()
