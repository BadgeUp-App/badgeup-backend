from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AdminUserDeleteView,
    AdminUserManageView,
    BadgeupTokenObtainPairView,
    GoogleCallbackView,
    GoogleLoginStartView,
    LeaderboardView,
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
    path("google/login/", GoogleLoginStartView.as_view(), name="google-login"),
    path("google/callback/", GoogleCallbackView.as_view(), name="google-callback"),
]
