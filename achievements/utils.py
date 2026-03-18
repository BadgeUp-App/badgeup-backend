from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.apps import apps
from django.db.models import Sum

from .models import FriendRequest, UserSticker


def get_friend_ids(user_id: int) -> list[int]:
    accepted = FriendRequest.objects.filter(
        status=FriendRequest.STATUS_ACCEPTED,
        from_user_id=user_id,
    ).values_list("to_user_id", flat=True)
    accepted_rev = FriendRequest.objects.filter(
        status=FriendRequest.STATUS_ACCEPTED,
        to_user_id=user_id,
    ).values_list("from_user_id", flat=True)
    return list(set(accepted) | set(accepted_rev))


def send_notification(user_ids: list[int], payload: dict, broadcast: bool = False):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    if broadcast:
        async_to_sync(channel_layer.group_send)("broadcast", {"type": "notification", "payload": payload})
    for uid in user_ids:
        async_to_sync(channel_layer.group_send)(
            f"user_{uid}",
            {"type": "notification", "payload": payload},
        )


def compute_user_points(user) -> int:
    """
    Return the sum of reward_points for approved sticker unlocks for a user.
    Works whether StickerUnlock model exists or only UserSticker is present.
    """
    try:
        sticker_unlock_model = apps.get_model("achievements", "StickerUnlock")
    except LookupError:
        sticker_unlock_model = None

    if sticker_unlock_model is not None:
        total = (
            sticker_unlock_model.objects.filter(user=user, status="approved")
            .aggregate(total=Sum("sticker__reward_points"))
            .get("total")
        )
    else:
        total = (
            UserSticker.objects.filter(user=user, status=UserSticker.STATUS_APPROVED)
            .aggregate(total=Sum("sticker__reward_points"))
            .get("total")
        )
    return total or 0
