import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "badgeup.settings")

app = Celery("badgeup")
app.config_from_object("django.conf:settings", namespace="CELERY")


def _installed_apps():
    from django.conf import settings
    return list(settings.INSTALLED_APPS)


app.autodiscover_tasks(_installed_apps)
