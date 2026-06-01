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


class QuotaEdgeCaseTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="edge", email="edge@a.com", password="S3curePass!2026"
        )

    def test_anonymous_user_returns_zero_limit(self):
        from django.contrib.auth.models import AnonymousUser
        from albums.quota import get_daily_limit

        self.assertEqual(get_daily_limit(AnonymousUser()), 0)

    def test_none_user_returns_zero_limit(self):
        from albums.quota import get_daily_limit

        self.assertEqual(get_daily_limit(None), 0)

    def test_premium_with_no_expiration_is_unlimited(self):
        from albums.quota import get_daily_limit

        self.user.is_premium = True
        self.user.premium_until = None
        self.user.save(update_fields=["is_premium", "premium_until"])
        self.assertIsNone(get_daily_limit(self.user))

    def test_premium_with_future_expiration_is_unlimited(self):
        from datetime import timedelta
        from django.utils import timezone
        from albums.quota import get_daily_limit

        self.user.is_premium = True
        self.user.premium_until = timezone.now() + timedelta(days=30)
        self.user.save(update_fields=["is_premium", "premium_until"])
        self.assertIsNone(get_daily_limit(self.user))

    def test_get_remaining_unlimited_for_premium(self):
        from albums.quota import get_remaining

        self.user.is_premium = True
        self.user.save(update_fields=["is_premium"])
        info = get_remaining(self.user)
        self.assertTrue(info["unlimited"])
        self.assertIsNone(info["limit"])
        self.assertIsNone(info["remaining"])

    def test_get_remaining_with_prior_usage(self):
        from albums.models import ScanQuotaUsage
        from django.utils import timezone
        from albums.quota import get_remaining

        ScanQuotaUsage.objects.create(user=self.user, date=timezone.localdate(), count=3)
        info = get_remaining(self.user)
        self.assertEqual(info["used"], 3)
        self.assertEqual(info["remaining"], 2)
        self.assertIn("reset_at", info)

    def test_next_reset_format_is_iso(self):
        from albums.quota import _next_reset

        out = _next_reset()
        self.assertIsInstance(out, str)
        self.assertIn("T", out)


class VisionCacheEdgeTests(APITestCase):
    def test_compute_dhash_none_input(self):
        from albums.vision_cache import compute_dhash

        self.assertIsNone(compute_dhash(None))

    def test_compute_dhash_handles_pil_error(self):
        from albums.vision_cache import compute_dhash

        self.assertIsNone(compute_dhash(b"\x00\x01\x02not an image"))

    def test_lookup_with_empty_phash_returns_none(self):
        from albums.vision_cache import lookup

        self.assertIsNone(lookup(""))
        self.assertIsNone(lookup(None))

    def test_lookup_when_disabled_returns_none(self):
        from django.test import override_settings
        from albums.vision_cache import lookup, store

        store("disabled_test", {"x": 1})
        with override_settings(VISION_CACHE_ENABLED=False):
            self.assertIsNone(lookup("disabled_test"))

    def test_store_with_empty_phash_is_noop(self):
        from albums.vision_cache import store
        from albums.models import VisionResultCache

        before = VisionResultCache.objects.count()
        store("", {"x": 1})
        store(None, {"x": 1})
        self.assertEqual(VisionResultCache.objects.count(), before)

    def test_store_with_empty_result_is_noop(self):
        from albums.vision_cache import store
        from albums.models import VisionResultCache

        before = VisionResultCache.objects.count()
        store("hash", {})
        store("hash", None)
        self.assertEqual(VisionResultCache.objects.count(), before)

    def test_lookup_increments_hit_count(self):
        from albums.vision_cache import store, lookup
        from albums.models import VisionResultCache

        store("hitter", {"x": 1})
        for _ in range(3):
            lookup("hitter")
        row = VisionResultCache.objects.get(phash="hitter")
        self.assertEqual(row.hit_count, 3)

    def test_lookup_swallows_db_exception(self):
        from unittest.mock import patch
        from albums.vision_cache import lookup

        with patch(
            "albums.vision_cache.VisionResultCache.objects"
        ) as mocked:
            mocked.select_for_update.side_effect = RuntimeError("db boom")
            self.assertIsNone(lookup("nonexistent_phash"))

    def test_store_swallows_db_exception(self):
        from unittest.mock import patch
        from albums.vision_cache import store

        with patch(
            "albums.vision_cache.VisionResultCache.objects"
        ) as mocked:
            mocked.get_or_create.side_effect = RuntimeError("db boom")
            store("any_phash", {"x": 1})


