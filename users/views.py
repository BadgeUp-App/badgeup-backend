import random
from datetime import timedelta

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from achievements.models import UserSticker

from .firebase_backend import verify_id_token as firebase_verify_id_token
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
        # Allow the "username" field to actually contain an email. If an email
        # is received, swap it for the matching username before delegating to
        # the parent validator.
        username_value = attrs.get(self.username_field, "")
        if isinstance(username_value, str) and "@" in username_value:
            try:
                user = User.objects.get(email__iexact=username_value)
                attrs[self.username_field] = user.username
            except User.DoesNotExist:
                pass
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
            User.objects.filter(is_staff=False)
            .order_by("-points")
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


class GoogleMobileLoginView(APIView):
    """
    Accepts an OAuth access_token obtained by the mobile app via google_sign_in
    and exchanges it for a BadgeUp JWT pair. The token is validated against
    Google's userinfo endpoint.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        access_token = request.data.get("access_token")
        if not access_token:
            return Response(
                {"detail": "access_token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        userinfo_resp = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if userinfo_resp.status_code != 200:
            return Response(
                {"detail": "Invalid Google access token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        profile = userinfo_resp.json()
        email = profile.get("email")
        if not email:
            return Response(
                {"detail": "Google account has no email."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        given_name = profile.get("given_name") or ""
        family_name = profile.get("family_name") or ""
        picture = profile.get("picture")
        email = email.lower()

        base_username = email.split("@")[0]
        username = base_username
        idx = 1
        while (
            User.objects.filter(username=username)
            .exclude(email=email)
            .exists()
        ):
            idx += 1
            username = f"{base_username}{idx}"

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": username,
                "first_name": given_name,
                "last_name": family_name,
            },
        )

        if picture and not user.avatar:
            try:
                user.avatar = picture
                user.save(update_fields=["avatar"])
            except Exception:
                pass

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": UserSerializer(user).data,
                "created": created,
            },
            status=status.HTTP_200_OK,
        )


class FirebaseLoginView(APIView):
    """Recibe un ID token de Firebase y devuelve un par de tokens BadgeUp."""

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        id_token = request.data.get("id_token")
        if not id_token:
            return Response(
                {"detail": "id_token es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        decoded, err = firebase_verify_id_token(id_token)
        if not decoded:
            is_config = err and err.startswith("Firebase no configurado")
            payload = {
                "detail": (
                    "Firebase no esta configurado en el servidor."
                    if is_config
                    else "Token de Firebase invalido."
                )
            }
            if err:
                payload["reason"] = err
            return Response(
                payload,
                status=(
                    status.HTTP_503_SERVICE_UNAVAILABLE
                    if is_config
                    else status.HTTP_401_UNAUTHORIZED
                ),
            )

        email = (decoded.get("email") or "").lower()
        if not email:
            return Response(
                {"detail": "La cuenta de Firebase no tiene email."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        name = decoded.get("name") or ""
        given_name = ""
        family_name = ""
        if name:
            parts = name.strip().split(" ", 1)
            given_name = parts[0]
            family_name = parts[1] if len(parts) > 1 else ""

        picture = decoded.get("picture")

        base_username = email.split("@")[0]
        username = base_username
        idx = 1
        while (
            User.objects.filter(username=username)
            .exclude(email=email)
            .exists()
        ):
            idx += 1
            username = f"{base_username}{idx}"

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": username,
                "first_name": given_name,
                "last_name": family_name,
            },
        )

        if picture and not user.avatar:
            try:
                user.avatar = picture
                user.save(update_fields=["avatar"])
            except Exception:
                pass

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": UserSerializer(user).data,
                "created": created,
            },
            status=status.HTTP_200_OK,
        )


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


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        email = (request.data.get("email") or "").strip().lower()
        generic_msg = "Si el correo existe, se envio un codigo de recuperacion."
        if not email:
            return Response({"detail": generic_msg}, status=status.HTTP_200_OK)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"detail": generic_msg}, status=status.HTTP_200_OK)

        if not user.has_usable_password():
            return Response({"detail": generic_msg}, status=status.HTTP_200_OK)

        code = f"{random.randint(0, 999999):06d}"
        user.reset_code = code
        user.reset_code_expires = timezone.now() + timedelta(minutes=15)
        user.save(update_fields=["reset_code", "reset_code_expires"])
        try:
            from django.core.mail import send_mail
            send_mail(
                "BadgeUp - Codigo de recuperacion",
                f"Tu codigo de recuperacion es: {code}\n\nExpira en 15 minutos.",
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=True,
            )
        except Exception:
            pass
        print(f"[PASSWORD RESET] {email} -> code: {code}")
        return Response({"detail": generic_msg}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        email = (request.data.get("email") or "").strip().lower()
        code = (request.data.get("code") or "").strip()
        new_password = request.data.get("new_password") or ""

        if not email or not code or not new_password:
            return Response(
                {"detail": "Faltan campos requeridos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"detail": "Codigo invalido o expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            not user.reset_code
            or user.reset_code != code
            or not user.reset_code_expires
            or user.reset_code_expires < timezone.now()
        ):
            return Response(
                {"detail": "Codigo invalido o expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.reset_code = None
        user.reset_code_expires = None
        user.save(update_fields=["password", "reset_code", "reset_code_expires"])
        return Response(
            {"detail": "Contrasena actualizada."},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        old_password = request.data.get("old_password") or ""
        new_password = request.data.get("new_password") or ""

        if not old_password or not new_password:
            return Response(
                {"detail": "Faltan campos requeridos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.check_password(old_password):
            return Response(
                {"detail": "La contrasena actual es incorrecta."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(new_password)
        request.user.save(update_fields=["password"])
        return Response(
            {"detail": "Contrasena actualizada."},
            status=status.HTTP_200_OK,
        )


class DeviceTokenView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        token = (request.data.get("token") or "").strip()
        platform = (request.data.get("platform") or "").strip().lower()
        if not token:
            return Response(
                {"detail": "token requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        user.fcm_token = token[:512]
        user.fcm_platform = platform[:16]
        user.fcm_updated_at = timezone.now()
        user.save(update_fields=["fcm_token", "fcm_platform", "fcm_updated_at"])
        return Response({"detail": "ok"}, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        user = request.user
        user.fcm_token = ""
        user.fcm_platform = ""
        user.save(update_fields=["fcm_token", "fcm_platform"])
        return Response(status=status.HTTP_204_NO_CONTENT)
