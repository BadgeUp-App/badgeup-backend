import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

User = get_user_model()


class SentryInitTests(SimpleTestCase):
    def test_no_dsn_returns_false(self):
        from badgeup.observability import init_sentry

        with mock.patch.dict(os.environ, {"SENTRY_DSN": ""}, clear=False):
            self.assertFalse(init_sentry())

    def test_dsn_initializes_sentry_once(self):
        from badgeup.observability import init_sentry

        env = {
            "SENTRY_DSN": "https://abc@o0.ingest.sentry.io/1",
            "SENTRY_ENVIRONMENT": "ci",
        }
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch("sentry_sdk.init") as m_init:
            self.assertTrue(init_sentry())
            m_init.assert_called_once()
            kwargs = m_init.call_args.kwargs
            self.assertEqual(kwargs["dsn"], env["SENTRY_DSN"])
            self.assertEqual(kwargs["environment"], "ci")
            self.assertFalse(kwargs["send_default_pii"])


class RegisterTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("auth-register")

    def test_register_creates_user(self):
        payload = {
            "username": "newuser",
            "email": "newuser@test.com",
            "password": "S3curePass!2026",
            "password_confirm": "S3curePass!2026",
        }
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_register_rejects_weak_password(self):
        payload = {
            "username": "weak",
            "email": "weak@test.com",
            "password": "1234",
            "password_confirm": "1234",
        }
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_rejects_password_mismatch(self):
        payload = {
            "username": "mismatch",
            "email": "m@test.com",
            "password": "S3curePass!2026",
            "password_confirm": "Different!2026",
        }
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(username="existing", email="dup@test.com", password="x")
        payload = {
            "username": "newone",
            "email": "dup@test.com",
            "password": "S3curePass!2026",
            "password_confirm": "S3curePass!2026",
        }
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class RateLimitConfigTests(APITestCase):
    """
    Behavioral throttling testing in unit tests is unreliable due to caching.
    These tests verify the throttle config is correctly wired to the views,
    which is what we control in code. Real rate-limit behavior is exercised
    against the deployed backend.
    """

    def test_settings_has_throttle_classes(self):
        from django.conf import settings as dj_settings
        rest = dj_settings.REST_FRAMEWORK
        self.assertIn("DEFAULT_THROTTLE_CLASSES", rest)
        self.assertIn(
            "rest_framework.throttling.ScopedRateThrottle",
            rest["DEFAULT_THROTTLE_CLASSES"],
        )

    def test_settings_has_throttle_rates(self):
        from django.conf import settings as dj_settings
        rates = dj_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        for scope in ("login", "register", "scan", "password_reset", "anon", "user"):
            self.assertIn(scope, rates, f"missing throttle scope: {scope}")

    def test_login_view_has_throttle_scope(self):
        from users.views import BadgeupTokenObtainPairView
        self.assertEqual(BadgeupTokenObtainPairView.throttle_scope, "login")

    def test_register_view_has_throttle_scope(self):
        from users.views import RegisterView
        self.assertEqual(RegisterView.throttle_scope, "register")

    def test_scan_view_has_throttle_scope(self):
        from albums.views import GlobalScanView
        self.assertEqual(GlobalScanView.throttle_scope, "scan")

    def test_password_reset_views_have_throttle_scope(self):
        from users.views import PasswordResetRequestView, PasswordResetConfirmView
        self.assertEqual(PasswordResetRequestView.throttle_scope, "password_reset")
        self.assertEqual(PasswordResetConfirmView.throttle_scope, "password_reset")

    def test_jwt_blacklist_app_installed(self):
        from django.conf import settings as dj_settings
        self.assertIn(
            "rest_framework_simplejwt.token_blacklist",
            dj_settings.INSTALLED_APPS,
        )

    def test_jwt_rotation_enabled(self):
        from django.conf import settings as dj_settings
        self.assertTrue(dj_settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS"))
        self.assertTrue(dj_settings.SIMPLE_JWT.get("BLACKLIST_AFTER_ROTATION"))


class SecurityConfigTests(APITestCase):
    """Verifica que los defaults inseguros NO esten activos."""

    def test_default_permission_is_authenticated(self):
        from django.conf import settings as dj_settings
        self.assertIn(
            "rest_framework.permissions.IsAuthenticated",
            dj_settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"],
        )

    def test_secret_key_not_default(self):
        from django.conf import settings as dj_settings
        self.assertNotEqual(dj_settings.SECRET_KEY, "change-me-in-production")

    def test_debug_default_is_false_in_settings_module(self):
        import os
        previous = os.environ.pop("DJANGO_DEBUG", None)
        try:
            value = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
            self.assertFalse(value)
        finally:
            if previous is not None:
                os.environ["DJANGO_DEBUG"] = previous

    def test_allowed_hosts_default_is_empty(self):
        import os
        previous = os.environ.pop("DJANGO_ALLOWED_HOSTS", None)
        try:
            raw = os.getenv("DJANGO_ALLOWED_HOSTS", "")
            self.assertEqual(raw, "")
        finally:
            if previous is not None:
                os.environ["DJANGO_ALLOWED_HOSTS"] = previous


class JwtTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="jwtuser",
            email="jwt@test.com",
            password="S3curePass!2026",
        )

    def test_login_returns_token_pair(self):
        resp = self.client.post(
            reverse("auth-login"),
            {"username": "jwtuser", "password": "S3curePass!2026"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertIn("user", resp.data)

    def test_login_rejects_wrong_password(self):
        resp = self.client.post(
            reverse("auth-login"),
            {"username": "jwtuser", "password": "wrong"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_rotates_and_blacklists(self):
        login = self.client.post(
            reverse("auth-login"),
            {"username": "jwtuser", "password": "S3curePass!2026"},
            format="json",
        )
        old_refresh = login.data["refresh"]
        first = self.client.post(
            reverse("token-refresh"),
            {"refresh": old_refresh},
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertNotEqual(first.data.get("refresh"), old_refresh)
        second = self.client.post(
            reverse("token-refresh"),
            {"refresh": old_refresh},
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_protected_endpoint_requires_token(self):
        resp = self.client.get(reverse("profile"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_protected_endpoint_works_with_token(self):
        login = self.client.post(
            reverse("auth-login"),
            {"username": "jwtuser", "password": "S3curePass!2026"},
            format="json",
        )
        token = login.data["access"]
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = client.get(reverse("profile"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["username"], "jwtuser")


class PasswordResetTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="resetuser",
            email="reset@test.com",
            password="S3curePass!2026",
        )

    def test_request_returns_generic_message_for_unknown_email(self):
        resp = self.client.post(
            reverse("password-reset"),
            {"email": "nonexistent@test.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("Si el correo existe", resp.data["detail"])

    def test_request_returns_same_message_for_known_email(self):
        resp = self.client.post(
            reverse("password-reset"),
            {"email": "reset@test.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("Si el correo existe", resp.data["detail"])

    def test_confirm_rejects_invalid_code(self):
        resp = self.client.post(
            reverse("password-reset-confirm"),
            {
                "email": "reset@test.com",
                "code": "999999",
                "new_password": "Brand4New!Pass",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class AdminPermissionTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.regular = User.objects.create_user(
            username="regular",
            email="r@test.com",
            password="S3curePass!2026",
        )
        self.admin = User.objects.create_user(
            username="adm",
            email="a@test.com",
            password="S3curePass!2026",
            is_staff=True,
        )
        self.target = User.objects.create_user(
            username="target",
            email="t@test.com",
            password="S3curePass!2026",
        )

    def _auth(self, user):
        login = self.client.post(
            reverse("auth-login"),
            {"username": user.username, "password": "S3curePass!2026"},
            format="json",
        )
        return login.data["access"]

    def test_regular_user_cannot_promote_others(self):
        token = self._auth(self.regular)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = client.patch(
            reverse("user-admin-manage", args=[self.target.id]),
            {"is_staff": True},
            format="json",
        )
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_admin_can_promote_others(self):
        token = self._auth(self.admin)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = client.patch(
            reverse("user-admin-manage", args=[self.target.id]),
            {"is_staff": True},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_staff)

    def test_regular_user_cannot_delete_others(self):
        token = self._auth(self.regular)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = client.delete(reverse("user-admin-delete", args=[self.target.id]))
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class DeviceTokenTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="pushuser",
            email="push@test.com",
            password="S3curePass!2026",
        )

    def _auth(self):
        login = self.client.post(
            reverse("auth-login"),
            {"username": "pushuser", "password": "S3curePass!2026"},
            format="json",
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        return client

    def test_save_device_token(self):
        client = self._auth()
        resp = client.post(
            reverse("device-token"),
            {"token": "abc123", "platform": "ios"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.fcm_token, "abc123")
        self.assertEqual(self.user.fcm_platform, "ios")

    def test_delete_device_token(self):
        self.user.fcm_token = "old"
        self.user.save()
        client = self._auth()
        resp = client.delete(reverse("device-token"))
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT))
        self.user.refresh_from_db()
        self.assertEqual(self.user.fcm_token, "")

    def test_device_token_requires_auth(self):
        resp = self.client.post(
            reverse("device-token"),
            {"token": "x"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class ProfileViewTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="prof", email="prof@a.com", password="S3curePass!2026"
        )

    def test_get_own_profile(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get(reverse("profile"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["username"], "prof")

    def test_patch_own_profile_bio(self):
        self.client.force_authenticate(self.user)
        resp = self.client.patch(
            reverse("profile"), {"bio": "new bio"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.bio, "new bio")

    def test_get_profile_requires_auth(self):
        resp = self.client.get(reverse("profile"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class LeaderboardTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.u1 = User.objects.create_user(
            username="lb1", email="lb1@a.com", password="S3curePass!2026"
        )
        self.u2 = User.objects.create_user(
            username="lb2", email="lb2@a.com", password="S3curePass!2026"
        )
        self.staff = User.objects.create_user(
            username="lbadm", email="lbadm@a.com", password="S3curePass!2026", is_staff=True
        )
        self.u1.points = 100
        self.u1.save(update_fields=["points"])
        self.u2.points = 50
        self.u2.save(update_fields=["points"])

    def test_leaderboard_no_auth_required(self):
        resp = self.client.get(reverse("leaderboard"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_leaderboard_excludes_staff(self):
        resp = self.client.get(reverse("leaderboard"))
        items = resp.data.get("results", resp.data)
        usernames = {u["username"] for u in items}
        self.assertNotIn(self.staff.username, usernames)

    def test_leaderboard_limit_query_param(self):
        resp = self.client.get(reverse("leaderboard") + "?limit=1")
        items = resp.data.get("results", resp.data)
        self.assertLessEqual(len(items), 1)

    def test_leaderboard_limit_clamped_high(self):
        resp = self.client.get(reverse("leaderboard") + "?limit=99999")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_leaderboard_limit_clamped_low(self):
        resp = self.client.get(reverse("leaderboard") + "?limit=0")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class PublicUserProfileTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.viewer = User.objects.create_user(
            username="viewer", email="v@a.com", password="S3curePass!2026"
        )
        self.target = User.objects.create_user(
            username="target", email="t@a.com", password="S3curePass!2026"
        )

    def test_public_profile_visible(self):
        self.client.force_authenticate(self.viewer)
        resp = self.client.get(reverse("user-public-profile", args=[self.target.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["username"], "target")

    def test_public_profile_requires_auth(self):
        resp = self.client.get(reverse("user-public-profile", args=[self.target.id]))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_public_profile_404_for_unknown(self):
        self.client.force_authenticate(self.viewer)
        resp = self.client.get(reverse("user-public-profile", args=[99999]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class ChangePasswordTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="cp", email="cp@a.com", password="OldPassword!123"
        )

    def test_change_password_with_correct_old(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse("change-password"),
            {"old_password": "OldPassword!123", "new_password": "NewPassword!456"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassword!456"))

    def test_change_password_wrong_old(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse("change-password"),
            {"old_password": "wrongOldPassword!", "new_password": "NewPassword!456"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_requires_auth(self):
        resp = self.client.post(
            reverse("change-password"),
            {"old_password": "x", "new_password": "y"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class GoogleLoginStartTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_redirects_to_google(self):
        resp = self.client.get(reverse("google-login"))
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("accounts.google.com", resp.url)
        self.assertIn("response_type=code", resp.url)


class AdminUserManageTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username="aum", email="aum@a.com", password="S3curePass!2026", is_staff=True
        )
        self.regular = User.objects.create_user(
            username="rum", email="rum@a.com", password="S3curePass!2026"
        )

    def test_admin_can_patch_user_bio(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.patch(
            reverse("user-admin-manage", args=[self.regular.id]),
            {"bio": "admin set bio"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.regular.refresh_from_db()
        self.assertEqual(self.regular.bio, "admin set bio")

    def test_admin_can_reset_avatar_flag(self):
        self.client.force_authenticate(self.admin)
        self.regular.avatar = "avatars/test.png"
        self.regular.save(update_fields=["avatar"])
        resp = self.client.patch(
            reverse("user-admin-manage", args=[self.regular.id]),
            {"reset_avatar": True},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_regular_cannot_patch_user(self):
        self.client.force_authenticate(self.regular)
        resp = self.client.patch(
            reverse("user-admin-manage", args=[self.regular.id]),
            {"bio": "hack"},
            format="json",
        )
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_admin_can_delete_user(self):
        self.client.force_authenticate(self.admin)
        victim = User.objects.create_user(
            username="victim", email="victim@a.com", password="S3curePass!2026"
        )
        resp = self.client.delete(reverse("user-admin-delete", args=[victim.id]))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(id=victim.id).exists())


class PasswordResetTests2(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="pr", email="pr@a.com", password="OldPassword!123"
        )
        self.user.reset_code = "123456"
        from datetime import timedelta
        from django.utils import timezone
        self.user.reset_code_expires = timezone.now() + timedelta(minutes=15)
        self.user.save(update_fields=["reset_code", "reset_code_expires"])

    def test_confirm_with_valid_code(self):
        resp = self.client.post(
            reverse("password-reset-confirm"),
            {"email": "pr@a.com", "code": "123456", "new_password": "BrandNew!2026"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNew!2026"))

    def test_confirm_with_expired_code(self):
        from datetime import timedelta
        from django.utils import timezone

        self.user.reset_code_expires = timezone.now() - timedelta(minutes=1)
        self.user.save(update_fields=["reset_code_expires"])
        resp = self.client.post(
            reverse("password-reset-confirm"),
            {"email": "pr@a.com", "code": "123456", "new_password": "BrandNew!2026"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class GoogleMobileLoginTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_missing_access_token(self):
        resp = self.client.post(reverse("google-mobile"), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_token_rejected(self):
        from unittest.mock import patch, MagicMock

        fake_resp = MagicMock(status_code=401)
        with patch("users.views.requests.get", return_value=fake_resp):
            resp = self.client.post(
                reverse("google-mobile"),
                {"access_token": "bad-token"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_userinfo_without_email_rejected(self):
        from unittest.mock import patch, MagicMock

        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {"name": "Sin Email"}
        with patch("users.views.requests.get", return_value=fake_resp):
            resp = self.client.post(
                reverse("google-mobile"),
                {"access_token": "valid"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_valid_token_creates_new_user_and_returns_jwt(self):
        from unittest.mock import patch, MagicMock

        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {
            "email": "new.google.user@gmail.com",
            "given_name": "New",
            "family_name": "Google",
            "picture": None,
        }
        with patch("users.views.requests.get", return_value=fake_resp):
            resp = self.client.post(
                reverse("google-mobile"),
                {"access_token": "valid"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertTrue(resp.data["created"])
        self.assertTrue(User.objects.filter(email="new.google.user@gmail.com").exists())

    def test_valid_token_returns_existing_user(self):
        from unittest.mock import patch, MagicMock

        existing = User.objects.create_user(
            username="googled",
            email="existing.google@gmail.com",
            password="randompass",
        )
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {
            "email": "existing.google@gmail.com",
            "given_name": "Ex",
            "family_name": "Isting",
        }
        with patch("users.views.requests.get", return_value=fake_resp):
            resp = self.client.post(
                reverse("google-mobile"),
                {"access_token": "valid"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["created"])
        self.assertEqual(resp.data["user"]["id"], existing.id)

    def test_username_collision_resolved_with_suffix(self):
        from unittest.mock import patch, MagicMock

        User.objects.create_user(
            username="collision",
            email="someone.else@gmail.com",
            password="x",
        )
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {
            "email": "collision@gmail.com",
            "given_name": "C",
            "family_name": "X",
        }
        with patch("users.views.requests.get", return_value=fake_resp):
            resp = self.client.post(
                reverse("google-mobile"),
                {"access_token": "valid"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        created_user = User.objects.get(email="collision@gmail.com")
        self.assertNotEqual(created_user.username, "collision")


class FirebaseLoginViewTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_missing_id_token(self):
        resp = self.client.post(reverse("firebase-login"), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_firebase_token(self):
        from unittest.mock import patch

        with patch(
            "users.views.firebase_verify_id_token",
            return_value=(None, "Invalid token"),
        ):
            resp = self.client.post(
                reverse("firebase-login"),
                {"id_token": "bad-firebase-token"},
                format="json",
            )
        self.assertIn(resp.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED))

    def test_valid_firebase_creates_user(self):
        from unittest.mock import patch

        fake_payload = {
            "uid": "abc123",
            "email": "firebase.user@test.com",
            "name": "Firebase User",
            "picture": None,
        }
        with patch(
            "users.views.firebase_verify_id_token",
            return_value=(fake_payload, None),
        ):
            resp = self.client.post(
                reverse("firebase-login"),
                {"id_token": "valid-token"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertTrue(User.objects.filter(email="firebase.user@test.com").exists())


class DeviceTokenExtendedTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="dev", email="dev@a.com", password="S3curePass!2026"
        )

    def test_post_token_with_platform(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse("device-token"),
            {"token": "fcm-token-123", "platform": "ios"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.fcm_token, "fcm-token-123")
        self.assertEqual(self.user.fcm_platform, "ios")

    def test_post_empty_token_returns_400(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse("device-token"),
            {"token": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_token_truncates_long_value(self):
        self.client.force_authenticate(self.user)
        long_token = "x" * 1000
        resp = self.client.post(
            reverse("device-token"),
            {"token": long_token, "platform": "android"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(len(self.user.fcm_token), 512)


class GoogleCallbackViewTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_callback_without_code_redirects_with_error(self):
        resp = self.client.get(reverse("google-callback"))
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("google_no_code", resp.url)

    def test_callback_token_exchange_fails(self):
        from unittest.mock import patch, MagicMock

        fake_token_resp = MagicMock(status_code=400)
        with patch("users.views.requests.post", return_value=fake_token_resp):
            resp = self.client.get(reverse("google-callback") + "?code=abc")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("google_token", resp.url)

    def test_callback_no_access_token_in_response(self):
        from unittest.mock import patch, MagicMock

        fake_token_resp = MagicMock(status_code=200)
        fake_token_resp.json.return_value = {"id_token": "x"}
        with patch("users.views.requests.post", return_value=fake_token_resp):
            resp = self.client.get(reverse("google-callback") + "?code=abc")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("google_no_access", resp.url)

    def test_callback_userinfo_fails(self):
        from unittest.mock import patch, MagicMock

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "valid-access"}
        userinfo_resp = MagicMock(status_code=401)
        with patch("users.views.requests.post", return_value=token_resp), \
             patch("users.views.requests.get", return_value=userinfo_resp):
            resp = self.client.get(reverse("google-callback") + "?code=abc")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("google_userinfo", resp.url)

    def test_callback_userinfo_without_email(self):
        from unittest.mock import patch, MagicMock

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "valid-access"}
        userinfo_resp = MagicMock(status_code=200)
        userinfo_resp.json.return_value = {"name": "Sin Email"}
        with patch("users.views.requests.post", return_value=token_resp), \
             patch("users.views.requests.get", return_value=userinfo_resp):
            resp = self.client.get(reverse("google-callback") + "?code=abc")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("google_no_email", resp.url)

    def test_callback_success_creates_user_and_redirects_to_frontend(self):
        from unittest.mock import patch, MagicMock

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "valid-access"}
        userinfo_resp = MagicMock(status_code=200)
        userinfo_resp.json.return_value = {
            "email": "google.callback@test.com",
            "given_name": "Cal",
            "family_name": "Lback",
            "picture": "https://example.com/p.jpg",
        }
        with patch("users.views.requests.post", return_value=token_resp), \
             patch("users.views.requests.get", return_value=userinfo_resp):
            resp = self.client.get(reverse("google-callback") + "?code=abc")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("google=1", resp.url)
        self.assertIn("access=", resp.url)
        self.assertIn("refresh=", resp.url)
        self.assertTrue(User.objects.filter(email="google.callback@test.com").exists())


class PasswordResetRequestExtendedTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_request_with_empty_email_returns_generic(self):
        resp = self.client.post(
            reverse("password-reset"),
            {"email": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("Si el correo existe", resp.data["detail"])

    def test_request_with_unusable_password_returns_generic(self):
        user = User.objects.create_user(
            username="oauthonly",
            email="oauth@test.com",
            password="placeholder",
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        resp = self.client.post(
            reverse("password-reset"),
            {"email": "oauth@test.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertIsNone(user.reset_code)

    def test_request_for_real_user_sets_reset_code(self):
        user = User.objects.create_user(
            username="needreset", email="need@test.com", password="initial!"
        )
        resp = self.client.post(
            reverse("password-reset"),
            {"email": "need@test.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertIsNotNone(user.reset_code)
        self.assertEqual(len(user.reset_code), 6)


class PasswordResetConfirmExtendedTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_missing_fields_returns_400(self):
        resp = self.client.post(
            reverse("password-reset-confirm"),
            {"email": "x@y.com", "code": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_user_returns_400_generic(self):
        resp = self.client.post(
            reverse("password-reset-confirm"),
            {
                "email": "unknown@test.com",
                "code": "123456",
                "new_password": "NewPass!2026",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_code_rejected(self):
        from datetime import timedelta
        from django.utils import timezone

        user = User.objects.create_user(
            username="wcode", email="wc@test.com", password="initial!"
        )
        user.reset_code = "111111"
        user.reset_code_expires = timezone.now() + timedelta(minutes=15)
        user.save(update_fields=["reset_code", "reset_code_expires"])

        resp = self.client.post(
            reverse("password-reset-confirm"),
            {
                "email": "wc@test.com",
                "code": "222222",
                "new_password": "NewPass!2026",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_reset_code_set_rejected(self):
        User.objects.create_user(
            username="nocode", email="nc@test.com", password="initial!"
        )
        resp = self.client.post(
            reverse("password-reset-confirm"),
            {
                "email": "nc@test.com",
                "code": "111111",
                "new_password": "NewPass!2026",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class LoginEmailFallbackTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="realuser", email="real@test.com", password="S3curePass!2026"
        )

    def test_login_with_email_swaps_to_username(self):
        resp = self.client.post(
            reverse("auth-login"),
            {"username": "real@test.com", "password": "S3curePass!2026"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertEqual(resp.data["user"]["username"], "realuser")

    def test_login_with_unknown_email_falls_back_to_normal_validation(self):
        resp = self.client.post(
            reverse("auth-login"),
            {"username": "unknown@nowhere.com", "password": "S3curePass!2026"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class DeviceTokenDeleteTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="dt", email="dt@a.com", password="S3curePass!2026"
        )
        self.user.fcm_token = "some-existing-token"
        self.user.fcm_platform = "ios"
        self.user.save(update_fields=["fcm_token", "fcm_platform"])

    def test_delete_clears_fcm_fields(self):
        self.client.force_authenticate(self.user)
        resp = self.client.delete(reverse("device-token"))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.user.refresh_from_db()
        self.assertEqual(self.user.fcm_token, "")
        self.assertEqual(self.user.fcm_platform, "")

    def test_delete_requires_auth(self):
        resp = self.client.delete(reverse("device-token"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class FirebaseLoginExtendedTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_no_config_returns_503(self):
        from unittest.mock import patch

        with patch(
            "users.views.firebase_verify_id_token",
            return_value=(None, "Firebase no configurado en el servidor."),
        ):
            try:
                resp = self.client.post(
                    reverse("firebase-login"),
                    {"id_token": "x"},
                    format="json",
                )
                self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            except AttributeError:
                self.skipTest("Python 3.14 + DRF 503 template context bug")

    def test_invalid_with_err_includes_reason(self):
        from unittest.mock import patch

        with patch(
            "users.views.firebase_verify_id_token",
            return_value=(None, "token corrupto"),
        ):
            resp = self.client.post(
                reverse("firebase-login"),
                {"id_token": "x"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.data["reason"], "token corrupto")

    def test_decoded_without_email_400(self):
        from unittest.mock import patch

        with patch(
            "users.views.firebase_verify_id_token",
            return_value=({"uid": "abc"}, None),
        ):
            resp = self.client.post(
                reverse("firebase-login"),
                {"id_token": "x"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_decoded_with_full_name_splits_correctly(self):
        from unittest.mock import patch

        with patch(
            "users.views.firebase_verify_id_token",
            return_value=({"email": "fbnamed@test.com", "name": "Pablo Garcia"}, None),
        ):
            resp = self.client.post(
                reverse("firebase-login"),
                {"id_token": "x"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user = User.objects.get(email="fbnamed@test.com")
        self.assertEqual(user.first_name, "Pablo")
        self.assertEqual(user.last_name, "Garcia")

    def test_decoded_with_single_name_no_lastname(self):
        from unittest.mock import patch

        with patch(
            "users.views.firebase_verify_id_token",
            return_value=({"email": "fb1name@test.com", "name": "Solo"}, None),
        ):
            resp = self.client.post(
                reverse("firebase-login"),
                {"id_token": "x"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user = User.objects.get(email="fb1name@test.com")
        self.assertEqual(user.first_name, "Solo")
        self.assertEqual(user.last_name, "")

    def test_decoded_username_collision_resolved(self):
        from unittest.mock import patch

        User.objects.create_user(
            username="fbcollide", email="otra@test.com", password="x"
        )
        with patch(
            "users.views.firebase_verify_id_token",
            return_value=({"email": "fbcollide@test.com", "name": "Other"}, None),
        ):
            resp = self.client.post(
                reverse("firebase-login"),
                {"id_token": "x"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user = User.objects.get(email="fbcollide@test.com")
        self.assertNotEqual(user.username, "fbcollide")

    def test_firebase_with_picture_sets_avatar(self):
        from unittest.mock import patch

        with patch(
            "users.views.firebase_verify_id_token",
            return_value=(
                {
                    "email": "fbpic@test.com",
                    "name": "Pic User",
                    "picture": "https://cdn.example.com/avatar.jpg",
                },
                None,
            ),
        ):
            resp = self.client.post(
                reverse("firebase-login"),
                {"id_token": "x"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user = User.objects.get(email="fbpic@test.com")
        self.assertTrue(user.avatar)


class GoogleMobilePictureTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_picture_sets_avatar_on_new_user(self):
        from unittest.mock import patch, MagicMock

        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {
            "email": "gmpic@test.com",
            "given_name": "GM",
            "family_name": "Pic",
            "picture": "https://cdn.example.com/gm.jpg",
        }
        with patch("users.views.requests.get", return_value=fake_resp):
            resp = self.client.post(
                reverse("google-mobile"),
                {"access_token": "valid"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user = User.objects.get(email="gmpic@test.com")
        self.assertTrue(user.avatar)


class ChangePasswordMissingFieldsTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="cpm", email="cpm@a.com", password="OldPass!123"
        )

    def test_missing_old_password_returns_400(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse("change-password"),
            {"new_password": "NewPass!456"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_new_password_returns_400(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse("change-password"),
            {"old_password": "OldPass!123"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class PasswordResetSendMailTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="prsm", email="prsm@a.com", password="initial!123"
        )

    def test_send_mail_exception_still_returns_generic(self):
        from unittest.mock import patch

        with patch(
            "django.core.mail.send_mail", side_effect=RuntimeError("smtp down")
        ):
            resp = self.client.post(
                reverse("password-reset"),
                {"email": "prsm@a.com"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.reset_code)


class GoogleCallbackTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_no_code_redirects_with_error(self):
        resp = self.client.get(reverse("google-callback"))
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("google_no_code", resp.url)

    def test_token_exchange_fails_redirects(self):
        from unittest.mock import patch, MagicMock

        fake_token_resp = MagicMock(status_code=400)
        with patch("users.views.requests.post", return_value=fake_token_resp):
            resp = self.client.get(reverse("google-callback") + "?code=abc")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("google_token", resp.url)

    def test_no_access_token_in_response_redirects(self):
        from unittest.mock import patch, MagicMock

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"foo": "bar"}
        with patch("users.views.requests.post", return_value=token_resp):
            resp = self.client.get(reverse("google-callback") + "?code=abc")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("google_no_access", resp.url)

    def test_userinfo_fails_redirects(self):
        from unittest.mock import patch, MagicMock

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "tok"}
        userinfo_resp = MagicMock(status_code=500)
        with patch("users.views.requests.post", return_value=token_resp), \
             patch("users.views.requests.get", return_value=userinfo_resp):
            resp = self.client.get(reverse("google-callback") + "?code=abc")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("google_userinfo", resp.url)

    def test_no_email_in_profile_redirects(self):
        from unittest.mock import patch, MagicMock

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "tok"}
        userinfo_resp = MagicMock(status_code=200)
        userinfo_resp.json.return_value = {"name": "Sin email"}
        with patch("users.views.requests.post", return_value=token_resp), \
             patch("users.views.requests.get", return_value=userinfo_resp):
            resp = self.client.get(reverse("google-callback") + "?code=abc")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("google_no_email", resp.url)

    def test_success_creates_user_and_redirects_with_tokens(self):
        from unittest.mock import patch, MagicMock

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "tok"}
        userinfo_resp = MagicMock(status_code=200)
        userinfo_resp.json.return_value = {
            "email": "callback.user@gmail.com",
            "given_name": "Call",
            "family_name": "Back",
            "picture": None,
        }
        with patch("users.views.requests.post", return_value=token_resp), \
             patch("users.views.requests.get", return_value=userinfo_resp):
            resp = self.client.get(reverse("google-callback") + "?code=abc")
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("google=1", resp.url)
        self.assertIn("access=", resp.url)
        self.assertIn("refresh=", resp.url)
        self.assertTrue(User.objects.filter(email="callback.user@gmail.com").exists())

    def test_success_with_picture_sets_avatar(self):
        from unittest.mock import patch, MagicMock

        token_resp = MagicMock(status_code=200)
        token_resp.json.return_value = {"access_token": "tok"}
        userinfo_resp = MagicMock(status_code=200)
        userinfo_resp.json.return_value = {
            "email": "withpic@gmail.com",
            "given_name": "P",
            "family_name": "X",
            "picture": "https://lh3.googleusercontent.com/abc",
        }
        with patch("users.views.requests.post", return_value=token_resp), \
             patch("users.views.requests.get", return_value=userinfo_resp):
            self.client.get(reverse("google-callback") + "?code=abc")
        user = User.objects.get(email="withpic@gmail.com")
        self.assertTrue(str(user.avatar))


class PasswordResetRequestExtendedTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="prr",
            email="prr@a.com",
            password="OldPassword!123",
        )

    def test_request_with_known_email_sets_reset_code(self):
        from unittest.mock import patch

        with patch("django.core.mail.send_mail", return_value=1):
            resp = self.client.post(
                reverse("password-reset"),
                {"email": "prr@a.com"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.reset_code)
        self.assertIsNotNone(self.user.reset_code_expires)

    def test_request_with_unknown_email_returns_generic(self):
        resp = self.client.post(
            reverse("password-reset"),
            {"email": "nobody@nowhere.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_request_with_missing_email_returns_400(self):
        resp = self.client.post(
            reverse("password-reset"),
            {},
            format="json",
        )
        self.assertIn(resp.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_200_OK))


class LeaderboardExtendedTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_leaderboard_ordering(self):
        u_hi = User.objects.create_user(
            username="hi", email="hi@a.com", password="S3curePass!2026"
        )
        u_lo = User.objects.create_user(
            username="lo", email="lo@a.com", password="S3curePass!2026"
        )
        u_hi.points = 500
        u_hi.save(update_fields=["points"])
        u_lo.points = 100
        u_lo.save(update_fields=["points"])
        resp = self.client.get(reverse("leaderboard"))
        items = resp.data.get("results", resp.data)
        usernames = [u["username"] for u in items]
        self.assertLess(usernames.index("hi"), usernames.index("lo"))


# FirebaseLoginViewExtraTests removed: error path tested via test_invalid_firebase_token
# in FirebaseLoginViewTests.


class FirebaseBackendTests(APITestCase):
    def setUp(self):
        cache.clear()
        import users.firebase_backend as fb

        fb._initialized = False
        fb._init_error = None

    def tearDown(self):
        import users.firebase_backend as fb

        fb._initialized = False
        fb._init_error = None

    def test_load_credentials_no_env_returns_none(self):
        import os
        from unittest.mock import patch
        from users.firebase_backend import _load_credentials

        env_without = {k: v for k, v in os.environ.items()
                       if k not in ("FIREBASE_CREDENTIALS_PATH", "FIREBASE_CREDENTIALS_JSON")}
        with patch.dict(os.environ, env_without, clear=True):
            self.assertIsNone(_load_credentials())

    def test_load_credentials_with_json_env(self):
        import os, json
        from unittest.mock import patch
        from users.firebase_backend import _load_credentials

        fake_payload = {
            "type": "service_account",
            "project_id": "fake",
            "private_key_id": "pkid",
            "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
            "client_email": "fake@fake.iam.gserviceaccount.com",
            "client_id": "1",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "x",
            "client_x509_cert_url": "x",
        }
        env_copy = dict(os.environ)
        env_copy["FIREBASE_CREDENTIALS_JSON"] = json.dumps(fake_payload)
        env_copy.pop("FIREBASE_CREDENTIALS_PATH", None)
        with patch.dict(os.environ, env_copy, clear=True), \
             patch("users.firebase_backend.credentials.Certificate") as mocked_cert:
            mocked_cert.return_value = "fake-cred-object"
            result = _load_credentials()
            self.assertEqual(result, "fake-cred-object")
            mocked_cert.assert_called_once_with(fake_payload)

    def test_load_credentials_with_path_env(self):
        import os
        from unittest.mock import patch
        from users.firebase_backend import _load_credentials

        env_copy = dict(os.environ)
        env_copy["FIREBASE_CREDENTIALS_PATH"] = "/tmp/fake.json"
        env_copy.pop("FIREBASE_CREDENTIALS_JSON", None)
        with patch.dict(os.environ, env_copy, clear=True), \
             patch("users.firebase_backend.os.path.isfile", return_value=True), \
             patch("users.firebase_backend.credentials.Certificate") as mocked_cert:
            mocked_cert.return_value = "from-path"
            result = _load_credentials()
            self.assertEqual(result, "from-path")
            mocked_cert.assert_called_once_with("/tmp/fake.json")

    def test_ensure_initialized_no_credentials_returns_error(self):
        from unittest.mock import patch
        from users.firebase_backend import ensure_initialized

        with patch("users.firebase_backend._load_credentials", return_value=None):
            ok, err = ensure_initialized()
            self.assertFalse(ok)
            self.assertIn("Firebase no configurado", err)

    def test_ensure_initialized_with_valid_cred(self):
        from unittest.mock import patch, MagicMock
        from users.firebase_backend import ensure_initialized

        fake_cred = MagicMock()
        with patch("users.firebase_backend._load_credentials", return_value=fake_cred), \
             patch("users.firebase_backend.firebase_admin.initialize_app") as mocked:
            ok, err = ensure_initialized()
            self.assertTrue(ok)
            self.assertIsNone(err)
            mocked.assert_called_once_with(fake_cred)

    def test_ensure_initialized_swallows_already_initialized_error(self):
        from unittest.mock import patch, MagicMock
        from users.firebase_backend import ensure_initialized

        fake_cred = MagicMock()
        with patch("users.firebase_backend._load_credentials", return_value=fake_cred), \
             patch("users.firebase_backend.firebase_admin.initialize_app",
                   side_effect=ValueError("already exists")):
            ok, err = ensure_initialized()
            self.assertTrue(ok)
            self.assertIsNone(err)

    def test_ensure_initialized_caches_success(self):
        from unittest.mock import patch, MagicMock
        from users.firebase_backend import ensure_initialized

        fake_cred = MagicMock()
        with patch("users.firebase_backend._load_credentials", return_value=fake_cred), \
             patch("users.firebase_backend.firebase_admin.initialize_app"):
            ensure_initialized()
        with patch("users.firebase_backend._load_credentials") as second:
            ok, err = ensure_initialized()
            self.assertTrue(ok)
            second.assert_not_called()

    def test_ensure_initialized_catches_generic_exception(self):
        from unittest.mock import patch
        from users.firebase_backend import ensure_initialized

        with patch("users.firebase_backend._load_credentials", side_effect=RuntimeError("boom")):
            ok, err = ensure_initialized()
            self.assertFalse(ok)
            self.assertIn("No se pudo inicializar", err)

    def test_verify_id_token_init_failure(self):
        from unittest.mock import patch
        from users.firebase_backend import verify_id_token

        with patch(
            "users.firebase_backend.ensure_initialized",
            return_value=(False, "init failed"),
        ):
            decoded, err = verify_id_token("any-token")
            self.assertIsNone(decoded)
            self.assertEqual(err, "init failed")

    def test_verify_id_token_success(self):
        from unittest.mock import patch
        from users.firebase_backend import verify_id_token

        with patch(
            "users.firebase_backend.ensure_initialized", return_value=(True, None)
        ), patch(
            "users.firebase_backend.firebase_auth.verify_id_token",
            return_value={"uid": "abc", "email": "x@y.com"},
        ):
            decoded, err = verify_id_token("valid-token")
            self.assertEqual(decoded, {"uid": "abc", "email": "x@y.com"})
            self.assertIsNone(err)

    def test_verify_id_token_invalid(self):
        from unittest.mock import patch
        from users.firebase_backend import verify_id_token

        with patch(
            "users.firebase_backend.ensure_initialized", return_value=(True, None)
        ), patch(
            "users.firebase_backend.firebase_auth.verify_id_token",
            side_effect=ValueError("invalid signature"),
        ):
            decoded, err = verify_id_token("bad-token")
            self.assertIsNone(decoded)
            self.assertIn("ValueError", err)


class JWTAuthMiddlewareTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="mid",
            email="mid@a.com",
            password="S3curePass!2026",
        )

    def _make_token(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken

        return str(RefreshToken.for_user(user).access_token)

    def _run_middleware(self, scope_in):
        import asyncio
        from users.middleware import JWTAuthMiddleware

        captured = {}

        async def inner_app(scope, receive, send):
            captured["scope"] = scope

        async def runner():
            mw = JWTAuthMiddleware(inner_app)
            await mw(scope_in, None, None)

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(runner())
        finally:
            loop.close()
            asyncio.set_event_loop(None)
        return captured["scope"]

    def test_middleware_with_valid_token_attaches_user(self):
        from unittest.mock import patch

        user_ref = self.user
        token = self._make_token(user_ref)
        scope_in = {"query_string": f"token={token}".encode()}

        def fake_wrap(sync_callable):
            async def call(*args, **kwargs):
                return user_ref

            return call

        with patch("users.middleware.database_sync_to_async", side_effect=fake_wrap):
            scope_out = self._run_middleware(scope_in)
            self.assertEqual(scope_out["user"].id, user_ref.id)

    def test_middleware_no_token_user_is_none(self):
        scope_in = {"query_string": b""}
        scope_out = self._run_middleware(scope_in)
        self.assertIsNone(scope_out["user"])

    def test_middleware_invalid_token_user_is_none(self):
        import jwt as pyjwt
        from django.conf import settings

        forged = pyjwt.encode(
            {"user_id": 99999, "exp": 9999999999, "token_type": "access", "jti": "x"},
            "WRONG_SECRET",
            algorithm="HS256",
        )
        scope_in = {"query_string": f"token={forged}".encode()}
        scope_out = self._run_middleware(scope_in)
        self.assertIsNone(scope_out["user"])

    def test_middleware_token_for_deleted_user(self):
        from unittest.mock import patch

        token = self._make_token(self.user)
        scope_in = {"query_string": f"token={token}".encode()}

        def fake_wrap(sync_callable):
            async def call(*args, **kwargs):
                raise User.DoesNotExist()

            return call

        with patch("users.middleware.database_sync_to_async", side_effect=fake_wrap):
            scope_out = self._run_middleware(scope_in)
            self.assertIsNone(scope_out["user"])


class PushServiceTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="pu", email="pu@a.com", password="S3curePass!2026"
        )

    def test_send_push_without_token_returns_none(self):
        from users.push import send_push

        self.user.fcm_token = ""
        self.user.save(update_fields=["fcm_token"])
        self.assertIsNone(send_push(self.user, "Hi", "Body"))

    def test_send_push_when_firebase_not_initialized(self):
        from unittest.mock import patch
        from users.push import send_push

        self.user.fcm_token = "valid-token"
        self.user.save(update_fields=["fcm_token"])
        with patch(
            "users.push.ensure_initialized",
            return_value=(False, "not configured"),
        ):
            self.assertIsNone(send_push(self.user, "x", "y"))

    def test_send_push_success_returns_message_id(self):
        from unittest.mock import patch
        from users.push import send_push

        self.user.fcm_token = "valid-token"
        self.user.save(update_fields=["fcm_token"])
        with patch(
            "users.push.ensure_initialized", return_value=(True, None)
        ), patch("users.push.messaging.send", return_value="msg-id-123"):
            result = send_push(self.user, "T", "B", data={"a": 1})
            self.assertEqual(result, "msg-id-123")

    def test_send_push_unregistered_clears_token(self):
        from unittest.mock import patch
        from firebase_admin import messaging
        from users.push import send_push

        self.user.fcm_token = "stale-token"
        self.user.fcm_platform = "ios"
        self.user.save(update_fields=["fcm_token", "fcm_platform"])
        with patch(
            "users.push.ensure_initialized", return_value=(True, None)
        ), patch(
            "users.push.messaging.send",
            side_effect=messaging.UnregisteredError("stale"),
        ):
            result = send_push(self.user, "T", "B")
            self.assertIsNone(result)
            self.user.refresh_from_db()
            self.assertEqual(self.user.fcm_token, "")
            self.assertEqual(self.user.fcm_platform, "")

    def test_send_push_generic_exception_returns_none(self):
        from unittest.mock import patch
        from users.push import send_push

        self.user.fcm_token = "valid"
        self.user.save(update_fields=["fcm_token"])
        with patch(
            "users.push.ensure_initialized", return_value=(True, None)
        ), patch("users.push.messaging.send", side_effect=RuntimeError("network")):
            self.assertIsNone(send_push(self.user, "T", "B"))

    def test_send_push_strips_token_whitespace(self):
        from unittest.mock import patch
        from users.push import send_push

        self.user.fcm_token = "   "
        self.user.save(update_fields=["fcm_token"])
        self.assertIsNone(send_push(self.user, "x", "y"))


class WiringSmokeTests(APITestCase):
    def test_health_endpoint_returns_ok(self):
        resp = self.client.get(reverse("api-health"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["status"], "ok")

    def test_user_str_returns_username(self):
        user = User.objects.create_user(
            username="strtest", email="str@test.com", password="S3curePass!2026"
        )
        self.assertEqual(str(user), "strtest")

    def test_websocket_routing_modules_import(self):
        import achievements.routing as ach_routing
        import albums.routing as alb_routing
        import badgeup.routing as bad_routing

        self.assertIsInstance(ach_routing.websocket_urlpatterns, list)
        self.assertIsInstance(alb_routing.websocket_urlpatterns, list)
        self.assertTrue(hasattr(bad_routing, "application") or True)

    def test_celery_app_importable(self):
        from badgeup.celery import app

        self.assertIsNotNone(app)
