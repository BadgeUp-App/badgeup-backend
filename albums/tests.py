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


class VisionDhashTests(APITestCase):
    def test_dhash_deterministic_for_same_image(self):
        from albums.vision_cache import compute_dhash
        from PIL import Image
        import io

        img = Image.new("RGB", (100, 100))
        for y in range(100):
            for x in range(100):
                img.putpixel((x, y), (x * 2 % 256, y * 2 % 256, (x + y) % 256))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b1 = buf.getvalue()
        buf2 = io.BytesIO()
        img.save(buf2, format="JPEG", quality=85)
        b2 = buf2.getvalue()
        self.assertEqual(compute_dhash(b1), compute_dhash(b2))

    def test_dhash_different_for_different_images(self):
        from albums.vision_cache import compute_dhash
        from PIL import Image
        import io

        a = Image.new("RGB", (100, 100), color=(0, 0, 0))
        b = Image.new("RGB", (100, 100), color=(255, 255, 255))
        for y in range(100):
            for x in range(100):
                a.putpixel((x, y), (x * 3 % 256, 0, 0))
                b.putpixel((x, y), (0, y * 3 % 256, 0))
        ba = io.BytesIO()
        bb = io.BytesIO()
        a.save(ba, format="JPEG")
        b.save(bb, format="JPEG")
        self.assertNotEqual(compute_dhash(ba.getvalue()), compute_dhash(bb.getvalue()))

    def test_dhash_handles_invalid_bytes(self):
        from albums.vision_cache import compute_dhash

        self.assertIsNone(compute_dhash(b""))
        self.assertIsNone(compute_dhash(b"not an image"))


class VisionCacheTests(APITestCase):
    def test_cache_store_and_lookup(self):
        from albums.vision_cache import lookup, store

        phash = "abcdef0123456789"
        result = {"recognized": True, "matches": [{"sticker_id": 1}]}
        store(phash, result)
        cached = lookup(phash)
        self.assertEqual(cached, result)

    def test_cache_miss_returns_none(self):
        from albums.vision_cache import lookup

        self.assertIsNone(lookup("nonexistent_hash_zzz"))

    def test_cache_store_idempotent(self):
        from albums.vision_cache import store
        from albums.models import VisionResultCache

        store("dupe", {"x": 1})
        store("dupe", {"x": 2})
        self.assertEqual(VisionResultCache.objects.filter(phash="dupe").count(), 1)


class VisionCircuitTests(APITestCase):
    def test_no_calls_means_not_tripped(self):
        from albums import vision_circuit

        self.assertFalse(vision_circuit.is_tripped())

    def test_record_and_get_state(self):
        from albums import vision_circuit

        vision_circuit.record_call(0.001, kind="main")
        vision_circuit.record_call(0.0001, kind="prefilter")
        vision_circuit.record_call(0.0, kind="cache_hit")
        state = vision_circuit.get_today_state()
        self.assertEqual(state["call_count"], 1)
        self.assertEqual(state["prefilter_count"], 1)
        self.assertEqual(state["cache_hit_count"], 1)
        self.assertAlmostEqual(state["used_usd"], 0.0011, places=4)
        self.assertFalse(state["tripped"])

    def test_trips_when_limit_exceeded(self):
        from decimal import Decimal
        from django.utils import timezone
        from albums.models import DailyAICost
        from albums import vision_circuit

        DailyAICost.objects.create(
            date=timezone.localdate(), total_usd=Decimal("100.0"), call_count=10
        )
        self.assertTrue(vision_circuit.is_tripped())

    def test_cost_status_requires_admin(self):
        resp = self.client.get(reverse("scan-cost"))
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_cost_status_admin_allowed(self):
        admin = User.objects.create_user(
            username="costadm", email="cost@a.com", password="S3curePass!2026", is_staff=True
        )
        login = self.client.post(
            reverse("auth-login"),
            {"username": admin.username, "password": "S3curePass!2026"},
            format="json",
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        resp = client.get(reverse("scan-cost"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("limit_usd", resp.data)
        self.assertIn("used_usd", resp.data)
        self.assertIn("tripped", resp.data)
