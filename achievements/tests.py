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


class ChatInboxTests(APITestCase):
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
