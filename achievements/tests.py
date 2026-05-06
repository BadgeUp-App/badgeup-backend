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
