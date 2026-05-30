from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ChatMessage, FriendRequest, UserSticker

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


class FriendRequestFlowTests(APITestCase):
    def setUp(self):
        self.alice = _make_user(username="al", email="al@test.com")
        self.bob = _make_user(username="bo", email="bo@test.com")
        self.eve = _make_user(username="ev", email="ev@test.com")

    def test_send_request_creates_pending(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.post(
            reverse("friend-requests"),
            {"to_user": self.bob.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], FriendRequest.STATUS_PENDING)

    def test_send_request_to_self_rejected(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.post(
            reverse("friend-requests"),
            {"to_user": self.alice.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_request_missing_to_user(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.post(reverse("friend-requests"), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reverse_pending_auto_accepts(self):
        FriendRequest.objects.create(from_user=self.bob, to_user=self.alice)
        self.client.force_authenticate(self.alice)
        resp = self.client.post(
            reverse("friend-requests"),
            {"to_user": self.bob.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], FriendRequest.STATUS_ACCEPTED)

    def test_resending_pending_returns_same(self):
        fr = FriendRequest.objects.create(from_user=self.alice, to_user=self.bob)
        self.client.force_authenticate(self.alice)
        resp = self.client.post(
            reverse("friend-requests"),
            {"to_user": self.bob.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["id"], fr.id)

    def test_send_after_rejected_reactivates(self):
        FriendRequest.objects.create(
            from_user=self.alice, to_user=self.bob, status=FriendRequest.STATUS_REJECTED
        )
        self.client.force_authenticate(self.alice)
        resp = self.client.post(
            reverse("friend-requests"),
            {"to_user": self.bob.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], FriendRequest.STATUS_PENDING)

    def test_already_friends_returns_existing(self):
        FriendRequest.objects.create(
            from_user=self.alice, to_user=self.bob, status=FriendRequest.STATUS_ACCEPTED
        )
        self.client.force_authenticate(self.alice)
        resp = self.client.post(
            reverse("friend-requests"),
            {"to_user": self.bob.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], FriendRequest.STATUS_ACCEPTED)

    def test_accept_request(self):
        fr = FriendRequest.objects.create(from_user=self.bob, to_user=self.alice)
        self.client.force_authenticate(self.alice)
        resp = self.client.post(reverse("friend-request-accept", args=[fr.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        fr.refresh_from_db()
        self.assertEqual(fr.status, FriendRequest.STATUS_ACCEPTED)

    def test_cannot_accept_others_request(self):
        fr = FriendRequest.objects.create(from_user=self.bob, to_user=self.alice)
        self.client.force_authenticate(self.eve)
        resp = self.client.post(reverse("friend-request-accept", args=[fr.id]))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_request(self):
        fr = FriendRequest.objects.create(from_user=self.bob, to_user=self.alice)
        self.client.force_authenticate(self.alice)
        resp = self.client.post(reverse("friend-request-reject", args=[fr.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        fr.refresh_from_db()
        self.assertEqual(fr.status, FriendRequest.STATUS_REJECTED)

    def test_cancel_own_pending(self):
        fr = FriendRequest.objects.create(from_user=self.alice, to_user=self.bob)
        self.client.force_authenticate(self.alice)
        resp = self.client.post(reverse("friend-request-cancel", args=[fr.id]))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(FriendRequest.objects.filter(id=fr.id).exists())

    def test_cannot_cancel_others_pending(self):
        fr = FriendRequest.objects.create(from_user=self.bob, to_user=self.alice)
        self.client.force_authenticate(self.alice)
        resp = self.client.post(reverse("friend-request-cancel", args=[fr.id]))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_friend(self):
        fr = FriendRequest.objects.create(
            from_user=self.alice, to_user=self.bob, status=FriendRequest.STATUS_ACCEPTED
        )
        self.client.force_authenticate(self.alice)
        resp = self.client.post(reverse("friend-remove", args=[fr.id]))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_remove_only_works_on_accepted(self):
        fr = FriendRequest.objects.create(
            from_user=self.alice, to_user=self.bob, status=FriendRequest.STATUS_PENDING
        )
        self.client.force_authenticate(self.alice)
        resp = self.client.post(reverse("friend-remove", args=[fr.id]))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_third_party_rejected(self):
        fr = FriendRequest.objects.create(
            from_user=self.alice, to_user=self.bob, status=FriendRequest.STATUS_ACCEPTED
        )
        self.client.force_authenticate(self.eve)
        resp = self.client.post(reverse("friend-remove", args=[fr.id]))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_friends_list_shows_accepted_only(self):
        FriendRequest.objects.create(
            from_user=self.alice, to_user=self.bob, status=FriendRequest.STATUS_ACCEPTED
        )
        FriendRequest.objects.create(
            from_user=self.alice, to_user=self.eve, status=FriendRequest.STATUS_PENDING
        )
        self.client.force_authenticate(self.alice)
        resp = self.client.get(reverse("friends-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        items = resp.data.get("results", resp.data)
        usernames = {u["username"] for u in items}
        self.assertIn(self.bob.username, usernames)
        self.assertNotIn(self.eve.username, usernames)

    def test_filter_received_scope(self):
        FriendRequest.objects.create(
            from_user=self.bob, to_user=self.alice
        )
        self.client.force_authenticate(self.alice)
        resp = self.client.get(reverse("friend-requests") + "?scope=received")
        items = resp.data.get("results", resp.data)
        self.assertEqual(len(items), 1)

    def test_filter_sent_scope(self):
        FriendRequest.objects.create(
            from_user=self.alice, to_user=self.bob
        )
        self.client.force_authenticate(self.alice)
        resp = self.client.get(reverse("friend-requests") + "?scope=sent")
        items = resp.data.get("results", resp.data)
        self.assertEqual(len(items), 1)


class ChatInboxFlowTests(APITestCase):
    def setUp(self):
        self.alice = _make_user(username="al2", email="al2@test.com")
        self.bob = _make_user(username="bo2", email="bo2@test.com")
        _be_friends(self.alice, self.bob)

    def test_inbox_empty_initial(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.get(reverse("chat-inbox"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_inbox_lists_messages_to_me(self):
        ChatMessage.objects.create(sender=self.bob, recipient=self.alice, text="hi")
        self.client.force_authenticate(self.alice)
        resp = self.client.get(reverse("chat-inbox"))
        items = resp.data.get("results", resp.data)
        self.assertEqual(len(items), 1)

    def test_inbox_filters_since_id(self):
        m1 = ChatMessage.objects.create(sender=self.bob, recipient=self.alice, text="m1")
        m2 = ChatMessage.objects.create(sender=self.bob, recipient=self.alice, text="m2")
        self.client.force_authenticate(self.alice)
        resp = self.client.get(reverse("chat-inbox") + f"?since_id={m1.id}")
        items = resp.data.get("results", resp.data)
        ids = [m["id"] for m in items]
        self.assertIn(m2.id, ids)
        self.assertNotIn(m1.id, ids)


class UserStickerHistoryTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker
        from achievements.models import UserSticker

        self.user_a = _make_user(username="histA", email="hA@test.com")
        self.user_b = _make_user(username="histB", email="hB@test.com")
        self.album = Album.objects.create(title="HistA", theme="t", description="d")
        self.s1 = Sticker.objects.create(album=self.album, name="s1")
        self.s2 = Sticker.objects.create(album=self.album, name="s2")
        UserSticker.objects.create(
            user=self.user_a, sticker=self.s1, validated=True,
            status=UserSticker.STATUS_APPROVED,
        )
        UserSticker.objects.create(
            user=self.user_b, sticker=self.s2, validated=True,
            status=UserSticker.STATUS_APPROVED,
        )

    def test_history_returns_only_own_captures(self):
        self.client.force_authenticate(self.user_a)
        resp = self.client.get(reverse("user-sticker-history"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        items = resp.data.get("results", resp.data)
        for entry in items:
            self.assertTrue(entry.get("sticker") or entry.get("id"))

    def test_history_requires_auth(self):
        resp = self.client.get(reverse("user-sticker-history"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class AnalyzeCarPhotoSimpleTests(APITestCase):
    def _fake_image_bytes(self):
        from PIL import Image
        import io

        img = Image.new("RGB", (100, 100), color=(100, 100, 100))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return buf

    def test_disabled_returns_error(self):
        from django.test import override_settings
        from achievements.services import analyze_car_photo

        with override_settings(USE_OPENAI_STICKER_VALIDATION=False):
            result = analyze_car_photo(self._fake_image_bytes(), [])
        self.assertIn("error", result)

    def test_successful_response_parsed(self):
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_car_photo
        from django.test import override_settings
        import json

        msg = MagicMock()
        msg.message.content = json.dumps({
            "recognized": True,
            "make": "Ferrari",
            "model": "F40",
            "confidence": 0.95,
            "sticker_id": 1,
            "reason": "obvious",
            "fun_fact": "italian",
        })
        completion = MagicMock(choices=[msg])
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = completion

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_car_photo(self._fake_image_bytes(), [])
        self.assertTrue(result["recognized"])
        self.assertEqual(result["make"], "Ferrari")
        self.assertEqual(result["sticker_id"], 1)

    def test_openai_exception_returns_none(self):
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_car_photo
        from django.test import override_settings

        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = RuntimeError("boom")
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_car_photo(self._fake_image_bytes(), [])
        self.assertIsNone(result)

    def test_response_fills_missing_keys(self):
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_car_photo
        from django.test import override_settings
        import json

        msg = MagicMock()
        msg.message.content = json.dumps({"recognized": True})
        completion = MagicMock(choices=[msg])
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = completion

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_car_photo(self._fake_image_bytes(), [])
        self.assertIn("make", result)
        self.assertIn("model", result)
        self.assertIn("confidence", result)
        self.assertIn("sticker_id", result)

    def test_photo_read_exception_returns_none(self):
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_car_photo
        from django.test import override_settings

        class BrokenStream:
            def read(self):
                raise IOError("cannot read photo")

            def seek(self, *a):
                pass

        fake_client = MagicMock()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_car_photo(BrokenStream(), [])
        self.assertIsNone(result)

    def test_client_init_failure_returns_none(self):
        from unittest.mock import patch
        from achievements.services import analyze_car_photo
        from django.test import override_settings

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", side_effect=RuntimeError("no key")):
            result = analyze_car_photo(self._fake_image_bytes(), [])
        self.assertIsNone(result)


class AnalyzeUserStickerSimpleTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker
        from achievements.models import UserSticker

        self.user = _make_user(username="auser", email="auser@test.com")
        self.album = Album.objects.create(title="A", theme="t", description="d")
        self.sticker = Sticker.objects.create(album=self.album, name="ferr")
        self.user_sticker = UserSticker.objects.create(
            user=self.user, sticker=self.sticker, photo_url="https://example.com/p.jpg"
        )

    def test_disabled_returns_auto_approve(self):
        from django.test import override_settings
        from achievements.services import analyze_user_sticker

        with override_settings(USE_OPENAI_STICKER_VALIDATION=False):
            result = analyze_user_sticker(self.user_sticker)
        self.assertTrue(result["approved"])
        self.assertIn("disabled", result["reason"].lower())

    def test_no_image_returns_rejected(self):
        from django.test import override_settings
        from albums.models import Sticker
        from achievements.models import UserSticker
        from achievements.services import analyze_user_sticker

        sticker2 = Sticker.objects.create(album=self.album, name="other-noimg")
        us = UserSticker.objects.create(
            user=self.user, sticker=sticker2, photo_url=""
        )
        with override_settings(USE_OPENAI_STICKER_VALIDATION=True):
            result = analyze_user_sticker(us)
        self.assertFalse(result["approved"])

    def test_with_description_and_reference_image_builds_full_prompt(self):
        from unittest.mock import patch, MagicMock
        from django.test import override_settings
        from django.core.files.uploadedfile import SimpleUploadedFile
        from achievements.services import analyze_user_sticker
        from PIL import Image
        import io, json

        img = Image.new("RGB", (10, 10), color=(7, 7, 7))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        self.sticker.description = "Ferrari rojo descapotable"
        self.sticker.image_reference = SimpleUploadedFile(
            "ref.jpg", buf.getvalue(), content_type="image/jpeg"
        )
        self.sticker.save(update_fields=["description", "image_reference"])

        captured = {}
        fake_response = MagicMock()
        fake_response.output_text = json.dumps(
            {"match_score": 0.9, "is_match": True, "reason": "ok"}
        )
        fake_response.id = "resp_xyz"
        fake_client = MagicMock()
        fake_client.responses.create.side_effect = lambda *a, **kw: (
            captured.update(kw) or fake_response
        )

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client), \
             patch.object(
                 type(self.sticker.image_reference), "open",
                 return_value=io.BytesIO(buf.getvalue()),
             ):
            result = analyze_user_sticker(self.user_sticker)

        self.assertTrue(result["approved"])
        content = captured["input"][0]["content"]
        prompt_text = content[0]["text"]
        self.assertIn("Ferrari rojo descapotable", prompt_text)
        self.assertIn("Álbum:", prompt_text)
        self.assertGreaterEqual(len(content), 3)

    def test_match_returns_approved(self):
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_user_sticker
        from django.test import override_settings
        import json

        fake_response = MagicMock()
        fake_response.output_text = json.dumps({
            "match_score": 0.9,
            "is_match": True,
            "reason": "matches well",
        })
        fake_response.id = "resp_abc123"
        fake_client = MagicMock()
        fake_client.responses.create.return_value = fake_response

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_user_sticker(self.user_sticker)
        self.assertTrue(result["approved"])
        self.assertTrue(result["is_match"])
        self.assertEqual(result["match_score"], 0.9)
        self.assertEqual(result["request_id"], "resp_abc123")

    def test_low_score_returns_not_approved(self):
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_user_sticker
        from django.test import override_settings
        import json

        fake_response = MagicMock()
        fake_response.output_text = json.dumps({
            "match_score": 0.3,
            "is_match": True,
            "reason": "weak match",
        })
        fake_client = MagicMock()
        fake_client.responses.create.return_value = fake_response

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_user_sticker(self.user_sticker)
        self.assertFalse(result["approved"])

    def test_no_match_returns_not_approved(self):
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_user_sticker
        from django.test import override_settings
        import json

        fake_response = MagicMock()
        fake_response.output_text = json.dumps({
            "match_score": 0.95,
            "is_match": False,
            "reason": "different car",
        })
        fake_client = MagicMock()
        fake_client.responses.create.return_value = fake_response

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_user_sticker(self.user_sticker)
        self.assertFalse(result["approved"])

    def test_malformed_json_returns_error(self):
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_user_sticker
        from django.test import override_settings

        fake_response = MagicMock()
        fake_response.output_text = "not valid json"
        fake_client = MagicMock()
        fake_client.responses.create.return_value = fake_response

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_user_sticker(self.user_sticker)
        self.assertFalse(result["approved"])
        self.assertIn("error", result)


class ValidateUserStickerTaskSimpleTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker
        from achievements.models import UserSticker

        self.user = _make_user(username="taskuser", email="taskuser@test.com")
        self.album = Album.objects.create(title="TA", theme="t", description="d")
        self.sticker = Sticker.objects.create(album=self.album, name="taskstick", reward_points=10)
        self.user_sticker = UserSticker.objects.create(
            user=self.user, sticker=self.sticker, photo_url="https://example.com/p.jpg"
        )

    def test_nonexistent_user_sticker_logs_and_returns(self):
        from achievements.tasks import validate_user_sticker

        validate_user_sticker(99999)

    def test_already_validated_skipped(self):
        from achievements.models import UserSticker
        from achievements.tasks import validate_user_sticker

        self.user_sticker.validated = True
        self.user_sticker.status = UserSticker.STATUS_APPROVED
        self.user_sticker.save()

        validate_user_sticker(self.user_sticker.id)
        self.user_sticker.refresh_from_db()
        self.assertEqual(self.user_sticker.status, UserSticker.STATUS_APPROVED)

    def test_approved_increments_points(self):
        from unittest.mock import patch
        from achievements.models import UserSticker
        from achievements.tasks import validate_user_sticker

        with patch(
            "achievements.tasks.analyze_user_sticker",
            return_value={"approved": True, "match_score": 0.95, "is_match": True},
        ):
            validate_user_sticker(self.user_sticker.id)
        self.user_sticker.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.user_sticker.status, UserSticker.STATUS_APPROVED)
        self.assertTrue(self.user_sticker.validated)
        self.assertIsNotNone(self.user_sticker.validated_at)
        self.assertEqual(self.user.points, 10)

    def test_rejected_keeps_zero_points(self):
        from unittest.mock import patch
        from achievements.models import UserSticker
        from achievements.tasks import validate_user_sticker

        with patch(
            "achievements.tasks.analyze_user_sticker",
            return_value={"approved": False, "match_score": 0.2, "is_match": False},
        ):
            validate_user_sticker(self.user_sticker.id)
        self.user_sticker.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.user_sticker.status, UserSticker.STATUS_REJECTED)
        self.assertFalse(self.user_sticker.validated)
        self.assertEqual(self.user.points, 0)

    def test_error_keeps_pending(self):
        from unittest.mock import patch
        from achievements.models import UserSticker
        from achievements.tasks import validate_user_sticker

        with patch(
            "achievements.tasks.analyze_user_sticker",
            return_value={"approved": False, "error": "OpenAI dead"},
        ):
            validate_user_sticker(self.user_sticker.id)
        self.user_sticker.refresh_from_db()
        self.assertEqual(self.user_sticker.status, UserSticker.STATUS_PENDING)
        self.assertFalse(self.user_sticker.validated)


class FirebaseBackendTests(APITestCase):
    def test_load_credentials_from_json_env(self):
        from unittest.mock import patch
        import json
        from users.firebase_backend import _load_credentials

        fake_cert = {
            "type": "service_account",
            "project_id": "test",
            "private_key_id": "abc",
            "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----",
            "client_email": "x@y.com",
            "client_id": "1",
        }
        env = {"FIREBASE_CREDENTIALS_JSON": json.dumps(fake_cert)}
        with patch.dict("os.environ", env, clear=False), \
             patch("users.firebase_backend.credentials.Certificate") as cert_class:
            cert_class.return_value = "fake-cert"
            result = _load_credentials()
            self.assertEqual(result, "fake-cert")

    def test_load_credentials_returns_none_when_empty(self):
        from unittest.mock import patch
        from users.firebase_backend import _load_credentials

        env = {}
        with patch.dict("os.environ", env, clear=True):
            result = _load_credentials()
            self.assertIsNone(result)

    def test_ensure_initialized_no_credentials_returns_false(self):
        from unittest.mock import patch
        import users.firebase_backend as fb

        with patch.object(fb, "_initialized", False), \
             patch.object(fb, "_init_error", None), \
             patch("users.firebase_backend._load_credentials", return_value=None):
            ok, err = fb.ensure_initialized()
            self.assertFalse(ok)
            self.assertIn("Firebase no configurado", err)

    def test_verify_id_token_propagates_init_failure(self):
        from unittest.mock import patch
        from users.firebase_backend import verify_id_token

        with patch(
            "users.firebase_backend.ensure_initialized",
            return_value=(False, "Firebase no configurado: test"),
        ):
            decoded, err = verify_id_token("anything")
            self.assertIsNone(decoded)
            self.assertIn("Firebase no configurado", err)

    def test_verify_id_token_catches_exception(self):
        from unittest.mock import patch
        from users.firebase_backend import verify_id_token

        with patch(
            "users.firebase_backend.ensure_initialized",
            return_value=(True, None),
        ), patch(
            "users.firebase_backend.firebase_auth.verify_id_token",
            side_effect=ValueError("token expired"),
        ):
            decoded, err = verify_id_token("bad-token")
            self.assertIsNone(decoded)
            self.assertIn("ValueError", err)

    def test_verify_id_token_success(self):
        from unittest.mock import patch
        from users.firebase_backend import verify_id_token

        with patch(
            "users.firebase_backend.ensure_initialized",
            return_value=(True, None),
        ), patch(
            "users.firebase_backend.firebase_auth.verify_id_token",
            return_value={"uid": "abc", "email": "test@firebase.com"},
        ):
            decoded, err = verify_id_token("valid")
            self.assertIsNone(err)
            self.assertEqual(decoded["uid"], "abc")


class AnalyzeCarPhotoTests(APITestCase):
    def _photo(self):
        from PIL import Image
        import io

        img = Image.new("RGB", (50, 50), color=(120, 80, 40))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return buf

    def test_disabled_returns_error(self):
        from django.test import override_settings
        from achievements.services import analyze_car_photo

        with override_settings(USE_OPENAI_STICKER_VALIDATION=False):
            result = analyze_car_photo(self._photo(), [])
            self.assertIn("error", result)

    def test_openai_exception_returns_none(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_car_photo

        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = RuntimeError("api down")

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            self.assertIsNone(analyze_car_photo(self._photo(), []))

    def test_success_returns_parsed_json(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_car_photo

        msg = MagicMock()
        msg.message.content = (
            '{"recognized": true, "make": "Toyota", "model": "Tacoma",'
            ' "confidence": 0.92, "sticker_id": 42}'
        )
        completion = MagicMock(choices=[msg])
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = completion

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_car_photo(self._photo(), [])
        self.assertTrue(result["recognized"])
        self.assertEqual(result["make"], "Toyota")
        self.assertEqual(result["confidence"], 0.92)
        self.assertEqual(result["sticker_id"], 42)

    def test_success_fills_default_fields(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_car_photo

        msg = MagicMock()
        msg.message.content = '{"recognized": false}'
        completion = MagicMock(choices=[msg])
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = completion

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_car_photo(self._photo(), [])
        self.assertFalse(result["recognized"])
        self.assertIsNone(result["make"])
        self.assertIsNone(result["sticker_id"])
        self.assertEqual(result["confidence"], 0.0)

    def test_invalid_json_returns_none(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_car_photo

        msg = MagicMock()
        msg.message.content = "not json {"
        completion = MagicMock(choices=[msg])
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = completion

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            self.assertIsNone(analyze_car_photo(self._photo(), []))

    def test_stickers_text_included_in_prompt(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_car_photo
        from albums.models import Album, Sticker

        album = Album.objects.create(title="A", theme="t", description="d")
        s1 = Sticker.objects.create(album=album, name="Ferrari", description="Italiano")

        captured_messages = []
        msg = MagicMock()
        msg.message.content = '{"recognized": true, "sticker_id": ' + str(s1.id) + '}'
        completion = MagicMock(choices=[msg])
        fake_client = MagicMock()

        def _capture(*args, **kwargs):
            captured_messages.append(kwargs.get("messages", []))
            return completion

        fake_client.chat.completions.create.side_effect = _capture

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            analyze_car_photo(self._photo(), [s1])

        user_msg = captured_messages[0][1]
        user_content = user_msg["content"][0]["text"]
        self.assertIn("Ferrari", user_content)
        self.assertIn(str(s1.id), user_content)


class AnalyzeUserStickerTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker
        from achievements.models import UserSticker

        self.user = _make_user(username="usval", email="usval@test.com")
        self.album = Album.objects.create(title="Val", theme="t", description="d")
        self.sticker = Sticker.objects.create(album=self.album, name="testcar")
        self.user_sticker = UserSticker.objects.create(
            user=self.user, sticker=self.sticker
        )

    def test_no_image_returns_unapproved(self):
        from achievements.services import analyze_user_sticker

        result = analyze_user_sticker(self.user_sticker)
        self.assertFalse(result["approved"])
        self.assertIn("No image", result["reason"])

    def test_disabled_auto_approves(self):
        from django.test import override_settings
        from achievements.services import analyze_user_sticker

        self.user_sticker.photo_url = "https://example.com/photo.jpg"
        self.user_sticker.save(update_fields=["photo_url"])

        with override_settings(USE_OPENAI_STICKER_VALIDATION=False):
            result = analyze_user_sticker(self.user_sticker)
        self.assertTrue(result["approved"])
        self.assertIn("disabled", result["reason"].lower())

    def test_match_high_confidence_approves(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_user_sticker

        self.user_sticker.photo_url = "https://example.com/photo.jpg"
        self.user_sticker.save(update_fields=["photo_url"])

        fake_response = MagicMock()
        fake_response.output_text = '{"match_score": 0.95, "is_match": true, "reason": "match"}'
        fake_response.id = "resp-1"
        fake_client = MagicMock()
        fake_client.responses.create.return_value = fake_response

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_user_sticker(self.user_sticker)
        self.assertTrue(result["approved"])
        self.assertEqual(result["match_score"], 0.95)
        self.assertTrue(result["is_match"])

    def test_match_low_confidence_does_not_approve(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_user_sticker

        self.user_sticker.photo_url = "https://example.com/photo.jpg"
        self.user_sticker.save(update_fields=["photo_url"])

        fake_response = MagicMock()
        fake_response.output_text = '{"match_score": 0.3, "is_match": true, "reason": "weak"}'
        fake_response.id = "resp-2"
        fake_client = MagicMock()
        fake_client.responses.create.return_value = fake_response

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_user_sticker(self.user_sticker)
        self.assertFalse(result["approved"])

    def test_no_match_does_not_approve(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_user_sticker

        self.user_sticker.photo_url = "https://example.com/photo.jpg"
        self.user_sticker.save(update_fields=["photo_url"])

        fake_response = MagicMock()
        fake_response.output_text = '{"match_score": 0.9, "is_match": false, "reason": "different car"}'
        fake_client = MagicMock()
        fake_client.responses.create.return_value = fake_response

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_user_sticker(self.user_sticker)
        self.assertFalse(result["approved"])
        self.assertFalse(result["is_match"])

    def test_invalid_json_returns_error(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_user_sticker

        self.user_sticker.photo_url = "https://example.com/photo.jpg"
        self.user_sticker.save(update_fields=["photo_url"])

        fake_response = MagicMock()
        fake_response.output_text = "not valid json {"
        fake_client = MagicMock()
        fake_client.responses.create.return_value = fake_response

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True), \
             patch("achievements.services.get_openai_client", return_value=fake_client):
            result = analyze_user_sticker(self.user_sticker)
        self.assertFalse(result["approved"])
        self.assertIn("error", result)


class ImagePayloadTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker
        from achievements.models import UserSticker

        self.user = _make_user(username="imp", email="imp@test.com")
        self.album = Album.objects.create(title="IP", theme="t", description="d")
        self.sticker = Sticker.objects.create(album=self.album, name="ipsticker")
        self.user_sticker = UserSticker.objects.create(
            user=self.user, sticker=self.sticker
        )

    def test_photo_url_takes_precedence(self):
        from achievements.services import _image_payload

        self.user_sticker.photo_url = "https://example.com/p.jpg"
        self.user_sticker.save(update_fields=["photo_url"])
        payload = _image_payload(self.user_sticker)
        self.assertEqual(payload["image_url"], "https://example.com/p.jpg")
        self.assertEqual(payload["type"], "input_image")

    def test_no_photo_no_url_returns_none(self):
        from achievements.services import _image_payload

        payload = _image_payload(self.user_sticker)
        self.assertIsNone(payload)

    def test_sticker_reference_no_image_returns_none(self):
        from achievements.services import _sticker_reference_payload

        self.assertIsNone(_sticker_reference_payload(self.sticker))

    def _attach_photo(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io

        img = Image.new("RGB", (10, 10), color=(20, 20, 20))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        self.user_sticker.photo = SimpleUploadedFile(
            "up.jpg", buf.getvalue(), content_type="image/jpeg"
        )
        self.user_sticker.save(update_fields=["photo"])

    def test_photo_read_success_returns_base64(self):
        from achievements.services import _image_payload

        self._attach_photo()
        payload = _image_payload(self.user_sticker)
        self.assertEqual(payload["type"], "input_image")
        self.assertTrue(payload["image_url"].startswith("data:image/jpeg;base64,"))

    def test_photo_file_not_found_returns_none(self):
        from unittest.mock import patch
        from achievements.services import _image_payload

        self._attach_photo()
        with patch.object(
            type(self.user_sticker.photo), "open", side_effect=FileNotFoundError
        ):
            payload = _image_payload(self.user_sticker)
        self.assertIsNone(payload)

    def test_photo_not_implemented_falls_back_to_url(self):
        from unittest.mock import patch, PropertyMock
        from achievements.services import _image_payload

        self._attach_photo()
        with patch.object(
            type(self.user_sticker.photo), "open", side_effect=NotImplementedError
        ), patch.object(
            type(self.user_sticker.photo), "url", new_callable=PropertyMock,
            return_value="https://cdn.example.com/up.jpg",
        ):
            payload = _image_payload(self.user_sticker)
        self.assertEqual(payload["image_url"], "https://cdn.example.com/up.jpg")

    def test_photo_value_error_on_url_returns_none(self):
        from unittest.mock import patch, PropertyMock
        from achievements.services import _image_payload

        self._attach_photo()
        with patch.object(
            type(self.user_sticker.photo), "open", side_effect=ValueError
        ), patch.object(
            type(self.user_sticker.photo), "url", new_callable=PropertyMock,
            side_effect=ValueError,
        ):
            payload = _image_payload(self.user_sticker)
        self.assertIsNone(payload)

    def _attach_reference(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io

        img = Image.new("RGB", (10, 10), color=(60, 60, 60))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        self.sticker.image_reference = SimpleUploadedFile(
            "ref.jpg", buf.getvalue(), content_type="image/jpeg"
        )
        self.sticker.save(update_fields=["image_reference"])

    def test_reference_read_success_returns_base64(self):
        from achievements.services import _sticker_reference_payload

        self._attach_reference()
        payload = _sticker_reference_payload(self.sticker)
        self.assertTrue(payload["image_url"].startswith("data:image/jpeg;base64,"))

    def test_reference_file_not_found_returns_none(self):
        from unittest.mock import patch
        from achievements.services import _sticker_reference_payload

        self._attach_reference()
        with patch.object(
            type(self.sticker.image_reference), "open", side_effect=FileNotFoundError
        ):
            self.assertIsNone(_sticker_reference_payload(self.sticker))

    def test_reference_not_implemented_falls_back_to_url(self):
        from unittest.mock import patch, PropertyMock
        from achievements.services import _sticker_reference_payload

        self._attach_reference()
        with patch.object(
            type(self.sticker.image_reference), "open", side_effect=NotImplementedError
        ), patch.object(
            type(self.sticker.image_reference), "url", new_callable=PropertyMock,
            return_value="https://cdn.example.com/ref.jpg",
        ):
            payload = _sticker_reference_payload(self.sticker)
        self.assertEqual(payload["image_url"], "https://cdn.example.com/ref.jpg")

    def test_reference_value_error_on_url_returns_none(self):
        from unittest.mock import patch, PropertyMock
        from achievements.services import _sticker_reference_payload

        self._attach_reference()
        with patch.object(
            type(self.sticker.image_reference), "open", side_effect=ValueError
        ), patch.object(
            type(self.sticker.image_reference), "url", new_callable=PropertyMock,
            side_effect=ValueError,
        ):
            self.assertIsNone(_sticker_reference_payload(self.sticker))


class UtilsTests(APITestCase):
    def setUp(self):
        self.alice = _make_user(username="ua1", email="ua1@test.com")
        self.bob = _make_user(username="ub1", email="ub1@test.com")
        self.eve = _make_user(username="ue1", email="ue1@test.com")

    def test_get_friend_ids_no_friends(self):
        from achievements.utils import get_friend_ids

        result = get_friend_ids(self.alice.id)
        self.assertEqual(result, [])

    def test_get_friend_ids_with_outgoing(self):
        from achievements.utils import get_friend_ids

        FriendRequest.objects.create(
            from_user=self.alice,
            to_user=self.bob,
            status=FriendRequest.STATUS_ACCEPTED,
        )
        result = get_friend_ids(self.alice.id)
        self.assertEqual(set(result), {self.bob.id})

    def test_get_friend_ids_with_incoming(self):
        from achievements.utils import get_friend_ids

        FriendRequest.objects.create(
            from_user=self.bob,
            to_user=self.alice,
            status=FriendRequest.STATUS_ACCEPTED,
        )
        result = get_friend_ids(self.alice.id)
        self.assertEqual(set(result), {self.bob.id})

    def test_get_friend_ids_dedupes(self):
        from achievements.utils import get_friend_ids

        FriendRequest.objects.create(
            from_user=self.alice,
            to_user=self.bob,
            status=FriendRequest.STATUS_ACCEPTED,
        )
        FriendRequest.objects.create(
            from_user=self.alice,
            to_user=self.eve,
            status=FriendRequest.STATUS_ACCEPTED,
        )
        result = get_friend_ids(self.alice.id)
        self.assertEqual(set(result), {self.bob.id, self.eve.id})

    def test_get_friend_ids_excludes_pending(self):
        from achievements.utils import get_friend_ids

        FriendRequest.objects.create(
            from_user=self.alice,
            to_user=self.bob,
            status=FriendRequest.STATUS_PENDING,
        )
        result = get_friend_ids(self.alice.id)
        self.assertEqual(result, [])

    def test_send_notification_no_channel_layer(self):
        from unittest.mock import patch
        from achievements.utils import send_notification

        with patch("achievements.utils.get_channel_layer", return_value=None):
            send_notification([1, 2], {"x": "y"})

    def test_send_notification_with_layer_and_broadcast(self):
        from unittest.mock import patch, MagicMock
        from achievements.utils import send_notification

        layer = MagicMock()
        with patch("achievements.utils.get_channel_layer", return_value=layer), \
             patch("achievements.utils.async_to_sync") as mocked_a2s:
            mocked_a2s.return_value = lambda *a, **kw: None
            send_notification([1, 2], {"x": "y"}, broadcast=True)
            self.assertGreaterEqual(mocked_a2s.call_count, 1)

    def test_send_notification_swallows_exception(self):
        from unittest.mock import patch
        from achievements.utils import send_notification

        with patch(
            "achievements.utils.get_channel_layer",
            side_effect=RuntimeError("layer down"),
        ):
            send_notification([1], {"a": "b"})

    def test_compute_user_points_no_stickers(self):
        from achievements.utils import compute_user_points

        self.assertEqual(compute_user_points(self.alice), 0)

    def test_compute_user_points_with_approved(self):
        from albums.models import Album, Sticker
        from achievements.utils import compute_user_points

        album = Album.objects.create(title="UP", theme="t")
        s1 = Sticker.objects.create(album=album, name="a", reward_points=10)
        s2 = Sticker.objects.create(album=album, name="b", reward_points=20)
        s3 = Sticker.objects.create(album=album, name="c", reward_points=99)
        UserSticker.objects.create(user=self.alice, sticker=s1, status=UserSticker.STATUS_APPROVED)
        UserSticker.objects.create(user=self.alice, sticker=s2, status=UserSticker.STATUS_APPROVED)
        UserSticker.objects.create(user=self.alice, sticker=s3, status=UserSticker.STATUS_PENDING)
        self.assertEqual(compute_user_points(self.alice), 30)

    def test_compute_user_points_with_sticker_unlock_model(self):
        from unittest.mock import patch, MagicMock
        from achievements.utils import compute_user_points

        fake_model = MagicMock()
        fake_qs = MagicMock()
        fake_qs.aggregate.return_value = {"total": 42}
        fake_model.objects.filter.return_value = fake_qs
        with patch("achievements.utils.apps.get_model", return_value=fake_model):
            self.assertEqual(compute_user_points(self.alice), 42)


class ValidateUserStickerTaskTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker

        self.user = _make_user(username="vu", email="vu@test.com")
        self.album = Album.objects.create(title="VAlb", theme="t", description="d")
        self.sticker = Sticker.objects.create(album=self.album, name="vs", reward_points=15)
        self.us = UserSticker.objects.create(
            user=self.user, sticker=self.sticker, status=UserSticker.STATUS_PENDING
        )

    def test_task_returns_when_user_sticker_not_found(self):
        from achievements.tasks import validate_user_sticker

        validate_user_sticker(99999)

    def test_task_skips_already_validated(self):
        from achievements.tasks import validate_user_sticker

        self.us.validated = True
        self.us.save(update_fields=["validated"])
        validate_user_sticker(self.us.id)
        self.us.refresh_from_db()
        self.assertTrue(self.us.validated)

    def test_task_error_sets_status_pending(self):
        from unittest.mock import patch
        from achievements.tasks import validate_user_sticker

        with patch(
            "achievements.tasks.analyze_user_sticker",
            return_value={"error": "openai down"},
        ):
            validate_user_sticker(self.us.id)
        self.us.refresh_from_db()
        self.assertEqual(self.us.status, UserSticker.STATUS_PENDING)
        self.assertFalse(self.us.validated)

    def test_task_approves_when_result_approved(self):
        from unittest.mock import patch
        from achievements.tasks import validate_user_sticker

        with patch(
            "achievements.tasks.analyze_user_sticker",
            return_value={
                "approved": True,
                "match_score": 0.9,
                "is_match": True,
                "reason": "exact",
            },
        ):
            validate_user_sticker(self.us.id)
        self.us.refresh_from_db()
        self.assertEqual(self.us.status, UserSticker.STATUS_APPROVED)
        self.assertTrue(self.us.validated)
        self.user.refresh_from_db()
        self.assertEqual(self.user.points, 15)

    def test_task_rejects_when_result_not_approved(self):
        from unittest.mock import patch
        from achievements.tasks import validate_user_sticker

        with patch(
            "achievements.tasks.analyze_user_sticker",
            return_value={
                "approved": False,
                "match_score": 0.2,
                "is_match": False,
                "reason": "no match",
            },
        ):
            validate_user_sticker(self.us.id)
        self.us.refresh_from_db()
        self.assertEqual(self.us.status, UserSticker.STATUS_REJECTED)
        self.assertFalse(self.us.validated)
        self.user.refresh_from_db()
        self.assertEqual(self.user.points, 0)


class AnalyzeUserStickerEdgeTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker

        self.user = _make_user(username="aus", email="aus@test.com")
        self.album = Album.objects.create(title="AUS", theme="t", description="d")
        self.sticker = Sticker.objects.create(
            album=self.album,
            name="ferrari",
            description="rojo italiano clasico",
        )

    def _make_user_sticker(self):
        us = UserSticker.objects.create(
            user=self.user,
            sticker=self.sticker,
            photo_url="https://example.com/photo.jpg",
        )
        return us

    def test_analyze_user_sticker_without_image(self):
        from achievements.services import analyze_user_sticker

        us = UserSticker.objects.create(user=self.user, sticker=self.sticker)
        result = analyze_user_sticker(us)
        self.assertFalse(result["approved"])
        self.assertIn("No image", result["reason"])

    def test_analyze_user_sticker_disabled_auto_approves(self):
        from django.test import override_settings
        from achievements.services import analyze_user_sticker

        us = self._make_user_sticker()
        with override_settings(USE_OPENAI_STICKER_VALIDATION=False):
            result = analyze_user_sticker(us)
        self.assertTrue(result["approved"])

    def test_analyze_user_sticker_high_match_approved(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_user_sticker

        us = self._make_user_sticker()

        fake_response = MagicMock()
        fake_response.output_text = (
            '{"match_score": 0.92, "is_match": true, "reason": "exact"}'
        )
        fake_response.id = "resp_123"
        fake_client = MagicMock()
        fake_client.responses.create.return_value = fake_response

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch(
                 "achievements.services.get_openai_client",
                 return_value=fake_client,
             ):
            result = analyze_user_sticker(us)
        self.assertTrue(result["approved"])
        self.assertEqual(result["match_score"], 0.92)

    def test_analyze_user_sticker_low_match_rejected(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_user_sticker

        us = self._make_user_sticker()

        fake_response = MagicMock()
        fake_response.output_text = (
            '{"match_score": 0.3, "is_match": false, "reason": "different"}'
        )
        fake_client = MagicMock()
        fake_client.responses.create.return_value = fake_response

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch(
                 "achievements.services.get_openai_client",
                 return_value=fake_client,
             ):
            result = analyze_user_sticker(us)
        self.assertFalse(result["approved"])

    def test_analyze_user_sticker_invalid_json_returns_error(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_user_sticker

        us = self._make_user_sticker()

        fake_response = MagicMock()
        fake_response.output_text = "not json"
        fake_client = MagicMock()
        fake_client.responses.create.return_value = fake_response

        with override_settings(USE_OPENAI_STICKER_VALIDATION=True, OPENAI_API_KEY="x"), \
             patch(
                 "achievements.services.get_openai_client",
                 return_value=fake_client,
             ):
            result = analyze_user_sticker(us)
        self.assertFalse(result["approved"])
        self.assertIn("Invalid JSON", result["error"])


class StickerUnlockViewTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker

        self.user = _make_user(username="unl", email="unl@test.com")
        self.album = Album.objects.create(title="UnlAlb", theme="t", description="d")
        self.sticker = Sticker.objects.create(album=self.album, name="unlsticker")

    def _payload(self):
        return {"photo_url": "https://example.com/photo.jpg"}

    def test_unlock_creates_user_sticker_validating(self):
        from unittest.mock import patch
        from achievements.models import UserSticker

        self.client.force_authenticate(self.user)
        with patch("achievements.views.validate_user_sticker.delay"):
            resp = self.client.post(
                reverse("sticker-unlock", args=[self.sticker.id]),
                self._payload(),
                format="json",
            )
        self.assertIn(resp.status_code, (status.HTTP_201_CREATED, status.HTTP_202_ACCEPTED))
        us = UserSticker.objects.get(user=self.user, sticker=self.sticker)
        self.assertEqual(us.status, UserSticker.STATUS_VALIDATING)
        self.assertFalse(us.validated)

    def test_unlock_existing_user_sticker_uses_202(self):
        from unittest.mock import patch
        from achievements.models import UserSticker

        UserSticker.objects.create(
            user=self.user, sticker=self.sticker, status=UserSticker.STATUS_APPROVED
        )
        self.client.force_authenticate(self.user)
        with patch("achievements.views.validate_user_sticker.delay"):
            resp = self.client.post(
                reverse("sticker-unlock", args=[self.sticker.id]),
                self._payload(),
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

    def test_unlock_falls_back_when_celery_unavailable(self):
        from unittest.mock import patch

        self.client.force_authenticate(self.user)
        with patch(
            "achievements.views.validate_user_sticker.delay",
            side_effect=RuntimeError("broker unavailable"),
        ), patch("achievements.views.validate_user_sticker.apply") as mocked_apply:
            resp = self.client.post(
                reverse("sticker-unlock", args=[self.sticker.id]),
                self._payload(),
                format="json",
            )
        self.assertIn(resp.status_code, (status.HTTP_201_CREATED, status.HTTP_202_ACCEPTED))
        mocked_apply.assert_called_once()

    def test_unlock_404_for_missing_sticker(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(
            reverse("sticker-unlock", args=[99999]),
            self._payload(),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_unlock_requires_auth(self):
        resp = self.client.post(
            reverse("sticker-unlock", args=[self.sticker.id]),
            self._payload(),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unlock_without_photo_or_url_returns_400(self):
        from unittest.mock import patch

        self.client.force_authenticate(self.user)
        with patch("achievements.views.validate_user_sticker.delay"):
            resp = self.client.post(
                reverse("sticker-unlock", args=[self.sticker.id]),
                {},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class MemberListViewTests(APITestCase):
    def setUp(self):
        self.me = _make_user(username="me", email="me@test.com")
        self.friend = _make_user(username="fr", email="fr@test.com")
        self.pending_in = _make_user(username="pi", email="pi@test.com")
        self.pending_out = _make_user(username="po", email="po@test.com")
        self.stranger = _make_user(username="st", email="st@test.com")
        self.staff = _make_user(username="sf", email="sf@test.com", is_staff=True)
        _be_friends(self.me, self.friend)
        FriendRequest.objects.create(from_user=self.pending_in, to_user=self.me)
        FriendRequest.objects.create(from_user=self.me, to_user=self.pending_out)

    def test_members_list_excludes_self_and_staff(self):
        self.client.force_authenticate(self.me)
        resp = self.client.get(reverse("friends-members"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        usernames = {u["username"] for u in resp.data}
        self.assertNotIn(self.me.username, usernames)
        self.assertNotIn(self.staff.username, usernames)
        self.assertIn(self.stranger.username, usernames)

    def test_members_list_includes_friend_status(self):
        self.client.force_authenticate(self.me)
        resp = self.client.get(reverse("friends-members"))
        friend_entry = next(u for u in resp.data if u["username"] == self.friend.username)
        self.assertEqual(friend_entry["relationship_status"], "friends")

    def test_members_list_includes_request_received(self):
        self.client.force_authenticate(self.me)
        resp = self.client.get(reverse("friends-members"))
        entry = next(u for u in resp.data if u["username"] == self.pending_in.username)
        self.assertEqual(entry["relationship_status"], "request_received")

    def test_members_list_includes_request_sent(self):
        self.client.force_authenticate(self.me)
        resp = self.client.get(reverse("friends-members"))
        entry = next(u for u in resp.data if u["username"] == self.pending_out.username)
        self.assertEqual(entry["relationship_status"], "request_sent")

    def test_members_list_stranger_no_relationship(self):
        self.client.force_authenticate(self.me)
        resp = self.client.get(reverse("friends-members"))
        entry = next(u for u in resp.data if u["username"] == self.stranger.username)
        self.assertEqual(entry["relationship_status"], "none")


class ChatMessagePermissionTests(APITestCase):
    def setUp(self):
        self.alice = _make_user(username="alc", email="alc@test.com")
        self.bob = _make_user(username="bbb", email="bbb@test.com")
        self.eve = _make_user(username="evb", email="evb@test.com")
        _be_friends(self.alice, self.bob)

    def test_strangers_cannot_send_message(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.post(
            reverse("chat-messages", args=[self.eve.id]),
            {"text": "ola"},
            format="json",
        )
        self.assertIn(resp.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST))

    def test_friends_can_send_message_with_channel_layer_failure(self):
        from unittest.mock import patch
        from achievements.models import ChatMessage

        self.client.force_authenticate(self.alice)
        with patch("achievements.views.get_channel_layer", return_value=None), \
             patch("users.push.send_push"):
            resp = self.client.post(
                reverse("chat-messages", args=[self.bob.id]),
                {"text": "ola desde alice"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            ChatMessage.objects.filter(
                sender=self.alice, recipient=self.bob, text="ola desde alice"
            ).exists()
        )

    def test_friends_message_with_channel_layer_exception_still_creates(self):
        from unittest.mock import patch, MagicMock
        from achievements.models import ChatMessage

        bad_layer = MagicMock()
        bad_layer.group_send.side_effect = RuntimeError("redis down")
        self.client.force_authenticate(self.alice)
        with patch("achievements.views.get_channel_layer", return_value=bad_layer), \
             patch("users.push.send_push"):
            resp = self.client.post(
                reverse("chat-messages", args=[self.bob.id]),
                {"text": "robust"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            ChatMessage.objects.filter(
                sender=self.alice, recipient=self.bob, text="robust"
            ).exists()
        )

    def test_self_chat_allowed(self):
        from unittest.mock import patch
        from achievements.models import ChatMessage

        self.client.force_authenticate(self.alice)
        with patch("achievements.views.get_channel_layer", return_value=None), \
             patch("users.push.send_push"):
            resp = self.client.post(
                reverse("chat-messages", args=[self.alice.id]),
                {"text": "nota personal"},
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class ChatRoomNameTests(APITestCase):
    def test_chat_room_name_is_order_independent(self):
        from achievements.consumers import chat_room_name

        self.assertEqual(chat_room_name(1, 2), chat_room_name(2, 1))
        self.assertEqual(chat_room_name(5, 5), "chat_5_5")

    def test_chat_room_name_format(self):
        from achievements.consumers import chat_room_name

        self.assertEqual(chat_room_name(10, 3), "chat_3_10")


class ChatConsumerTests(APITestCase):
    def setUp(self):
        self.alice = _make_user(username="ca", email="ca@test.com")
        self.bob = _make_user(username="cb", email="cb@test.com")
        self.eve = _make_user(username="ce", email="ce@test.com")
        _be_friends(self.alice, self.bob)

    def test_consumer_connects_when_friend(self):
        import asyncio
        from unittest.mock import AsyncMock
        from achievements.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.scope = {
                "user": self.alice,
                "url_route": {"kwargs": {"other_id": str(self.bob.id)}},
            }
            c.channel_name = "chan-1"
            c.channel_layer = AsyncMock()
            c.accept = AsyncMock()
            c.close = AsyncMock()

            async def fake_is_friend(*args, **kwargs):
                return True

            c._is_friend = fake_is_friend
            await c.connect()
            c.accept.assert_called_once()
            c.close.assert_not_called()

        asyncio.run(runner())

    def test_consumer_rejects_when_not_friend(self):
        import asyncio
        from unittest.mock import AsyncMock
        from achievements.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.scope = {
                "user": self.alice,
                "url_route": {"kwargs": {"other_id": str(self.eve.id)}},
            }
            c.channel_name = "chan-2"
            c.channel_layer = AsyncMock()
            c.accept = AsyncMock()
            c.close = AsyncMock()

            async def fake_is_friend(*args, **kwargs):
                return False

            c._is_friend = fake_is_friend
            await c.connect()
            c.close.assert_called_once()
            c.accept.assert_not_called()

        asyncio.run(runner())

    def test_consumer_rejects_unauthenticated(self):
        import asyncio
        from unittest.mock import AsyncMock
        from achievements.consumers import ChatConsumer
        from django.contrib.auth.models import AnonymousUser

        async def runner():
            c = ChatConsumer()
            c.scope = {
                "user": AnonymousUser(),
                "url_route": {"kwargs": {"other_id": str(self.bob.id)}},
            }
            c.channel_name = "chan-3"
            c.channel_layer = AsyncMock()
            c.accept = AsyncMock()
            c.close = AsyncMock()
            await c.connect()
            c.close.assert_called_once()
            c.accept.assert_not_called()

        asyncio.run(runner())

    def test_consumer_disconnect_calls_group_discard(self):
        import asyncio
        from unittest.mock import AsyncMock
        from achievements.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.channel_name = "chan-d"
            c.room_group_name = "chat_1_2"
            c.channel_layer = AsyncMock()
            await c.disconnect(1000)
            c.channel_layer.group_discard.assert_called_once()

        asyncio.run(runner())

    def test_consumer_receive_empty_text_skipped(self):
        import asyncio
        from unittest.mock import AsyncMock
        from achievements.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.scope = {
                "user": self.alice,
                "url_route": {"kwargs": {"other_id": str(self.bob.id)}},
            }
            c.channel_name = "chan-r"
            c.channel_layer = AsyncMock()
            await c.receive_json({"text": "   "})
            c.channel_layer.group_send.assert_not_called()

        asyncio.run(runner())

    def test_consumer_receive_creates_message_and_broadcasts(self):
        import asyncio
        from unittest.mock import AsyncMock
        from achievements.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.scope = {
                "user": self.alice,
                "url_route": {"kwargs": {"other_id": str(self.bob.id)}},
            }
            c.channel_name = "chan-msg"
            c.room_group_name = "chat_alice_bob"
            c.channel_layer = AsyncMock()

            async def fake_create(sender_id, recipient_id, text):
                return {"id": 1, "text": text, "sender_id": sender_id}

            c._create_message = fake_create
            await c.receive_json({"text": "hola bob"})
            self.assertEqual(c.channel_layer.group_send.call_count, 2)

        asyncio.run(runner())

    def test_consumer_chat_message_handler_sends_payload(self):
        import asyncio
        from unittest.mock import AsyncMock
        from achievements.consumers import ChatConsumer

        async def runner():
            c = ChatConsumer()
            c.send_json = AsyncMock()
            await c.chat_message({"message": {"text": "hola"}})
            c.send_json.assert_called_once_with(
                {"type": "chat_message", "message": {"text": "hola"}}
            )

        asyncio.run(runner())


class NotificationsConsumerTests(APITestCase):
    def setUp(self):
        self.user = _make_user(username="nu", email="nu@test.com")

    def test_connect_accepts_authenticated(self):
        import asyncio
        from unittest.mock import AsyncMock
        from achievements.consumers import NotificationsConsumer

        async def runner():
            c = NotificationsConsumer()
            c.scope = {"user": self.user}
            c.channel_name = "n-1"
            c.channel_layer = AsyncMock()
            c.accept = AsyncMock()
            c.close = AsyncMock()
            await c.connect()
            c.accept.assert_called_once()
            c.close.assert_not_called()

        asyncio.run(runner())

    def test_connect_rejects_anonymous(self):
        import asyncio
        from unittest.mock import AsyncMock
        from achievements.consumers import NotificationsConsumer
        from django.contrib.auth.models import AnonymousUser

        async def runner():
            c = NotificationsConsumer()
            c.scope = {"user": AnonymousUser()}
            c.channel_name = "n-2"
            c.channel_layer = AsyncMock()
            c.accept = AsyncMock()
            c.close = AsyncMock()
            await c.connect()
            c.close.assert_called_once()
            c.accept.assert_not_called()

        asyncio.run(runner())

    def test_disconnect_discards_groups(self):
        import asyncio
        from unittest.mock import AsyncMock
        from achievements.consumers import NotificationsConsumer

        async def runner():
            c = NotificationsConsumer()
            c.channel_name = "n-3"
            c.group_name = "user_42"
            c.channel_layer = AsyncMock()
            await c.disconnect(1000)
            self.assertEqual(c.channel_layer.group_discard.call_count, 2)

        asyncio.run(runner())

    def test_notification_handler_sends_payload(self):
        import asyncio
        from unittest.mock import AsyncMock
        from achievements.consumers import NotificationsConsumer

        async def runner():
            c = NotificationsConsumer()
            c.send_json = AsyncMock()
            await c.notification(
                {"payload": {"title": "T", "message": "M"}}
            )
            c.send_json.assert_called_once_with(
                {"type": "notification", "title": "T", "message": "M"}
            )

        asyncio.run(runner())


class AnalyzePhotoGlobalCatalogTests(APITestCase):
    def _fake_image_bytes(self):
        from PIL import Image
        import io

        img = Image.new("RGB", (200, 200), color=(50, 100, 150))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return buf

    def _fake_main_response(self, matches=None):
        import json
        from unittest.mock import MagicMock

        payload = {
            "recognized": True,
            "item_count": len(matches or []),
            "photo_category": "test",
            "matches": matches or [],
            "fun_fact": "ok",
        }
        msg = MagicMock()
        msg.message.content = json.dumps(payload)
        return MagicMock(choices=[msg])

    def test_catalog_includes_album_and_stickers_text(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from albums.models import Album, Sticker
        from achievements.services import analyze_photo_global

        album = Album.objects.create(
            title="Carros JDM",
            theme="autos",
            description="d",
            tags="autos,jdm,deportivos",
        )
        s1 = Sticker.objects.create(album=album, name="Skyline", description="R34")

        captured = []
        completion = self._fake_main_response()
        fake_main = MagicMock()
        fake_main.chat.completions.create.side_effect = lambda *a, **kw: (
            captured.append(kw.get("messages", [])) or completion
        )

        with override_settings(VISION_PREFILTER_ENABLED=False), \
             patch("achievements.services.get_openai_client", return_value=fake_main):
            analyze_photo_global(
                self._fake_image_bytes(), Album.objects.prefetch_related("stickers").all()
            )

        system_text = captured[0][0]["content"]
        self.assertIn("PASO 1", system_text)
        user_content = captured[0][1]["content"]
        catalog_text = next(
            (c["text"] for c in user_content if c.get("type") == "text"
             and "Carros JDM" in c.get("text", "")),
            None,
        )
        self.assertIsNotNone(catalog_text)
        self.assertIn("Skyline", catalog_text)
        self.assertIn(str(s1.id), catalog_text)

    def test_custom_prompt_album_is_appended(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from albums.models import Album
        from achievements.services import analyze_photo_global

        Album.objects.create(
            title="Especial",
            theme="custom",
            description="d",
            tags="autos",
            custom_prompt="Reglas extra para este album",
        )

        captured = []
        completion = self._fake_main_response()
        fake_main = MagicMock()
        fake_main.chat.completions.create.side_effect = lambda *a, **kw: (
            captured.append(kw.get("messages", [])) or completion
        )

        with override_settings(VISION_PREFILTER_ENABLED=False), \
             patch("achievements.services.get_openai_client", return_value=fake_main):
            analyze_photo_global(
                self._fake_image_bytes(), Album.objects.prefetch_related("stickers").all()
            )

        system_text = captured[0][0]["content"]
        self.assertIn("INSTRUCCIONES ESPECIALES POR ALBUM", system_text)
        self.assertIn("Reglas extra para este album", system_text)

    def test_person_album_without_refs_uses_text_prompt(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from albums.models import Album, Sticker
        from achievements.services import analyze_photo_global

        album = Album.objects.create(
            title="Profes ITESO",
            theme="profes",
            description="d",
            tags="profes,personas",
        )
        Sticker.objects.create(album=album, name="Profe Juan", description="Cara redonda")

        captured = []
        completion = self._fake_main_response()
        fake_main = MagicMock()
        fake_main.chat.completions.create.side_effect = lambda *a, **kw: (
            captured.append(kw.get("messages", [])) or completion
        )

        with override_settings(VISION_PREFILTER_ENABLED=False), \
             patch("achievements.services.get_openai_client", return_value=fake_main):
            analyze_photo_global(
                self._fake_image_bytes(), Album.objects.prefetch_related("stickers").all()
            )

        system_text = captured[0][0]["content"]
        self.assertIn("PERSONAS:", system_text)
        self.assertNotIn("PERSONAS CON REFERENCIA VISUAL", system_text)

    def test_legacy_sticker_id_field_is_promoted_to_matches(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_photo_global

        import json

        legacy_payload = {
            "recognized": True,
            "sticker_id": 7,
            "detected_item": "ford",
            "confidence": 0.8,
            "album_id": 1,
        }
        msg = MagicMock()
        msg.message.content = json.dumps(legacy_payload)
        completion = MagicMock(choices=[msg])
        fake_main = MagicMock()
        fake_main.chat.completions.create.return_value = completion

        with override_settings(VISION_PREFILTER_ENABLED=False), \
             patch("achievements.services.get_openai_client", return_value=fake_main):
            result = analyze_photo_global(self._fake_image_bytes(), [])

        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["matches"][0]["sticker_id"], 7)
        self.assertEqual(result["item_count"], 1)

    def test_match_defaults_filled(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_photo_global

        import json

        payload = {
            "recognized": True,
            "matches": [{}],
            "fun_fact": "x",
        }
        msg = MagicMock()
        msg.message.content = json.dumps(payload)
        completion = MagicMock(choices=[msg])
        fake_main = MagicMock()
        fake_main.chat.completions.create.return_value = completion

        with override_settings(VISION_PREFILTER_ENABLED=False), \
             patch("achievements.services.get_openai_client", return_value=fake_main):
            result = analyze_photo_global(self._fake_image_bytes(), [])

        m = result["matches"][0]
        self.assertEqual(m["confidence"], 0.0)
        self.assertIsNone(m["sticker_id"])
        self.assertIsNone(m["album_id"])
        self.assertEqual(m["detected_item"], "")
        self.assertEqual(m["detected_category"], "")
        self.assertEqual(m["reason"], "")

    def test_catalog_exception_is_swallowed_and_continues(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from achievements.services import analyze_photo_global

        class FakeBrokenAlbum:
            @property
            def tags(self):
                raise RuntimeError("boom")

        completion = self._fake_main_response()
        fake_main = MagicMock()
        fake_main.chat.completions.create.return_value = completion

        with override_settings(VISION_PREFILTER_ENABLED=False), \
             patch("achievements.services.get_openai_client", return_value=fake_main):
            result = analyze_photo_global(self._fake_image_bytes(), [FakeBrokenAlbum()])

        self.assertIsNotNone(result)

    def test_person_album_with_reference_photos_attaches_images(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock
        from albums.models import Album, Sticker, StickerReferencePhoto
        from achievements.services import analyze_photo_global

        album = Album.objects.create(
            title="Profes con foto",
            theme="profes",
            description="d",
            tags="profes,personas",
        )
        sticker = Sticker.objects.create(album=album, name="Profe Ana")
        ref = StickerReferencePhoto.objects.create(sticker=sticker, label="frente")

        captured = []
        completion = self._fake_main_response()
        fake_main = MagicMock()
        fake_main.chat.completions.create.side_effect = lambda *a, **kw: (
            captured.append(kw.get("messages", [])) or completion
        )

        with override_settings(VISION_PREFILTER_ENABLED=False), \
             patch("achievements.services.get_openai_client", return_value=fake_main), \
             patch.object(
                 type(ref.photo), "url", new_callable=__import__("unittest.mock", fromlist=["PropertyMock"]).PropertyMock,
                 return_value="https://cdn.example.com/ref-ana.jpg",
             ):
            analyze_photo_global(
                self._fake_image_bytes(),
                Album.objects.prefetch_related("stickers", "stickers__reference_photos").all(),
            )

        system_text = captured[0][0]["content"]
        self.assertIn("PERSONAS CON REFERENCIA VISUAL", system_text)
        user_content = captured[0][1]["content"]
        has_ref_image = any(
            c.get("type") == "image_url"
            and "cdn.example.com/ref-ana.jpg" in str(c.get("image_url", {}))
            for c in user_content
        )
        self.assertTrue(has_ref_image)

    def test_person_album_reference_url_exception_swallowed(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock, PropertyMock
        from albums.models import Album, Sticker, StickerReferencePhoto
        from achievements.services import analyze_photo_global

        album = Album.objects.create(
            title="Profes rotos", theme="profes", description="d", tags="profes",
        )
        sticker = Sticker.objects.create(album=album, name="Profe Z")
        ref = StickerReferencePhoto.objects.create(sticker=sticker, label="x")

        completion = self._fake_main_response()
        fake_main = MagicMock()
        fake_main.chat.completions.create.return_value = completion

        with override_settings(VISION_PREFILTER_ENABLED=False), \
             patch("achievements.services.get_openai_client", return_value=fake_main), \
             patch.object(
                 type(ref.photo), "url", new_callable=PropertyMock, side_effect=ValueError,
             ):
            result = analyze_photo_global(
                self._fake_image_bytes(),
                Album.objects.prefetch_related("stickers", "stickers__reference_photos").all(),
            )
        self.assertIsNotNone(result)

    def test_photo_read_exception_returns_none(self):
        from django.test import override_settings
        from achievements.services import analyze_photo_global

        class BrokenStream:
            def read(self):
                raise IOError("cannot read")

            def seek(self, *a):
                pass

        with override_settings(VISION_PREFILTER_ENABLED=False):
            result = analyze_photo_global(BrokenStream(), [])
        self.assertIsNone(result)

    def test_person_album_single_image_reference_attaches(self):
        from django.test import override_settings
        from unittest.mock import patch, MagicMock, PropertyMock
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io
        from albums.models import Album, Sticker
        from achievements.services import analyze_photo_global

        album = Album.objects.create(
            title="Profes single ref", theme="profes", description="d", tags="profes,personas",
        )
        img = Image.new("RGB", (10, 10), color=(5, 5, 5))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        sticker = Sticker.objects.create(
            album=album, name="Profe Solo",
            image_reference=SimpleUploadedFile("r.jpg", buf.getvalue(), content_type="image/jpeg"),
        )

        captured = []
        completion = self._fake_main_response()
        fake_main = MagicMock()
        fake_main.chat.completions.create.side_effect = lambda *a, **kw: (
            captured.append(kw.get("messages", [])) or completion
        )

        with override_settings(VISION_PREFILTER_ENABLED=False), \
             patch("achievements.services.get_openai_client", return_value=fake_main), \
             patch.object(
                 type(sticker.image_reference), "url", new_callable=PropertyMock,
                 return_value="https://cdn.example.com/profe-solo.jpg",
             ):
            analyze_photo_global(
                self._fake_image_bytes(),
                Album.objects.prefetch_related("stickers", "stickers__reference_photos").all(),
            )

        user_content = captured[0][1]["content"]
        has_ref = any(
            c.get("type") == "image_url"
            and "profe-solo.jpg" in str(c.get("image_url", {}))
            for c in user_content
        )
        self.assertTrue(has_ref)


class JwtAuthMiddlewareTests(APITestCase):
    def setUp(self):
        self.user = _make_user(username="wsuser", email="ws@test.com")

    def _run(self, query_string):
        from asgiref.sync import async_to_sync
        from achievements.auth import JwtAuthMiddlewareStack

        captured = {}

        async def fake_inner(scope, receive, send):
            captured["scope"] = scope

        mw = JwtAuthMiddlewareStack(fake_inner)
        scope = {"query_string": query_string}
        async_to_sync(mw)(scope, None, None)
        return captured["scope"]

    def test_valid_token_sets_user(self):
        from rest_framework_simplejwt.tokens import AccessToken

        token = str(AccessToken.for_user(self.user))
        scope = self._run(f"token={token}".encode())
        self.assertEqual(scope["user"].id, self.user.id)

    def test_no_token_is_anonymous(self):
        from django.contrib.auth.models import AnonymousUser

        scope = self._run(b"")
        self.assertIsInstance(scope["user"], AnonymousUser)

    def test_invalid_token_is_anonymous(self):
        from django.contrib.auth.models import AnonymousUser

        scope = self._run(b"token=garbage-not-a-jwt")
        self.assertIsInstance(scope["user"], AnonymousUser)

    def test_token_for_deleted_user_is_anonymous(self):
        from django.contrib.auth.models import AnonymousUser
        from rest_framework_simplejwt.tokens import AccessToken

        token = str(AccessToken.for_user(self.user))
        self.user.delete()
        scope = self._run(f"token={token}".encode())
        self.assertIsInstance(scope["user"], AnonymousUser)


class OpenAIClientTests(APITestCase):
    def tearDown(self):
        from badgeup.openai_client import get_openai_client

        get_openai_client.cache_clear()

    def test_raises_when_no_api_key(self):
        from django.test import override_settings
        from badgeup.openai_client import get_openai_client

        get_openai_client.cache_clear()
        with override_settings(OPENAI_API_KEY=""):
            with self.assertRaises(RuntimeError):
                get_openai_client()

    def test_returns_client_when_key_present(self):
        from unittest.mock import patch
        from django.test import override_settings
        import badgeup.openai_client as oc

        oc.get_openai_client.cache_clear()
        with override_settings(OPENAI_API_KEY="sk-test-key"), \
             patch.object(oc, "OpenAI", return_value="fake-client") as mock_openai:
            client = oc.get_openai_client()
        self.assertEqual(client, "fake-client")
        mock_openai.assert_called_once_with(api_key="sk-test-key")

    def test_raises_when_sdk_missing(self):
        from unittest.mock import patch
        from django.test import override_settings
        import badgeup.openai_client as oc

        oc.get_openai_client.cache_clear()
        with override_settings(OPENAI_API_KEY="sk-test-key"), \
             patch.object(oc, "OpenAI", None):
            with self.assertRaises(RuntimeError):
                oc.get_openai_client()


class SyncUserPointsCommandTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker
        from achievements.models import UserSticker

        self.user = _make_user(username="syncpts", email="sp@test.com")
        self.album = Album.objects.create(title="SP", theme="t", description="d")
        self.sticker = Sticker.objects.create(album=self.album, name="sps", reward_points=30)
        UserSticker.objects.create(
            user=self.user, sticker=self.sticker, validated=True,
            status=UserSticker.STATUS_APPROVED,
        )
        self.user.points = 0
        self.user.save(update_fields=["points"])

    def test_command_syncs_points(self):
        from io import StringIO
        from django.core.management import call_command

        out = StringIO()
        call_command("sync_user_points", stdout=out)
        self.user.refresh_from_db()
        self.assertEqual(self.user.points, 30)
        self.assertIn("Sincronizados", out.getvalue())

    def test_command_no_change_when_already_synced(self):
        from io import StringIO
        from django.core.management import call_command

        self.user.points = 30
        self.user.save(update_fields=["points"])
        out = StringIO()
        call_command("sync_user_points", stdout=out)
        self.user.refresh_from_db()
        self.assertEqual(self.user.points, 30)


class SeedRandomUnlocksCommandTests(APITestCase):
    def setUp(self):
        from albums.models import Album, Sticker

        self.user = _make_user(username="seeduser", email="seed@test.com")
        self.album = Album.objects.create(title="SeedA", theme="t", description="d")
        for i in range(6):
            Sticker.objects.create(album=self.album, name=f"seed{i}", reward_points=10)

    def test_seeds_unlocks_for_user(self):
        from io import StringIO
        from django.core.management import call_command
        from achievements.models import UserSticker

        out = StringIO()
        call_command("seed_random_sticker_unlocks", "--per-user", "3", stdout=out)
        self.assertEqual(UserSticker.objects.filter(user=self.user).count(), 3)
        self.assertIn("Seeded", out.getvalue())

    def test_purge_then_seed(self):
        from io import StringIO
        from django.core.management import call_command
        from achievements.models import UserSticker

        UserSticker.objects.create(user=self.user, sticker=self.album.stickers.first())
        out = StringIO()
        call_command("seed_random_sticker_unlocks", "--per-user", "2", "--purge", stdout=out)
        self.assertIn("Purged", out.getvalue())

    def test_no_stickers_warns(self):
        from io import StringIO
        from django.core.management import call_command
        from albums.models import Sticker

        Sticker.objects.all().delete()
        out = StringIO()
        call_command("seed_random_sticker_unlocks", stdout=out)
        self.assertIn("No users or stickers found", out.getvalue())

    def test_filter_by_username(self):
        from io import StringIO
        from django.core.management import call_command
        from achievements.models import UserSticker

        other = _make_user(username="seedother", email="so@test.com")
        out = StringIO()
        call_command(
            "seed_random_sticker_unlocks", "--per-user", "2", "--users", "seeduser", stdout=out
        )
        self.assertEqual(UserSticker.objects.filter(user=other).count(), 0)
        self.assertGreater(UserSticker.objects.filter(user=self.user).count(), 0)
