import logging
import os
import platform

import requests

_ENDPOINT = os.getenv(
    "AROA_ERRORS_ENDPOINT", "https://internal.aroagroup.com/api/errors/ingest"
)


def _ingest_key():
    return os.getenv("AROA_ERRORS_KEY", "").strip()


def report_error(exception_type, message="", stack_trace=None, level="error", extra=None):
    key = _ingest_key()
    if not key:
        return False

    payload = {
        "exception_type": exception_type or "Error",
        "message": message or "",
        "stack_trace": stack_trace,
        "level": level,
        "release": os.getenv("AROA_ERRORS_RELEASE") or None,
        "environment": os.getenv("AROA_ERRORS_ENVIRONMENT", "production"),
        "platform_meta": {
            "runtime": "django",
            "python": platform.python_version(),
        },
    }
    if extra:
        payload["extra"] = extra

    try:
        requests.post(
            _ENDPOINT,
            json=payload,
            headers={"x-aroa-ingest-key": key},
            timeout=3,
        )
        return True
    except Exception:
        return False


class AroaErrorsHandler(logging.Handler):
    def emit(self, record):
        try:
            exc_type = "Error"
            stack = None
            if record.exc_info:
                exc = record.exc_info[1]
                if exc is not None:
                    exc_type = type(exc).__name__
                stack = logging.Formatter().formatException(record.exc_info)
            report_error(
                exception_type=exc_type,
                message=record.getMessage(),
                stack_trace=stack,
                level="error",
                extra={"logger": record.name},
            )
        except Exception:
            pass
