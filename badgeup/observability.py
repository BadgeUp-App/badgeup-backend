import logging
import os

logger = logging.getLogger(__name__)


def init_sentry():
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
    except ImportError:
        logger.warning("SENTRY_DSN configurado pero sentry-sdk no esta instalado")
        return False

    def _rate(name, default):
        try:
            return float(os.getenv(name, default))
        except (TypeError, ValueError):
            return float(default)

    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration()],
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        release=os.getenv("SENTRY_RELEASE") or None,
        traces_sample_rate=_rate("SENTRY_TRACES_SAMPLE_RATE", "0.0"),
        send_default_pii=False,
    )
    return True
