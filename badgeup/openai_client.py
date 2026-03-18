from functools import lru_cache

from django.conf import settings

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - dependency guarded by requirements
    OpenAI = None  # type: ignore


@lru_cache(maxsize=1)
def get_openai_client():
    """
    Return a shared OpenAI client configured with the API key from settings.
    Raises RuntimeError if the SDK is missing or API key is not set.
    """
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    if OpenAI is None:
        raise RuntimeError("openai package is not installed")
    return OpenAI(api_key=settings.OPENAI_API_KEY)
