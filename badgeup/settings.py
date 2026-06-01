"""
Django settings for badgeup project.

Environment driven configuration for running locally with Docker and
deploying to production safely.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_list(key: str, default: str = "") -> list[str]:
    """Return comma-separated environment variable as list of stripped values."""
    raw = os.getenv(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "change-me-in-production")
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "")

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "True").lower() == "true"
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"



INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "channels",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "storages",
    # Local apps
    "users",
    "albums",
    "achievements",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "badgeup.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "badgeup.wsgi.application"
ASGI_APPLICATION = "badgeup.asgi.application"


DATABASE_URL = os.getenv("DATABASE_URL", "")
DATABASE_FALLBACK = os.getenv("DATABASE_FALLBACK", "true").lower() == "true"

_db_resolved = False
if DATABASE_URL:
    import dj_database_url
    _parsed = dj_database_url.parse(DATABASE_URL)
    if DATABASE_URL.startswith("sqlite"):
        DATABASES = {"default": _parsed}
        _db_resolved = True
    else:
        try:
            import psycopg2
            psycopg2.connect(
                host=_parsed["HOST"],
                port=_parsed["PORT"],
                user=_parsed["USER"],
                password=_parsed["PASSWORD"],
                dbname=_parsed["NAME"],
                connect_timeout=5,
            ).close()
            DATABASES = {"default": _parsed}
            _db_resolved = True
        except Exception:
            if DATABASE_FALLBACK:
                DATABASES = {
                    "default": {
                        "ENGINE": "django.db.backends.postgresql",
                        "NAME": os.getenv("POSTGRES_DB", "badgeup_db"),
                        "USER": os.getenv("POSTGRES_USER", "badgeup"),
                        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "badgeup"),
                        "HOST": os.getenv("POSTGRES_HOST", "db"),
                        "PORT": os.getenv("POSTGRES_PORT", "5432"),
                    }
                }
            else:
                DATABASES = {"default": _parsed}
            _db_resolved = True
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "badgeup_db"),
            "USER": os.getenv("POSTGRES_USER", "badgeup"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "badgeup"),
            "HOST": os.getenv("POSTGRES_HOST", "db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

USE_S3 = os.getenv("USE_S3", "False").lower() == "true"
if USE_S3:
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "")
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "us-east-1")
    AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL", "")
    AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN")
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_ADDRESSING_STYLE = "path"
    AWS_S3_FILE_OVERWRITE = False

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "users.User"


REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/hour",
        "user": "1000/hour",
        "login": "10/minute",
        "register": "5/hour",
        "scan": "60/hour",
        "password_reset": "5/hour",
    },
}

# Cache que usa el throttling de DRF. LocMemCache = por proceso: cada worker de
# gunicorn lleva su propio contador, asi que el limite efectivo es
# N_workers x rate. Decision consciente: Render no corre Redis y no se justifica
# todavia. Para hacerlo global a futuro: Redis, o DatabaseCache (createcachetable).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "badgeup-locmem",
    }
}


_cors_origins = env_list("CORS_ALLOWED_ORIGINS")
if _cors_origins:
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = _cors_origins
elif DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOWED_ORIGINS = []
CORS_ALLOW_CREDENTIALS = True


SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("ACCESS_TOKEN_LIFETIME_MINUTES", "60"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.getenv("REFRESH_TOKEN_LIFETIME_DAYS", "7"))
    ),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}


CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "300"))

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.getenv("REDIS_URL", "redis://redis:6379/0")],
        },
    },
}


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
USE_OPENAI_STICKER_VALIDATION = bool(OPENAI_API_KEY)

MAX_SCANS_PER_DAY_FREE = int(os.getenv("MAX_SCANS_PER_DAY_FREE", "5"))

VISION_CACHE_ENABLED = os.getenv("VISION_CACHE_ENABLED", "True").lower() == "true"
VISION_PREFILTER_ENABLED = os.getenv("VISION_PREFILTER_ENABLED", "True").lower() == "true"
VISION_PREFILTER_MODEL = os.getenv("VISION_PREFILTER_MODEL", "gpt-4o-mini")
VISION_MAIN_COST_USD = float(os.getenv("VISION_MAIN_COST_USD", "0.001"))
VISION_PREFILTER_COST_USD = float(os.getenv("VISION_PREFILTER_COST_USD", "0.0001"))
OPENAI_DAILY_COST_LIMIT_USD = float(os.getenv("OPENAI_DAILY_COST_LIMIT_USD", "20.0"))

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/api/auth/google/callback/",
)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "BadgeUp <noreply@badgeup.app>")


from badgeup.observability import init_sentry  # noqa: E402

init_sentry()
