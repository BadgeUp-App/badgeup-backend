from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

User = get_user_model()


class AlbumPermissionTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.regular = User.objects.create_user(
            username="reg", email="r@a.com", password="S3curePass!2026"
        )
        self.admin = User.objects.create_user(
            username="adm", email="a@a.com", password="S3curePass!2026", is_staff=True
        )

    def _auth(self, user):
        login = self.client.post(
            reverse("auth-login"),
            {"username": user.username, "password": "S3curePass!2026"},
            format="json",
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        return client

    def test_anyone_authenticated_can_list(self):
        client = self._auth(self.regular)
        resp = client.get(reverse("album-list-create"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_unauthenticated_cannot_list(self):
        resp = self.client.get(reverse("album-list-create"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_cannot_create_album(self):
        client = self._auth(self.regular)
        resp = client.post(
            reverse("album-list-create"),
            {"title": "Hack", "description": "x", "theme": "x"},
            format="multipart",
        )
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_admin_can_create_album(self):
        client = self._auth(self.admin)
        resp = client.post(
            reverse("album-list-create"),
            {"title": "OK", "description": "x", "theme": "x"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class ScanTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="scanner", email="s@s.com", password="S3curePass!2026"
        )

    def test_scan_requires_auth(self):
        resp = self.client.post(reverse("global-scan"), {}, format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class StickerLocationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user_a = User.objects.create_user(
            username="usera", email="ua@a.com", password="S3curePass!2026"
        )
        self.user_b = User.objects.create_user(
            username="userb", email="ub@b.com", password="S3curePass!2026"
        )

    def _auth(self, user):
        login = self.client.post(
            reverse("auth-login"),
            {"username": user.username, "password": "S3curePass!2026"},
            format="json",
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        return client

    def test_locations_isolated_per_user(self):
        client_a = self._auth(self.user_a)
        resp_a = client_a.get(reverse("sticker-locations"))
        self.assertEqual(resp_a.status_code, status.HTTP_200_OK)

    def test_locations_unauth(self):
        resp = self.client.get(reverse("sticker-locations"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class ScanQuotaTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.free = User.objects.create_user(
            username="free", email="free@a.com", password="S3curePass!2026"
        )
        self.premium = User.objects.create_user(
            username="prem", email="prem@a.com", password="S3curePass!2026", is_premium=True
        )
        self.staff = User.objects.create_user(
            username="adm2", email="adm2@a.com", password="S3curePass!2026", is_staff=True
        )

    def _auth(self, user):
        login = self.client.post(
            reverse("auth-login"),
            {"username": user.username, "password": "S3curePass!2026"},
            format="json",
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        return client

    def test_free_default_quota_endpoint(self):
        client = self._auth(self.free)
        resp = client.get(reverse("scan-quota"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["limit"], 5)
        self.assertEqual(resp.data["used"], 0)
        self.assertEqual(resp.data["remaining"], 5)
        self.assertFalse(resp.data["unlimited"])

    def test_premium_quota_unlimited(self):
        client = self._auth(self.premium)
        resp = client.get(reverse("scan-quota"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["unlimited"])
        self.assertIsNone(resp.data["limit"])

    def test_staff_quota_unlimited(self):
        client = self._auth(self.staff)
        resp = client.get(reverse("scan-quota"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["unlimited"])

    def test_quota_unauth(self):
        resp = self.client.get(reverse("scan-quota"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reserve_increments_and_blocks(self):
        from albums.quota import reserve_scan

        for i in range(5):
            allowed, info = reserve_scan(self.free)
            self.assertTrue(allowed, f"call {i+1} should be allowed")
            self.assertEqual(info["used"], i + 1)
            self.assertEqual(info["remaining"], 5 - (i + 1))
        allowed, info = reserve_scan(self.free)
        self.assertFalse(allowed)
        self.assertEqual(info["remaining"], 0)
        self.assertEqual(info["used"], 5)

    def test_reserve_premium_never_blocks(self):
        from albums.quota import reserve_scan

        for _ in range(20):
            allowed, info = reserve_scan(self.premium)
            self.assertTrue(allowed)
            self.assertTrue(info["unlimited"])

    def test_reserve_staff_never_blocks(self):
        from albums.quota import reserve_scan

        for _ in range(20):
            allowed, info = reserve_scan(self.staff)
            self.assertTrue(allowed)
            self.assertTrue(info["unlimited"])

    def test_premium_expired_falls_back_to_free(self):
        from datetime import timedelta
        from django.utils import timezone
        from albums.quota import reserve_scan

        self.premium.premium_until = timezone.now() - timedelta(days=1)
        self.premium.save(update_fields=["premium_until"])
        for _ in range(5):
            allowed, _ = reserve_scan(self.premium)
            self.assertTrue(allowed)
        allowed, info = reserve_scan(self.premium)
        self.assertFalse(allowed)

    def test_quota_resets_per_user(self):
        from albums.quota import reserve_scan

        other = User.objects.create_user(
            username="other", email="other@a.com", password="S3curePass!2026"
        )
        for _ in range(5):
            reserve_scan(self.free)
        allowed, _ = reserve_scan(other)
        self.assertTrue(allowed)
