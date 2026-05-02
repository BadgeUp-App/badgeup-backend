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
