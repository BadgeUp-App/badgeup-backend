import logging

from celery import shared_task
from django.db.models import F
from django.utils import timezone

from .models import UserSticker
from .services import analyze_user_sticker

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def validate_user_sticker(self, user_sticker_id: int):
    try:
        user_sticker = UserSticker.objects.select_related("sticker", "user").get(
            pk=user_sticker_id
        )
    except UserSticker.DoesNotExist:
        logger.warning("UserSticker %s no longer exists.", user_sticker_id)
        return

    if user_sticker.validated:
        logger.info("UserSticker %s already validated. Skipping.", user_sticker_id)
        return

    user_sticker.status = UserSticker.STATUS_VALIDATING
    user_sticker.save(update_fields=["status", "updated_at"])

    result = analyze_user_sticker(user_sticker)

    if result.get("error"):
        user_sticker.status = UserSticker.STATUS_PENDING
        user_sticker.validated = False
        user_sticker.validation_notes = result
        user_sticker.validation_score = None
        user_sticker.save(
            update_fields=["status", "validated", "validation_notes", "validation_score", "updated_at"]
        )
        logger.warning("OpenAI validation error for UserSticker %s: %s", user_sticker_id, result.get("error"))
        return

    approved = result.get("approved", False)
    status_value = UserSticker.STATUS_APPROVED if approved else UserSticker.STATUS_REJECTED

    user_sticker.status = status_value
    user_sticker.validated = approved
    user_sticker.validated_at = timezone.now() if approved else None
    user_sticker.validation_notes = result
    user_sticker.validation_score = result.get("match_score")
    user_sticker.save(
        update_fields=[
            "status",
            "validated",
            "validated_at",
            "validation_notes",
            "validation_score",
            "updated_at",
        ]
    )

    if approved:
        User = user_sticker.user.__class__
        User.objects.filter(id=user_sticker.user_id).update(
            points=F("points") + user_sticker.sticker.reward_points
        )
        logger.info(
            "UserSticker %s approved; added %s points to user %s (total will be refreshed)",
            user_sticker_id,
            user_sticker.sticker.reward_points,
            user_sticker.user_id,
        )
    else:
        logger.info("UserSticker %s rejected: %s", user_sticker_id, result)
