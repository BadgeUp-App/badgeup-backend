from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AdminUserDeleteView,
    AdminUserManageView,
    BadgeupTokenObtainPairView,
    ChangePasswordView,
    FirebaseLoginView,
    GoogleCallbackView,
    GoogleLoginStartView,
    GoogleMobileLoginView,
    LeaderboardView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfileView,
    PublicUserProfileView,
    RegisterView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", BadgeupTokenObtainPairView.as_view(), name="auth-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("users/<int:pk>/", PublicUserProfileView.as_view(), name="user-public-profile"),
    path("users/<int:pk>/admin/", AdminUserManageView.as_view(), name="user-admin-manage"),
    path("users/<int:pk>/admin/delete/", AdminUserDeleteView.as_view(), name="user-admin-delete"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("google/login/", GoogleLoginStartView.as_view(), name="google-login"),
    path("google/callback/", GoogleCallbackView.as_view(), name="google-callback"),
    path("google/mobile/", GoogleMobileLoginView.as_view(), name="google-mobile"),
    path("firebase/", FirebaseLoginView.as_view(), name="firebase-login"),
]