class VisionCircuitEdgeTests(APITestCase):
    def test_get_daily_limit_usd_default(self):
        from decimal import Decimal
        from django.test import override_settings
        from albums.vision_circuit import get_daily_limit_usd

        with override_settings(OPENAI_DAILY_COST_LIMIT_USD="50.0"):
            self.assertEqual(get_daily_limit_usd(), Decimal("50.0"))

    def test_get_daily_limit_usd_invalid_falls_back(self):
        from decimal import Decimal
        from django.test import override_settings
        from albums.vision_circuit import get_daily_limit_usd

        with override_settings(OPENAI_DAILY_COST_LIMIT_USD="not-a-number"):
            self.assertEqual(get_daily_limit_usd(), Decimal("20.0"))

    def test_get_today_state_with_no_row(self):
        from albums import vision_circuit

        state = vision_circuit.get_today_state()
        self.assertEqual(state["used_usd"], 0.0)
        self.assertEqual(state["call_count"], 0)
        self.assertFalse(state["tripped"])

    def test_get_today_state_with_existing_row(self):
        from decimal import Decimal
        from django.utils import timezone
        from albums.models import DailyAICost
        from albums import vision_circuit

        DailyAICost.objects.create(
            date=timezone.localdate(),
            total_usd=Decimal("1.5"),
            call_count=10,
            prefilter_count=5,
            cache_hit_count=3,
        )
        state = vision_circuit.get_today_state()
        self.assertEqual(state["used_usd"], 1.5)
        self.assertEqual(state["call_count"], 10)
        self.assertEqual(state["prefilter_count"], 5)
        self.assertEqual(state["cache_hit_count"], 3)
        self.assertGreater(state["remaining_usd"], 0)

    def test_record_call_swallows_exception(self):
        from unittest.mock import patch
        from albums import vision_circuit

        with patch(
            "albums.vision_circuit.DailyAICost.objects"
        ) as mocked:
            mocked.select_for_update.side_effect = RuntimeError("db boom")
            vision_circuit.record_call(0.001, kind="main")

    def test_get_daily_limit_usd_decimal_fallback_on_invalid_object(self):
        from decimal import Decimal
        from django.test import override_settings
        from albums.vision_circuit import get_daily_limit_usd

        with override_settings(OPENAI_DAILY_COST_LIMIT_USD=object()):
            self.assertEqual(get_daily_limit_usd(), Decimal("20.0"))

    def test_record_call_unknown_kind_only_updates_total(self):
        from django.utils import timezone
        from albums import vision_circuit
        from albums.models import DailyAICost

        vision_circuit.record_call(0.5, kind="unknown")
        row = DailyAICost.objects.get(date=timezone.localdate())
        self.assertEqual(row.call_count, 0)
        self.assertEqual(row.prefilter_count, 0)
        self.assertEqual(row.cache_hit_count, 0)
        self.assertAlmostEqual(float(row.total_usd), 0.5, places=4)


