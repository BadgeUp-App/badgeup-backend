import io
import logging
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import transaction
from django.db.models import F
from PIL import Image, UnidentifiedImageError

from .models import VisionResultCache

logger = logging.getLogger(__name__)


def compute_dhash(image_bytes: bytes) -> Optional[str]:
    if not image_bytes:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L").resize(
            (9, 8), Image.LANCZOS
        )
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    pixels = list(img.getdata())
    bits = []
    for row in range(8):
        for col in range(8):
            idx = row * 9 + col
            bits.append("1" if pixels[idx] > pixels[idx + 1] else "0")
    return f"{int(''.join(bits), 2):016x}"


def is_enabled() -> bool:
    return bool(getattr(settings, "VISION_CACHE_ENABLED", True))


def lookup(phash: str) -> Optional[Dict[str, Any]]:
    if not phash or not is_enabled():
        return None
    try:
        with transaction.atomic():
            row = (
                VisionResultCache.objects.select_for_update()
                .filter(phash=phash)
                .first()
            )
            if not row:
                return None
            VisionResultCache.objects.filter(pk=row.pk).update(
                hit_count=F("hit_count") + 1
            )
            return row.result_json
    except Exception:
        logger.exception("vision_cache lookup failed for %s", phash)
        return None


def store(phash: str, result: Dict[str, Any]) -> None:
    if not phash or not result or not is_enabled():
        return
    try:
        VisionResultCache.objects.get_or_create(
            phash=phash, defaults={"result_json": result}
        )
    except Exception:
        logger.exception("vision_cache store failed for %s", phash)
