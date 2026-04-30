import logging
from typing import Optional

from firebase_admin import messaging

from .firebase_backend import ensure_initialized

logger = logging.getLogger(__name__)


def send_push(
    user,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> Optional[str]:
    """Send an FCM push to a single user. Returns message id or None."""
    token = (user.fcm_token or "").strip()
    if not token:
        return None

    ok, err = ensure_initialized()
    if not ok:
        logger.info("Skipping push: firebase not initialized (%s)", err)
        return None

    payload = {str(k): str(v) for k, v in (data or {}).items()}
    message = messaging.Message(
        token=token,
        notification=messaging.Notification(title=title, body=body),
        data=payload,
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default", badge=1)
            )
        ),
    )

    try:
        response = messaging.send(message)
        return response
    except messaging.UnregisteredError:
        user.fcm_token = ""
        user.fcm_platform = ""
        user.save(update_fields=["fcm_token", "fcm_platform"])
        logger.info("Cleared stale FCM token for user=%s", user.pk)
        return None
    except Exception as exc:
        logger.warning("FCM send failed for user=%s: %s", user.pk, exc)
        return None
