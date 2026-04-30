from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user with optional profile details and gamification points.
    """

    email = models.EmailField(unique=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    bio = models.TextField(blank=True)
    points = models.PositiveIntegerField(default=0)

    reset_code = models.CharField(max_length=6, blank=True, null=True)
    reset_code_expires = models.DateTimeField(blank=True, null=True)

    fcm_token = models.CharField(max_length=512, blank=True, default="")
    fcm_platform = models.CharField(max_length=16, blank=True, default="")
    fcm_updated_at = models.DateTimeField(blank=True, null=True)

    REQUIRED_FIELDS = ["email"]

    def __str__(self) -> str:
        return self.username
