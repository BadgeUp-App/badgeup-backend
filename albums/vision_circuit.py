import logging
from decimal import Decimal
from typing import Any, Dict

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import DailyAICost

logger = logging.getLogger(__name__)


def get_daily_limit_usd() -> Decimal:
    raw = getattr(settings, "OPENAI_DAILY_COST_LIMIT_USD", "20.0")
    try:
        return Decimal(str(raw))
    except Exception:
        return Decimal("20.0")


def get_today_state() -> Dict[str, Any]:
    today = timezone.localdate()
    row = DailyAICost.objects.filter(date=today).first()
    limit = get_daily_limit_usd()
    used = row.total_usd if row else Decimal("0")
    return {
        "date": str(today),
        "used_usd": float(used),
        "limit_usd": float(limit),
        "remaining_usd": float(max(Decimal("0"), limit - used)),
        "call_count": row.call_count if row else 0,
        "prefilter_count": row.prefilter_count if row else 0,
        "cache_hit_count": row.cache_hit_count if row else 0,
        "tripped": used >= limit,
    }


def is_tripped() -> bool:
    today = timezone.localdate()
    row = DailyAICost.objects.filter(date=today).first()
    if not row:
        return False
    return Decimal(row.total_usd) >= get_daily_limit_usd()


def record_call(cost_usd: float, kind: str = "main") -> None:
    today = timezone.localdate()
    cost = Decimal(str(cost_usd))
    try:
        with transaction.atomic():
            row, _ = DailyAICost.objects.select_for_update().get_or_create(
                date=today, defaults={"total_usd": Decimal("0")}
            )
            updates = {
                "total_usd": F("total_usd") + cost,
            }
            if kind == "main":
                updates["call_count"] = F("call_count") + 1
            elif kind == "prefilter":
                updates["prefilter_count"] = F("prefilter_count") + 1
            elif kind == "cache_hit":
                updates["cache_hit_count"] = F("cache_hit_count") + 1
            DailyAICost.objects.filter(pk=row.pk).update(**updates)
    except Exception:
        logger.exception("vision_circuit record_call failed")
