from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from albums.models import Sticker

from users.models import User

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .consumers import chat_room_name
from .models import ChatMessage, FriendRequest, UserSticker
from .serializers import (
    ChatMessageSerializer,
    FriendRequestSerializer,
    MemberSerializer,
    MemberWithRelationSerializer,
    StickerUnlockSerializer,
    UserStickerHistorySerializer,
    UserStickerSerializer,
)
from .tasks import validate_user_sticker
from .utils import send_notification


class StickerUnlockView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        sticker = get_object_or_404(Sticker, pk=pk)
        user_sticker, created = UserSticker.objects.get_or_create(
            user=request.user,
            sticker=sticker,
        )

        serializer = StickerUnlockSerializer(
            user_sticker,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        for attr, value in serializer.validated_data.items():
            setattr(user_sticker, attr, value)
        user_sticker.status = UserSticker.STATUS_VALIDATING
        user_sticker.validated = False
        user_sticker.save()

        try:
            validate_user_sticker.delay(user_sticker.id)
        except Exception:  # pragma: no cover - fallback for missing broker
            validate_user_sticker.apply(args=[user_sticker.id])

        output_serializer = UserStickerSerializer(user_sticker)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_202_ACCEPTED
        return Response(output_serializer.data, status=status_code)


class FriendRequestListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FriendRequestSerializer

    def get_queryset(self):
        scope = self.request.query_params.get("scope", "all")
        qs = FriendRequest.objects.select_related("from_user", "to_user")
        if scope == "received":
            qs = qs.filter(to_user=self.request.user)
        elif scope == "sent":
            qs = qs.filter(from_user=self.request.user)
        else:
            qs = qs.filter(
                models.Q(from_user=self.request.user) | models.Q(to_user=self.request.user)
            )
        status_param = self.request.query_params.get("status")
        if status_param in {FriendRequest.STATUS_PENDING, FriendRequest.STATUS_ACCEPTED, FriendRequest.STATUS_REJECTED}:
            qs = qs.filter(status=status_param)
        return qs.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        to_user_id = request.data.get("to_user")
        if not to_user_id:
            return Response({"detail": "to_user is required"}, status=status.HTTP_400_BAD_REQUEST)
        if str(to_user_id) == str(request.user.id):
            return Response({"detail": "No puedes enviarte una solicitud a ti mismo."}, status=status.HTTP_400_BAD_REQUEST)

        target = get_object_or_404(User, pk=to_user_id)

        existing = FriendRequest.objects.filter(
            models.Q(from_user=request.user, to_user=target)
            | models.Q(from_user=target, to_user=request.user)
        ).first()

        if existing:
            if existing.status == FriendRequest.STATUS_ACCEPTED:
                serializer = self.get_serializer(existing)
                return Response(serializer.data, status=status.HTTP_200_OK)
            if existing.status == FriendRequest.STATUS_PENDING:
                if existing.from_user_id == request.user.id:
                    serializer = self.get_serializer(existing)
                    return Response(serializer.data, status=status.HTTP_200_OK)
                existing.status = FriendRequest.STATUS_ACCEPTED
                existing.responded_at = timezone.now()
                existing.save(update_fields=["status", "responded_at"])
                serializer = self.get_serializer(existing)
                return Response(serializer.data, status=status.HTTP_200_OK)
            if existing.status == FriendRequest.STATUS_REJECTED:
                existing.from_user = request.user
                existing.to_user = target
                existing.status = FriendRequest.STATUS_PENDING
                existing.responded_at = None
                existing.save(update_fields=["from_user", "to_user", "status", "responded_at"])
                serializer = self.get_serializer(existing)
                return Response(serializer.data, status=status.HTTP_201_CREATED)

        friend_request = FriendRequest.objects.create(
            from_user=request.user,
            to_user=target,
            status=FriendRequest.STATUS_PENDING,
        )
        send_notification(
            [target.id],
            {
                "title": "Solicitud de amistad",
                "message": f"{request.user.username} quiere agregarte",
                "category": "friend_request",
            },
        )
        serializer = self.get_serializer(friend_request)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class FriendRequestActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, action: str):
        fr = get_object_or_404(
            FriendRequest.objects.select_related("from_user", "to_user"),
            pk=pk,
        )
        if action == "accept":
            if fr.to_user != request.user or fr.status != FriendRequest.STATUS_PENDING:
                return Response({"detail": "No puedes aceptar esta solicitud."}, status=status.HTTP_400_BAD_REQUEST)
            fr.status = FriendRequest.STATUS_ACCEPTED
            fr.responded_at = timezone.now()
            fr.save(update_fields=["status", "responded_at"])
            send_notification(
                [fr.from_user_id],
                {
                    "title": "Solicitud aceptada",
                    "message": f"{request.user.username} ahora es tu amigo",
                    "category": "friend_accept",
                },
            )
        elif action == "reject":
            if fr.to_user != request.user or fr.status != FriendRequest.STATUS_PENDING:
                return Response({"detail": "No puedes rechazar esta solicitud."}, status=status.HTTP_400_BAD_REQUEST)
            fr.status = FriendRequest.STATUS_REJECTED
            fr.responded_at = timezone.now()
            fr.save(update_fields=["status", "responded_at"])
        elif action == "cancel":
            if fr.from_user != request.user or fr.status != FriendRequest.STATUS_PENDING:
                return Response({"detail": "No puedes cancelar esta solicitud."}, status=status.HTTP_400_BAD_REQUEST)
            fr.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        elif action == "remove":
            if fr.status != FriendRequest.STATUS_ACCEPTED or (
                fr.from_user != request.user and fr.to_user != request.user
            ):
                return Response({"detail": "No puedes eliminar esta amistad."}, status=status.HTTP_400_BAD_REQUEST)
            fr.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response({"detail": "Acción no válida"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = FriendRequestSerializer(fr)
        return Response(serializer.data, status=status.HTTP_200_OK)


class FriendRequestAcceptView(FriendRequestActionView):
    def post(self, request, pk):
        return super().post(request, pk, "accept")


class FriendRequestRejectView(FriendRequestActionView):
    def post(self, request, pk):
        return super().post(request, pk, "reject")


class FriendRequestCancelView(FriendRequestActionView):
    def post(self, request, pk):
        return super().post(request, pk, "cancel")


class FriendRemoveView(FriendRequestActionView):
    def post(self, request, pk):
        return super().post(request, pk, "remove")


class FriendsListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MemberWithRelationSerializer

    def get_queryset(self):
        user = self.request.user
        accepted = list(
            FriendRequest.objects.filter(
                status=FriendRequest.STATUS_ACCEPTED,
            )
            .filter(models.Q(from_user=user) | models.Q(to_user=user))
            .select_related("from_user", "to_user")
        )
        other_ids = []
        relationship_map = {}
        for fr in accepted:
            other = fr.to_user if fr.from_user_id == user.id else fr.from_user
            other_ids.append(other.id)
            relationship_map[other.id] = {
                "status": "friends",
                "request_id": fr.id,
            }
        self.relationship_map = relationship_map
        return User.objects.filter(id__in=other_ids)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["relationship_map"] = getattr(self, "relationship_map", {})
        return ctx


class MemberListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        users = User.objects.exclude(id=request.user.id)
        serializer = MemberSerializer(users, many=True, context={"request": request})
        return Response(serializer.data)


class ChatMessageView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChatMessageSerializer

    def get_queryset(self):
        other_id = int(self.kwargs["other_id"])
        user = self.request.user
        qs = ChatMessage.objects.filter(
            models.Q(sender=user, recipient_id=other_id)
            | models.Q(sender_id=other_id, recipient=user)
        ).select_related("sender", "recipient")
        limit = int(self.request.query_params.get("limit", 50))
        return qs.order_by("-created_at")[: max(1, min(limit, 200))]

    def perform_create(self, serializer):
        other_id = int(self.kwargs["other_id"])
        user = self.request.user
        if not self._is_friend(user.id, other_id):
            raise PermissionDenied("No tienes permiso para chatear con este usuario.")
        other = get_object_or_404(User, pk=other_id)
        instance = serializer.save(sender=user, recipient=other)
        payload = ChatMessageSerializer(instance, context={"request": self.request}).data
        channel_layer = get_channel_layer()
        group = chat_room_name(user.id, other_id)
        async_to_sync(channel_layer.group_send)(group, {"type": "chat.message", "message": payload})
        async_to_sync(channel_layer.group_send)(
            f"user_{other_id}",
            {
                "type": "notification",
                "payload": {
                    "title": "Nuevo mensaje",
                    "message": f"{user.username}: {(instance.text or '')[:80]}",
                },
            },
        )

    def _is_friend(self, user_id: int, other_id: int) -> bool:
        if user_id == other_id:
            return True
        return FriendRequest.objects.filter(
            status=FriendRequest.STATUS_ACCEPTED,
            from_user_id__in=[user_id, other_id],
            to_user_id__in=[user_id, other_id],
        ).exists()


class UserStickerHistoryView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserStickerHistorySerializer

    def get_queryset(self):
        return (
            UserSticker.objects.filter(user=self.request.user, status=UserSticker.STATUS_APPROVED)
            .select_related("sticker__album")
            .order_by("-unlocked_at")
        )
