from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import ScanQuotaUsage


def get_daily_limit(user) -> Optional[int]:
    if not user or not user.is_authenticated:
        return 0
    if user.is_staff or user.is_superuser:
        return None
    if getattr(user, "is_premium", False):
        premium_until = getattr(user, "premium_until", None)
        if premium_until is None or premium_until > timezone.now():
            return None
    return int(getattr(settings, "MAX_SCANS_PER_DAY_FREE", 5))


def get_remaining(user) -> Dict[str, Any]:
    limit = get_daily_limit(user)
    if limit is None:
        return {"limit": None, "used": 0, "remaining": None, "unlimited": True}
    today = timezone.localdate()
    used = (
        ScanQuotaUsage.objects.filter(user=user, date=today)
        .values_list("count", flat=True)
        .first()
        or 0
    )
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "unlimited": False,
        "reset_at": _next_reset(),
    }


def reserve_scan(user) -> Tuple[bool, Dict[str, Any]]:
    limit = get_daily_limit(user)
    if limit is None:
        return True, {"limit": None, "remaining": None, "unlimited": True}
    today = timezone.localdate()
    with transaction.atomic():
        usage, _ = ScanQuotaUsage.objects.select_for_update().get_or_create(
            user=user, date=today, defaults={"count": 0}
        )
        if usage.count >= limit:
            return False, {
                "limit": limit,
                "used": usage.count,
                "remaining": 0,
                "unlimited": False,
                "reset_at": _next_reset(),
            }
        usage.count += 1
        usage.save(update_fields=["count", "last_at"])
        return True, {
            "limit": limit,
            "used": usage.count,
            "remaining": max(0, limit - usage.count),
            "unlimited": False,
            "reset_at": _next_reset(),
        }


def _next_reset() -> str:
    now = timezone.localtime()
    next_midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return next_midnight.isoformat()
