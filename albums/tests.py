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
