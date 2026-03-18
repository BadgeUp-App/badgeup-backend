from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model

from achievements.models import ChatMessage, FriendRequest
from achievements.serializers import ChatMessageSerializer


User = get_user_model()


def chat_room_name(user_a: int, user_b: int) -> str:
    left, right = sorted([user_a, user_b])
    return f"chat_{left}_{right}"


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        other_id = self.scope["url_route"]["kwargs"].get("other_id")
        if not user or not user.is_authenticated or not other_id:
            await self.close()
            return
        allowed = await self._is_friend(user.id, int(other_id))
        if not allowed:
            await self.close()
            return
        self.room_group_name = chat_room_name(user.id, int(other_id))
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    @sync_to_async
    def _is_friend(self, user_id: int, other_id: int) -> bool:
        if user_id == other_id:
            return True
        return FriendRequest.objects.filter(
            status=FriendRequest.STATUS_ACCEPTED,
            from_user_id__in=[user_id, other_id],
            to_user_id__in=[user_id, other_id],
        ).exists()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        user = self.scope.get("user")
        other_id = self.scope["url_route"]["kwargs"].get("other_id")
        if not user or not user.is_authenticated or not other_id:
            return
        text = (content.get("text") or "").strip()
        if not text:
            return
        message = await self._create_message(user.id, int(other_id), text)
        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "chat.message", "message": message},
        )
        await self.channel_layer.group_send(
            f"user_{other_id}",
            {
                "type": "notification",
                "payload": {
                    "title": "Nuevo mensaje",
                    "message": f"{user.username}: {text[:80]}",
                },
            },
        )

    @sync_to_async
    def _create_message(self, sender_id: int, recipient_id: int, text: str):
        sender = User.objects.get(pk=sender_id)
        recipient = User.objects.get(pk=recipient_id)
        msg = ChatMessage.objects.create(sender=sender, recipient=recipient, text=text)
        return ChatMessageSerializer(msg).data

    async def chat_message(self, event):
        await self.send_json({"type": "chat_message", "message": event["message"]})


class NotificationsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return
        self.group_name = f"user_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.channel_layer.group_add("broadcast", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        await self.channel_layer.group_discard("broadcast", self.channel_name)

    async def notification(self, event):
        await self.send_json({"type": "notification", **event.get("payload", {})})
