from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ChatMessage, FriendRequest

User = get_user_model()


def _make_user(**overrides):
    defaults = {
        "username": "u",
        "email": "u@test.com",
        "password": "S3curePass!2026",
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def _be_friends(a, b):
    return FriendRequest.objects.create(
        from_user=a, to_user=b, status=FriendRequest.STATUS_ACCEPTED
    )


class ChatMessageTests(APITestCase):
    def setUp(self):
        self.alice = _make_user(username="alice", email="alice@test.com")
        self.bob = _make_user(username="bob", email="bob@test.com")
        self.eve = _make_user(username="eve", email="eve@test.com")
        _be_friends(self.alice, self.bob)

    def test_send_message_to_friend(self):
        self.client.force_authenticate(self.alice)
        url = reverse("chat-messages", args=[self.bob.id])
        resp = self.client.post(url, {"text": "hola bob"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["text"], "hola bob")
        self.assertEqual(resp.data["sender_id"], self.alice.id)
        self.assertEqual(resp.data["sender_username"], "alice")

    def test_send_message_to_non_friend_forbidden(self):
        self.client.force_authenticate(self.alice)
        url = reverse("chat-messages", args=[self.eve.id])
        resp = self.client.post(url, {"text": "hi"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_send_empty_message_rejected(self):
        self.client.force_authenticate(self.alice)
        url = reverse("chat-messages", args=[self.bob.id])
        resp = self.client.post(url, {"text": ""}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_messages_between_friends(self):
        ChatMessage.objects.create(sender=self.alice, recipient=self.bob, text="m1")
        ChatMessage.objects.create(sender=self.bob, recipient=self.alice, text="m2")
        ChatMessage.objects.create(sender=self.eve, recipient=self.alice, text="other")
        self.client.force_authenticate(self.alice)
        url = reverse("chat-messages", args=[self.bob.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get("results", resp.data)
        texts = sorted(m["text"] for m in results)
        self.assertEqual(texts, ["m1", "m2"])

    def test_unauthenticated_rejected(self):
        url = reverse("chat-messages", args=[self.bob.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class ChatInboxTests(APITestCase):
    def setUp(self):
        self.alice = _make_user(username="alice", email="alice@test.com")
        self.bob = _make_user(username="bob", email="bob@test.com")
        self.url = reverse("chat-inbox")

    def test_inbox_returns_only_received(self):
        ChatMessage.objects.create(sender=self.bob, recipient=self.alice, text="for alice")
        ChatMessage.objects.create(sender=self.alice, recipient=self.bob, text="from alice")
        self.client.force_authenticate(self.alice)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get("results", resp.data)
        texts = [m["text"] for m in results]
        self.assertIn("for alice", texts)
        self.assertNotIn("from alice", texts)

    def test_inbox_since_id_filter(self):
        m1 = ChatMessage.objects.create(sender=self.bob, recipient=self.alice, text="m1")
        ChatMessage.objects.create(sender=self.bob, recipient=self.alice, text="m2")
        self.client.force_authenticate(self.alice)
        resp = self.client.get(self.url, {"since_id": m1.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get("results", resp.data)
        texts = [m["text"] for m in results]
        self.assertIn("m2", texts)
        self.assertNotIn("m1", texts)

    def test_inbox_serializer_fields(self):
        ChatMessage.objects.create(sender=self.bob, recipient=self.alice, text="hola")
        self.client.force_authenticate(self.alice)
        resp = self.client.get(self.url)
        results = resp.data.get("results", resp.data)
        self.assertEqual(len(results), 1)
        msg = results[0]
        self.assertEqual(msg["sender_id"], self.bob.id)
        self.assertEqual(msg["sender_username"], "bob")
        self.assertEqual(msg["text"], "hola")
        self.assertIn("id", msg)
        self.assertIn("created_at", msg)

    def test_inbox_empty_for_no_messages(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get("results", resp.data)
        self.assertEqual(len(results), 0)


class ProfileDeleteTests(APITestCase):
    def setUp(self):
        self.user = _make_user(username="todelete", email="del@test.com")

    def test_delete_own_account(self):
        self.client.force_authenticate(self.user)
        url = reverse("profile")
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(id=self.user.id).exists())

    def test_delete_unauthenticated_rejected(self):
        url = reverse("profile")
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class AnalyzePhotoGlobalTests(APITestCase):
    def _fake_main_response(self, recognized=True, matches=None):
        import json
        from unittest.mock import MagicMock

        payload = {
            "recognized": recognized,
            "item_count": len(matches or []),
            "photo_category": "test",
            "matches": matches or [],
            "fun_fact": "ok",
        }
        msg = MagicMock()
        msg.message.content = json.dumps(payload)
        return MagicMock(choices=[msg])

    def _fake_image_bytes(self):
        from PIL import Image
        import io

        img = Image.new("RGB", (200, 200), color=(120, 80, 40))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return buf

    def test_disabled_returns_error(self):
        from django.test import override_settings
        from achievements.services import analyze_photo_global

        with override_settings(USE_OPENAI_STICKER_VALIDATION=False):
            result = analyze_photo_global(self._fake_image_bytes(), [])
            self.assertIn("error", result)

    def test_cache_hit_short_circuits_openai(self):
        from unittest.mock import patch
        from achievements.services import analyze_photo_global
        from albums import vision_cache

        buf = self._fake_image_bytes()
        raw = buf.getvalue()
        phash = vision_cache.compute_dhash(raw)
        cached = {"recognized": True, "matches": [{"sticker_id": 999}], "fun_fact": "cached"}
        vision_cache.store(phash, cached)
        buf.seek(0)

        with patch("achievements.services.get_openai_client") as mocked:
            result = analyze_photo_global(buf, [])
            self.assertEqual(result, cached)
            mocked.assert_not_called()

    def test_circuit_tripped_returns_error_response(self):
        from decimal import Decimal
        from django.utils import timezone
        from unittest.mock import patch
        from achievements.services import analyze_photo_global
        from albums.models import DailyAICost

        DailyAICost.objects.create(
            date=timezone.localdate(), total_usd=Decimal("100.0"), call_count=10
        )
        with patch("achievements.services.get_openai_client"):
            result = analyze_photo_global(self._fake_image_bytes(), [])
        self.assertFalse(result["recognized"])
        self.assertTrue(result.get("circuit_tripped"))

    def test_prefilter_rejects_skips_main_call(self):
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_photo_global

        prefilter_msg = MagicMock()
        prefilter_msg.message.content = '{"collectible": false, "reason": "foto borrosa"}'
        prefilter_completion = MagicMock(choices=[prefilter_msg])
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = prefilter_completion

        with patch("achievements.services.get_openai_client", return_value=fake_client), \
             patch("albums.vision_prefilter.get_openai_client", return_value=fake_client):
            result = analyze_photo_global(self._fake_image_bytes(), [])

        self.assertFalse(result["recognized"])
        self.assertTrue(result.get("prefiltered"))
        self.assertEqual(result["fun_fact"], "foto borrosa")

    def test_normal_flow_records_cost_and_stores_cache(self):
        from unittest.mock import patch, MagicMock
        from django.test import override_settings
        from achievements.services import analyze_photo_global
        from albums.models import DailyAICost, VisionResultCache
        from albums import vision_cache

        buf = self._fake_image_bytes()
        raw = buf.getvalue()
        phash = vision_cache.compute_dhash(raw)
        buf.seek(0)

        prefilter_msg = MagicMock()
        prefilter_msg.message.content = '{"collectible": true}'
        prefilter_completion = MagicMock(choices=[prefilter_msg])
        main_completion = self._fake_main_response(recognized=True, matches=[])

        fake_client_main = MagicMock()
        fake_client_main.chat.completions.create.return_value = main_completion
        fake_client_pref = MagicMock()
        fake_client_pref.chat.completions.create.return_value = prefilter_completion

        with override_settings(VISION_MAIN_COST_USD=0.001, VISION_PREFILTER_COST_USD=0.0001), \
             patch("achievements.services.get_openai_client", return_value=fake_client_main), \
             patch("albums.vision_prefilter.get_openai_client", return_value=fake_client_pref):
            result = analyze_photo_global(buf, [])

        self.assertTrue(result["recognized"])
        self.assertTrue(VisionResultCache.objects.filter(phash=phash).exists())
        cost_row = DailyAICost.objects.first()
        self.assertGreater(cost_row.total_usd, 0)
        self.assertGreaterEqual(cost_row.call_count, 1)

    def test_openai_main_exception_returns_none(self):
        from unittest.mock import patch, MagicMock
        from django.test import override_settings
        from achievements.services import analyze_photo_global

        fake_client_main = MagicMock()
        fake_client_main.chat.completions.create.side_effect = RuntimeError("boom")

        with override_settings(VISION_PREFILTER_ENABLED=False), \
             patch("achievements.services.get_openai_client", return_value=fake_client_main):
            result = analyze_photo_global(self._fake_image_bytes(), [])

        self.assertIsNone(result)

    def test_client_init_failure_returns_none(self):
        from django.test import override_settings
        from unittest.mock import patch
        from achievements.services import analyze_photo_global

        with override_settings(VISION_PREFILTER_ENABLED=False), patch(
            "achievements.services.get_openai_client",
            side_effect=RuntimeError("no openai"),
        ):
            self.assertIsNone(analyze_photo_global(self._fake_image_bytes(), []))
