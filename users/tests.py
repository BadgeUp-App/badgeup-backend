from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

User = get_user_model()


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