class AlbumCRUDTests(APITestCase):
    def setUp(self):
        self.regular = User.objects.create_user(
            username="reg2", email="reg2@a.com", password="S3curePass!2026"
        )
        self.admin = User.objects.create_user(
            username="adm3", email="adm3@a.com", password="S3curePass!2026", is_staff=True
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

    def _create_album(self, title="Album X", theme="test"):
        from albums.models import Album

        return Album.objects.create(title=title, theme=theme, description="desc")

    def test_album_list_includes_stickers_count(self):
        from albums.models import Sticker

        album = self._create_album()
        Sticker.objects.create(album=album, name="s1")
        Sticker.objects.create(album=album, name="s2")
        client = self._auth(self.regular)
        resp = client.get(reverse("album-list-create"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(len(resp.data["results"]) >= 1)

    def test_album_detail_get(self):
        album = self._create_album(title="DetailTest")
        client = self._auth(self.regular)
        resp = client.get(reverse("album-detail", args=[album.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["title"], "DetailTest")

    def test_album_detail_admin_can_patch(self):
        album = self._create_album(title="OldTitle")
        client = self._auth(self.admin)
        resp = client.patch(
            reverse("album-detail", args=[album.id]),
            {"title": "NewTitle"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        album.refresh_from_db()
        self.assertEqual(album.title, "NewTitle")

    def test_album_detail_regular_cannot_patch(self):
        album = self._create_album()
        client = self._auth(self.regular)
        resp = client.patch(
            reverse("album-detail", args=[album.id]),
            {"title": "Hack"},
            format="json",
        )
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class StickerCRUDTests(APITestCase):
    def setUp(self):
        from albums.models import Album

        self.regular = User.objects.create_user(
            username="r4", email="r4@a.com", password="S3curePass!2026"
        )
        self.admin = User.objects.create_user(
            username="a4", email="a4@a.com", password="S3curePass!2026", is_staff=True
        )
        self.album = Album.objects.create(title="A1", theme="t", description="d")

    def _auth(self, user):
        login = self.client.post(
            reverse("auth-login"),
            {"username": user.username, "password": "S3curePass!2026"},
            format="json",
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        return client

    def test_list_stickers_filtered_by_album(self):
        from albums.models import Album, Sticker

        other = Album.objects.create(title="A2", theme="t")
        Sticker.objects.create(album=self.album, name="mine")
        Sticker.objects.create(album=other, name="other")
        client = self._auth(self.regular)
        resp = client.get(reverse("sticker-list-create") + f"?album={self.album.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = [s["name"] for s in resp.data["results"]]
        self.assertIn("mine", names)
        self.assertNotIn("other", names)

    def test_sticker_detail_get(self):
        from albums.models import Sticker

        sticker = Sticker.objects.create(album=self.album, name="solo")
        client = self._auth(self.regular)
        resp = client.get(reverse("sticker-detail", args=[sticker.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["name"], "solo")

    def test_sticker_admin_can_patch(self):
        from albums.models import Sticker

        sticker = Sticker.objects.create(album=self.album, name="old")
        client = self._auth(self.admin)
        resp = client.patch(
            reverse("sticker-detail", args=[sticker.id]),
            {"name": "renamed"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        sticker.refresh_from_db()
        self.assertEqual(sticker.name, "renamed")

    def test_sticker_regular_cannot_create(self):
        client = self._auth(self.regular)
        resp = client.post(
            reverse("sticker-list-create"),
            {"album": self.album.id, "name": "hack"},
            format="multipart",
        )
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_sticker_admin_can_create_triggers_notification(self):
        from unittest.mock import patch
        from albums.models import Sticker

        client = self._auth(self.admin)
        with patch("albums.views.send_notification") as mocked:
            resp = client.post(
                reverse("sticker-list-create"),
                {
                    "album": self.album.id,
                    "name": "new-sticker",
                    "rarity": "common",
                    "description": "x",
                },
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Sticker.objects.filter(name="new-sticker").exists())
        mocked.assert_called_once()

    def test_sticker_admin_create_swallows_notification_failure(self):
        from unittest.mock import patch
        from albums.models import Sticker

        client = self._auth(self.admin)
        with patch("albums.views.send_notification", side_effect=RuntimeError("no channels")):
            resp = client.post(
                reverse("sticker-list-create"),
                {
                    "album": self.album.id,
                    "name": "robust-sticker",
                    "rarity": "common",
                    "description": "x",
                },
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class StickerMessageTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker

        self.user = User.objects.create_user(
            username="msguser", email="msg@a.com", password="S3curePass!2026"
        )
        self.album = Album.objects.create(title="MsgA", theme="t", description="d")
        self.sticker = Sticker.objects.create(album=self.album, name="msgsticker")

    def _auth(self):
        login = self.client.post(
            reverse("auth-login"),
            {"username": self.user.username, "password": "S3curePass!2026"},
            format="json",
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        return client

    def test_post_message_creates_or_updates_user_sticker(self):
        from achievements.models import UserSticker

        client = self._auth()
        resp = client.post(
            reverse("sticker-message", args=[self.sticker.id]),
            {"message": "esto es mio"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        us = UserSticker.objects.get(user=self.user, sticker=self.sticker)
        self.assertEqual(us.user_message, "esto es mio")

    def test_message_strips_whitespace(self):
        from achievements.models import UserSticker

        client = self._auth()
        client.post(
            reverse("sticker-message", args=[self.sticker.id]),
            {"message": "   trimmed   "},
            format="json",
        )
        us = UserSticker.objects.get(user=self.user, sticker=self.sticker)
        self.assertEqual(us.user_message, "trimmed")

    def test_message_endpoint_requires_auth(self):
        resp = self.client.post(
            reverse("sticker-message", args=[self.sticker.id]),
            {"message": "x"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_message_returns_404_for_missing_sticker(self):
        client = self._auth()
        resp = client.post(
            reverse("sticker-message", args=[99999]),
            {"message": "x"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class ScanLogListTests(APITestCase):
    def setUp(self):
        from albums.models import Album, ScanLog

        self.user_a = User.objects.create_user(
            username="loga", email="loga@a.com", password="S3curePass!2026"
        )
        self.user_b = User.objects.create_user(
            username="logb", email="logb@a.com", password="S3curePass!2026"
        )
        self.admin = User.objects.create_user(
            username="logadm", email="logadm@a.com", password="S3curePass!2026", is_staff=True
        )
        ScanLog.objects.create(user=self.user_a, detected_items="x1", matched=True)
        ScanLog.objects.create(user=self.user_a, detected_items="x2", matched=False)
        ScanLog.objects.create(user=self.user_b, detected_items="y1", matched=True)

    def _auth(self, user):
        login = self.client.post(
            reverse("auth-login"),
            {"username": user.username, "password": "S3curePass!2026"},
            format="json",
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        return client

    def test_regular_user_sees_only_own_logs(self):
        client = self._auth(self.user_a)
        resp = client.get(reverse("scan-log-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        items = resp.data.get("results", resp.data)
        for entry in items:
            self.assertEqual(entry["username"], self.user_a.username)

    def test_admin_sees_all_logs(self):
        client = self._auth(self.admin)
        resp = client.get(reverse("scan-log-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        items = resp.data.get("results", resp.data)
        usernames = {entry["username"] for entry in items}
        self.assertIn(self.user_a.username, usernames)
        self.assertIn(self.user_b.username, usernames)

    def test_filter_matched_true(self):
        client = self._auth(self.user_a)
        resp = client.get(reverse("scan-log-list") + "?matched=true")
        items = resp.data.get("results", resp.data)
        self.assertTrue(all(entry["matched"] for entry in items))

    def test_filter_matched_false(self):
        client = self._auth(self.user_a)
        resp = client.get(reverse("scan-log-list") + "?matched=false")
        items = resp.data.get("results", resp.data)
        self.assertTrue(all(not entry["matched"] for entry in items))

    def test_scan_log_requires_auth(self):
        resp = self.client.get(reverse("scan-log-list"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class StickerReferenceUploadTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker

        self.admin = User.objects.create_user(
            username="refadm", email="refadm@a.com", password="S3curePass!2026", is_staff=True
        )
        self.regular = User.objects.create_user(
            username="reffer", email="reffer@a.com", password="S3curePass!2026"
        )
        self.album = Album.objects.create(title="RefA", theme="t", description="d")
        self.sticker = Sticker.objects.create(album=self.album, name="needs-refs")

    def _auth(self, user):
        login = self.client.post(
            reverse("auth-login"),
            {"username": user.username, "password": "S3curePass!2026"},
            format="json",
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        return client

    def _fake_image(self, name="ref.jpg"):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io

        img = Image.new("RGB", (10, 10), color=(50, 50, 50))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")

    def test_upload_creates_reference_photos(self):
        from albums.models import StickerReferencePhoto

        client = self._auth(self.admin)
        resp = client.post(
            reverse("sticker-references", args=[self.sticker.id]),
            {"photos": [self._fake_image("a.jpg"), self._fake_image("b.jpg")], "label": "lab1"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["uploaded"], 2)
        self.assertEqual(StickerReferencePhoto.objects.filter(sticker=self.sticker).count(), 2)

    def test_upload_no_photos_returns_400(self):
        client = self._auth(self.admin)
        resp = client.post(
            reverse("sticker-references", args=[self.sticker.id]),
            {"label": "x"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_regular_user_forbidden(self):
        client = self._auth(self.regular)
        resp = client.post(
            reverse("sticker-references", args=[self.sticker.id]),
            {"photos": self._fake_image()},
            format="multipart",
        )
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class MatchAlbumPhotoTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker

        cache.clear()
        self.user = User.objects.create_user(
            username="matchu", email="matchu@a.com", password="S3curePass!2026"
        )
        self.album = Album.objects.create(title="Carros", theme="vehiculos", description="d")
        self.sticker = Sticker.objects.create(album=self.album, name="ferrari")

    def _auth(self):
        client = APIClient()
        client.force_authenticate(self.user)
        return client

    def _photo(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io

        img = Image.new("RGB", (50, 50), color=(100, 100, 100))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return SimpleUploadedFile("car.jpg", buf.getvalue(), content_type="image/jpeg")

    def test_disabled_returns_message(self):
        from django.test import override_settings

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=False):
            resp = client.post(
                reverse("album-match-photo", args=[self.album.id]),
                {"photo": self._photo()},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["unlocked"])
        self.assertIn("deshabilitada", resp.data["message"].lower())

    def test_missing_photo_returns_400(self):
        from django.test import override_settings

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="fake"):
            resp = client.post(
                reverse("album-match-photo", args=[self.album.id]),
                {},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_album_not_found(self):
        from django.test import override_settings

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="fake"):
            resp = client.post(
                reverse("album-match-photo", args=[99999]),
                {"photo": self._photo()},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_analyzer_returns_none(self):
        from django.test import override_settings
        from unittest.mock import patch

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="fake"), \
             patch("albums.views.analyze_car_photo", return_value=None):
            resp = client.post(
                reverse("album-match-photo", args=[self.album.id]),
                {"photo": self._photo()},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["unlocked"])

    def test_analyzer_unrecognized(self):
        from django.test import override_settings
        from unittest.mock import patch

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="fake"), \
             patch("albums.views.analyze_car_photo", return_value={"recognized": False, "fun_fact": "no car"}):
            resp = client.post(
                reverse("album-match-photo", args=[self.album.id]),
                {"photo": self._photo()},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["unlocked"])
        self.assertEqual(resp.data["fun_fact"], "no car")

    def test_analyzer_recognized_no_sticker_id(self):
        from django.test import override_settings
        from unittest.mock import patch

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="fake"), \
             patch(
                 "albums.views.analyze_car_photo",
                 return_value={
                     "recognized": True,
                     "confidence": 0.9,
                     "sticker_id": None,
                     "make": "Tesla",
                     "model": "Model 3",
                 },
             ):
            resp = client.post(
                reverse("album-match-photo", args=[self.album.id]),
                {"photo": self._photo()},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["unlocked"])
        self.assertIn("Tesla", resp.data["message"])

    def test_analyzer_sticker_not_in_album(self):
        from django.test import override_settings
        from unittest.mock import patch

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="fake"), \
             patch(
                 "albums.views.analyze_car_photo",
                 return_value={
                     "recognized": True,
                     "confidence": 0.95,
                     "sticker_id": 99999,
                     "make": "Audi",
                 },
             ):
            resp = client.post(
                reverse("album-match-photo", args=[self.album.id]),
                {"photo": self._photo()},
                format="multipart",
            )
        self.assertFalse(resp.data["unlocked"])
        self.assertIn("no pertenece", resp.data["message"].lower())

    def test_analyzer_low_confidence(self):
        from django.test import override_settings
        from unittest.mock import patch

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="fake"), \
             patch(
                 "albums.views.analyze_car_photo",
                 return_value={
                     "recognized": True,
                     "confidence": 0.3,
                     "sticker_id": self.sticker.id,
                     "make": "Ferrari",
                 },
             ):
            resp = client.post(
                reverse("album-match-photo", args=[self.album.id]),
                {"photo": self._photo()},
                format="multipart",
            )
        self.assertFalse(resp.data["unlocked"])
        self.assertIn("segura", resp.data["message"].lower())

    def test_full_unlock_success(self):
        from django.test import override_settings
        from unittest.mock import patch
        from achievements.models import UserSticker

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="fake"), \
             patch(
                 "albums.views.analyze_car_photo",
                 return_value={
                     "recognized": True,
                     "confidence": 0.95,
                     "sticker_id": self.sticker.id,
                     "make": "Ferrari",
                     "model": "F40",
                     "fun_fact": "icon",
                     "reason": "ok",
                 },
             ), patch("albums.views.send_notification"):
            resp = client.post(
                reverse("album-match-photo", args=[self.album.id]),
                {"photo": self._photo(), "lat": "20.5", "lng": "-103.5"},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["unlocked"])
        us = UserSticker.objects.get(user=self.user, sticker=self.sticker)
        self.assertTrue(us.validated)
        self.assertEqual(us.location_lat, 20.5)
        self.assertEqual(us.location_lng, -103.5)

    def test_already_unlocked_adds_photo(self):
        from django.test import override_settings
        from unittest.mock import patch
        from achievements.models import UserSticker, CapturePhoto

        UserSticker.objects.create(
            user=self.user, sticker=self.sticker, validated=True,
            status=UserSticker.STATUS_APPROVED,
        )

        client = self._auth()
        before = CapturePhoto.objects.filter(user_sticker__user=self.user).count()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="fake"), \
             patch(
                 "albums.views.analyze_car_photo",
                 return_value={
                     "recognized": True,
                     "confidence": 0.95,
                     "sticker_id": self.sticker.id,
                     "make": "Ferrari",
                 },
             ):
            resp = client.post(
                reverse("album-match-photo", args=[self.album.id]),
                {"photo": self._photo()},
                format="multipart",
            )
        self.assertTrue(resp.data["unlocked"])
        self.assertTrue(resp.data["already_unlocked"])
        after = CapturePhoto.objects.filter(user_sticker__user=self.user).count()
        self.assertEqual(after, before + 1)

    def test_invalid_lat_lng_swallowed(self):
        from django.test import override_settings
        from unittest.mock import patch

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="fake"), \
             patch(
                 "albums.views.analyze_car_photo",
                 return_value={
                     "recognized": True,
                     "confidence": 0.95,
                     "sticker_id": self.sticker.id,
                     "make": "Ferrari",
                 },
             ), patch("albums.views.send_notification"):
            resp = client.post(
                reverse("album-match-photo", args=[self.album.id]),
                {"photo": self._photo(), "lat": "not-a-float", "lng": "also-bad"},
                format="multipart",
            )
        self.assertTrue(resp.data["unlocked"])


class GlobalScanTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker

        cache.clear()
        self.user = User.objects.create_user(
            username="gscan", email="gs@a.com", password="S3curePass!2026"
        )
        self.album = Album.objects.create(title="GS-Album", theme="t", description="d")
        self.s1 = Sticker.objects.create(album=self.album, name="ferrari-rojo")
        self.s2 = Sticker.objects.create(album=self.album, name="lambo")

    def _auth(self):
        client = APIClient()
        client.force_authenticate(self.user)
        return client

    def _photo(self, color=(0, 0, 0)):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io

        img = Image.new("RGB", (40, 40), color=color)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return SimpleUploadedFile(
            "scan.jpg", buf.getvalue(), content_type="image/jpeg"
        )

    def test_disabled_returns_message(self):
        from django.test import override_settings

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=False, OPENAI_API_KEY=""):
            resp = client.post(
                reverse("global-scan"), {"photo": self._photo()}, format="multipart"
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["unlocked"])

    def test_missing_photo_returns_400(self):
        from django.test import override_settings

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"):
            resp = client.post(reverse("global-scan"), {}, format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_quota_exceeded_returns_429(self):
        from django.test import override_settings
        from albums.models import ScanQuotaUsage
        from django.utils import timezone

        ScanQuotaUsage.objects.create(
            user=self.user, date=timezone.localdate(), count=5
        )
        client = self._auth()
        with override_settings(
            USE_OPENAI_STICKER_VALIDATION=True,
            OPENAI_API_KEY="x",
            MAX_SCANS_PER_DAY_FREE=5,
        ):
            resp = client.post(
                reverse("global-scan"), {"photo": self._photo()}, format="multipart"
            )
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertTrue(resp.data["quota_exceeded"])

    def test_analyzer_returns_none(self):
        from django.test import override_settings
        from unittest.mock import patch

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch("albums.views.analyze_photo_global", return_value=None):
            resp = client.post(
                reverse("global-scan"), {"photo": self._photo()}, format="multipart"
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["unlocked"])

    def test_unrecognized_creates_scan_log(self):
        from django.test import override_settings
        from unittest.mock import patch
        from albums.models import ScanLog

        client = self._auth()
        before = ScanLog.objects.count()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch(
                 "albums.views.analyze_photo_global",
                 return_value={
                     "recognized": False,
                     "matches": [],
                     "fun_fact": "nada reconocible",
                     "item_count": 0,
                 },
             ):
            resp = client.post(
                reverse("global-scan"),
                {"photo": self._photo(color=(50, 50, 50))},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["unlocked"])
        self.assertEqual(ScanLog.objects.count(), before + 1)

    def test_match_with_sticker_unlocks(self):
        from django.test import override_settings
        from unittest.mock import patch
        from achievements.models import UserSticker

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch(
                 "albums.views.analyze_photo_global",
                 return_value={
                     "recognized": True,
                     "matches": [
                         {
                             "detected_item": "ferrari rojo",
                             "detected_category": "auto",
                             "confidence": 0.92,
                             "sticker_id": self.s1.id,
                             "album_id": self.album.id,
                             "reason": "match",
                         }
                     ],
                     "fun_fact": "rojo italiano",
                     "item_count": 1,
                 },
             ):
            resp = client.post(
                reverse("global-scan"),
                {"photo": self._photo(color=(200, 0, 0)), "lat": "20.5", "lng": "-103.3"},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["unlocked"])
        us = UserSticker.objects.get(user=self.user, sticker=self.s1)
        self.assertTrue(us.validated)
        self.assertEqual(us.location_lat, 20.5)

    def test_multi_match_returns_multiple_unlocks(self):
        from django.test import override_settings
        from unittest.mock import patch

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch(
                 "albums.views.analyze_photo_global",
                 return_value={
                     "recognized": True,
                     "matches": [
                         {
                             "detected_item": "ferrari",
                             "confidence": 0.92,
                             "sticker_id": self.s1.id,
                             "album_id": self.album.id,
                         },
                         {
                             "detected_item": "lambo",
                             "confidence": 0.91,
                             "sticker_id": self.s2.id,
                             "album_id": self.album.id,
                         },
                     ],
                     "fun_fact": "dos autos",
                 },
             ):
            resp = client.post(
                reverse("global-scan"),
                {"photo": self._photo(color=(100, 100, 0))},
                format="multipart",
            )
        self.assertTrue(resp.data["unlocked"])
        self.assertGreaterEqual(resp.data["unlock_count"], 2)

    def test_low_confidence_match_is_rejected(self):
        from django.test import override_settings
        from unittest.mock import patch

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch(
                 "albums.views.analyze_photo_global",
                 return_value={
                     "recognized": True,
                     "matches": [
                         {
                             "detected_item": "borroso",
                             "confidence": 0.3,
                             "sticker_id": self.s1.id,
                             "album_id": self.album.id,
                         }
                     ],
                     "fun_fact": "duda",
                 },
             ):
            resp = client.post(
                reverse("global-scan"),
                {"photo": self._photo(color=(120, 120, 120))},
                format="multipart",
            )
        self.assertFalse(resp.data["unlocked"])

    def test_unknown_sticker_id_skipped(self):
        from django.test import override_settings
        from unittest.mock import patch

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch(
                 "albums.views.analyze_photo_global",
                 return_value={
                     "recognized": True,
                     "matches": [
                         {
                             "detected_item": "fantasma",
                             "confidence": 0.95,
                             "sticker_id": 99999,
                             "album_id": self.album.id,
                         }
                     ],
                     "fun_fact": "???",
                 },
             ):
            resp = client.post(
                reverse("global-scan"),
                {"photo": self._photo(color=(80, 80, 80))},
                format="multipart",
            )
        self.assertFalse(resp.data["unlocked"])

    def test_match_without_sticker_id_returns_rejected(self):
        from django.test import override_settings
        from unittest.mock import patch

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch(
                 "albums.views.analyze_photo_global",
                 return_value={
                     "recognized": True,
                     "matches": [
                         {
                             "detected_item": "algo",
                             "confidence": 0.95,
                             "sticker_id": None,
                             "album_id": self.album.id,
                         }
                     ],
                     "fun_fact": "no hay sticker",
                 },
             ):
            resp = client.post(
                reverse("global-scan"),
                {"photo": self._photo(color=(160, 160, 160))},
                format="multipart",
            )
        self.assertFalse(resp.data["unlocked"])

    def test_already_unlocked_adds_capture_photo(self):
        from django.test import override_settings
        from unittest.mock import patch
        from achievements.models import UserSticker, CapturePhoto

        UserSticker.objects.create(
            user=self.user,
            sticker=self.s1,
            validated=True,
            status=UserSticker.STATUS_APPROVED,
        )
        before = CapturePhoto.objects.filter(
            user_sticker__user=self.user, user_sticker__sticker=self.s1
        ).count()

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch(
                 "albums.views.analyze_photo_global",
                 return_value={
                     "recognized": True,
                     "matches": [
                         {
                             "detected_item": "ferrari",
                             "confidence": 0.95,
                             "sticker_id": self.s1.id,
                             "album_id": self.album.id,
                         }
                     ],
                 },
             ):
            resp = client.post(
                reverse("global-scan"),
                {"photo": self._photo(color=(200, 50, 50))},
                format="multipart",
            )
        self.assertTrue(resp.data["unlocked"])
        after = CapturePhoto.objects.filter(
            user_sticker__user=self.user, user_sticker__sticker=self.s1
        ).count()
        self.assertEqual(after, before + 1)

    def test_premium_user_no_quota_block(self):
        from django.test import override_settings
        from unittest.mock import patch
        from albums.models import ScanQuotaUsage
        from django.utils import timezone

        self.user.is_premium = True
        self.user.save(update_fields=["is_premium"])
        ScanQuotaUsage.objects.create(
            user=self.user, date=timezone.localdate(), count=999
        )

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch(
                 "albums.views.analyze_photo_global",
                 return_value={
                     "recognized": True,
                     "matches": [
                         {
                             "detected_item": "ferrari",
                             "confidence": 0.95,
                             "sticker_id": self.s1.id,
                             "album_id": self.album.id,
                         }
                     ],
                 },
             ):
            resp = client.post(
                reverse("global-scan"),
                {"photo": self._photo(color=(50, 200, 50))},
                format="multipart",
            )
        self.assertNotEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_response_includes_quota_info(self):
        from django.test import override_settings
        from unittest.mock import patch

        client = self._auth()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch(
                 "albums.views.analyze_photo_global",
                 return_value={"recognized": False, "matches": [], "fun_fact": "x"},
             ):
            resp = client.post(
                reverse("global-scan"),
                {"photo": self._photo(color=(10, 10, 10))},
                format="multipart",
            )
        self.assertIn("quota", resp.data)
        self.assertIn("limit", resp.data["quota"])

    def test_requires_auth(self):
        from django.test import override_settings

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"):
            resp = self.client.post(
                reverse("global-scan"),
                {"photo": self._photo()},
                format="multipart",
            )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class AlbumsChatRoomTests(APITestCase):
    def test_chat_room_name_order_independent(self):
        from albums.consumers import chat_room_name

        self.assertEqual(chat_room_name(1, 2), chat_room_name(2, 1))
        self.assertEqual(chat_room_name(3, 3), "chat_3_3")

    def test_chat_room_name_format(self):
        from albums.consumers import chat_room_name

        self.assertEqual(chat_room_name(7, 4), "chat_4_7")


class AlbumsAuthenticateJWTTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="jw", email="jw@a.com", password="S3curePass!2026"
        )

    def _token(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        return str(RefreshToken.for_user(self.user).access_token)

    def test_authenticate_jwt_valid_returns_user(self):
        import asyncio
        from unittest.mock import patch
        from albums.consumers import authenticate_jwt

        token = self._token()

        def fake_wrap(sync_callable):
            async def call(*args, **kwargs):
                return self.user

            return call

        with patch("albums.consumers.sync_to_async", side_effect=fake_wrap):
            result = asyncio.run(authenticate_jwt(token))
        self.assertEqual(result.id, self.user.id)

    def test_authenticate_jwt_invalid_returns_none(self):
        import asyncio
        from albums.consumers import authenticate_jwt

        result = asyncio.run(authenticate_jwt("garbage"))
        self.assertIsNone(result)


class AlbumsChatConsumerTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username="acca", email="acca@a.com", password="S3curePass!2026"
        )
        self.bob = User.objects.create_user(
            username="accb", email="accb@a.com", password="S3curePass!2026"
        )

    def test_connect_without_token_closes(self):
        import asyncio
        from unittest.mock import AsyncMock
        from albums.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.scope = {"query_string": b"", "url_route": {"kwargs": {"room_id": "1"}}}
            c.channel_name = "x"
            c.channel_layer = AsyncMock()
            c.accept = AsyncMock()
            c.close = AsyncMock()
            await c.connect()
            c.close.assert_called_once()
            c.accept.assert_not_called()

        asyncio.run(runner())

    def test_connect_with_invalid_token_closes(self):
        import asyncio
        from unittest.mock import AsyncMock
        from albums.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.scope = {
                "query_string": b"token=badtoken",
                "url_route": {"kwargs": {"room_id": "1"}},
            }
            c.channel_name = "x"
            c.channel_layer = AsyncMock()
            c.accept = AsyncMock()
            c.close = AsyncMock()
            await c.connect()
            c.close.assert_called_once()
            c.accept.assert_not_called()

        asyncio.run(runner())

    def test_connect_without_room_id_closes(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        from albums.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.scope = {
                "query_string": b"token=x",
                "url_route": {"kwargs": {}},
            }
            c.channel_name = "x"
            c.channel_layer = AsyncMock()
            c.accept = AsyncMock()
            c.close = AsyncMock()

            async def fake_authenticate(_t):
                return self.alice

            with patch("albums.consumers.authenticate_jwt", fake_authenticate):
                await c.connect()
            c.close.assert_called_once()
            c.accept.assert_not_called()

        asyncio.run(runner())

    def test_connect_authorized_friend_accepts(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        from albums.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.scope = {
                "query_string": b"token=x",
                "url_route": {"kwargs": {"room_id": str(self.bob.id)}},
            }
            c.channel_name = "x"
            c.channel_layer = AsyncMock()
            c.accept = AsyncMock()
            c.close = AsyncMock()

            async def fake_authenticate(_t):
                return self.alice

            async def fake_is_friend(*args, **kwargs):
                return True

            c._is_friend = fake_is_friend
            with patch("albums.consumers.authenticate_jwt", fake_authenticate):
                await c.connect()
            c.accept.assert_called_once()
            c.close.assert_not_called()

        asyncio.run(runner())

    def test_disconnect_discards(self):
        import asyncio
        from unittest.mock import AsyncMock
        from albums.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.channel_name = "x"
            c.room_group_name = "chat_1_2"
            c.channel_layer = AsyncMock()
            await c.disconnect(1000)
            c.channel_layer.group_discard.assert_called_once()

        asyncio.run(runner())

    def test_receive_empty_text_skipped(self):
        import asyncio
        from unittest.mock import AsyncMock
        from albums.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.scope = {
                "user": self.alice,
                "url_route": {"kwargs": {"room_id": str(self.bob.id)}},
            }
            c.channel_name = "x"
            c.channel_layer = AsyncMock()
            await c.receive_json({"text": "   "})
            c.channel_layer.group_send.assert_not_called()

        asyncio.run(runner())

    def test_receive_broadcasts_message(self):
        import asyncio
        from unittest.mock import AsyncMock
        from albums.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.scope = {
                "user": self.alice,
                "url_route": {"kwargs": {"room_id": str(self.bob.id)}},
            }
            c.channel_name = "x"
            c.room_group_name = "chat_a_b"
            c.channel_layer = AsyncMock()

            async def fake_create(sender_id, recipient_id, text):
                return {"id": 1, "text": text}

            c._create_message = fake_create
            await c.receive_json({"text": "hola"})
            self.assertEqual(c.channel_layer.group_send.call_count, 2)

        asyncio.run(runner())

    def test_chat_message_handler(self):
        import asyncio
        from unittest.mock import AsyncMock
        from albums.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.send_json = AsyncMock()
            await c.chat_message({"message": {"x": 1}})
            c.send_json.assert_called_once_with(
                {"type": "chat_message", "message": {"x": 1}}
            )

        asyncio.run(runner())


class AlbumsNotificationConsumerTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="nuc", email="nuc@a.com", password="S3curePass!2026"
        )

    def test_connect_without_token_closes(self):
        import asyncio
        from unittest.mock import AsyncMock
        from albums.consumers import NotificationConsumer

        async def runner():
            c = NotificationConsumer()
            c.scope = {"query_string": b""}
            c.channel_name = "x"
            c.channel_layer = AsyncMock()
            c.accept = AsyncMock()
            c.close = AsyncMock()
            await c.connect()
            c.close.assert_called_once()

        asyncio.run(runner())

    def test_connect_invalid_token_closes(self):
        import asyncio
        from unittest.mock import AsyncMock
        from albums.consumers import NotificationConsumer

        async def runner():
            c = NotificationConsumer()
            c.scope = {"query_string": b"token=bad"}
            c.channel_name = "x"
            c.channel_layer = AsyncMock()
            c.accept = AsyncMock()
            c.close = AsyncMock()
            await c.connect()
            c.close.assert_called_once()

        asyncio.run(runner())

    def test_connect_valid_token_accepts(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        from albums.consumers import NotificationConsumer

        async def runner():
            c = NotificationConsumer()
            c.scope = {"query_string": b"token=x"}
            c.channel_name = "x"
            c.channel_layer = AsyncMock()
            c.accept = AsyncMock()
            c.close = AsyncMock()

            async def fake_authenticate(_t):
                return self.user

            with patch("albums.consumers.authenticate_jwt", fake_authenticate):
                await c.connect()
            c.accept.assert_called_once()
            c.close.assert_not_called()

        asyncio.run(runner())

    def test_disconnect_discards_groups(self):
        import asyncio
        from unittest.mock import AsyncMock
        from albums.consumers import NotificationConsumer

        async def runner():
            c = NotificationConsumer()
            c.channel_name = "x"
            c.group_name = "user_42"
            c.channel_layer = AsyncMock()
            await c.disconnect(1000)
            self.assertEqual(c.channel_layer.group_discard.call_count, 2)

        asyncio.run(runner())

    def test_notification_handler(self):
        import asyncio
        from unittest.mock import AsyncMock
        from albums.consumers import NotificationConsumer

        async def runner():
            c = NotificationConsumer()
            c.send_json = AsyncMock()
            await c.notification({"payload": {"a": "b"}})
            c.send_json.assert_called_once_with({"type": "notification", "a": "b"})

        asyncio.run(runner())


class VisionPrefilterTests(APITestCase):
    def test_disabled_returns_none(self):
        from django.test import override_settings
        from albums.vision_prefilter import is_collectible

        with override_settings(VISION_PREFILTER_ENABLED=False):
            self.assertIsNone(is_collectible(b"some bytes"))

    def test_empty_bytes_returns_none(self):
        from albums.vision_prefilter import is_collectible

        self.assertIsNone(is_collectible(b""))
        self.assertIsNone(is_collectible(None))

    def test_collectible_true_response(self):
        from unittest.mock import patch, MagicMock
        from albums.vision_prefilter import is_collectible

        fake_msg = MagicMock()
        fake_msg.message.content = '{"collectible": true}'
        fake_completion = MagicMock(choices=[fake_msg])
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_completion

        with patch("albums.vision_prefilter.get_openai_client", return_value=fake_client):
            result = is_collectible(b"image bytes")
            self.assertEqual(result, {"collectible": True})

    def test_collectible_false_response(self):
        from unittest.mock import patch, MagicMock
        from albums.vision_prefilter import is_collectible

        fake_msg = MagicMock()
        fake_msg.message.content = '{"collectible": false, "reason": "borrosa"}'
        fake_completion = MagicMock(choices=[fake_msg])
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_completion

        with patch("albums.vision_prefilter.get_openai_client", return_value=fake_client):
            result = is_collectible(b"image bytes")
            self.assertFalse(result["collectible"])
            self.assertEqual(result["reason"], "borrosa")

    def test_client_init_failure_returns_none(self):
        from unittest.mock import patch
        from albums.vision_prefilter import is_collectible

        with patch(
            "albums.vision_prefilter.get_openai_client",
            side_effect=RuntimeError("no key"),
        ):
            self.assertIsNone(is_collectible(b"bytes"))

    def test_completion_exception_returns_none(self):
        from unittest.mock import patch, MagicMock
        from albums.vision_prefilter import is_collectible

        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = RuntimeError("openai down")

        with patch("albums.vision_prefilter.get_openai_client", return_value=fake_client):
            self.assertIsNone(is_collectible(b"bytes"))

    def test_malformed_json_returns_none(self):
        from unittest.mock import patch, MagicMock
        from albums.vision_prefilter import is_collectible

        fake_msg = MagicMock()
        fake_msg.message.content = "not valid json {"
        fake_completion = MagicMock(choices=[fake_msg])
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_completion

        with patch("albums.vision_prefilter.get_openai_client", return_value=fake_client):
            self.assertIsNone(is_collectible(b"bytes"))

    def test_empty_content_handled(self):
        from unittest.mock import patch, MagicMock
        from albums.vision_prefilter import is_collectible

        fake_msg = MagicMock()
        fake_msg.message.content = None
        fake_completion = MagicMock(choices=[fake_msg])
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = fake_completion

        with patch("albums.vision_prefilter.get_openai_client", return_value=fake_client):
            result = is_collectible(b"bytes")
            self.assertEqual(result, {})


class SeedCarrosDeFerCommandTests(APITestCase):
    def test_creates_album_and_stickers(self):
        from io import StringIO
        from django.core.management import call_command
        from albums.models import Album, Sticker

        out = StringIO()
        call_command("seed_carros_de_fer", stdout=out)
        album = Album.objects.get(title="Carros de Fer")
        self.assertGreater(Sticker.objects.filter(album=album).count(), 0)

    def test_idempotent_second_run_skips(self):
        from io import StringIO
        from django.core.management import call_command
        from albums.models import Album, Sticker

        call_command("seed_carros_de_fer", stdout=StringIO())
        album = Album.objects.get(title="Carros de Fer")
        count_after_first = Sticker.objects.filter(album=album).count()
        call_command("seed_carros_de_fer", stdout=StringIO())
        self.assertEqual(Sticker.objects.filter(album=album).count(), count_after_first)
        self.assertEqual(Album.objects.filter(title="Carros de Fer").count(), 1)

    def test_reset_recreates_album(self):
        from io import StringIO
        from django.core.management import call_command
        from albums.models import Album

        call_command("seed_carros_de_fer", stdout=StringIO())
        first_id = Album.objects.get(title="Carros de Fer").id
        call_command("seed_carros_de_fer", "--reset", stdout=StringIO())
        new_id = Album.objects.get(title="Carros de Fer").id
        self.assertNotEqual(first_id, new_id)
