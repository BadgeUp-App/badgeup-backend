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

    REQUIRED_FIELDS = ["email"]

    def __str__(self) -> str:
        return self.username
