from django.conf import settings
from django.db import models

from albums.models import Sticker


class UserSticker(models.Model):
    """
    Represents a sticker unlocked (or pending validation) by a user.
    """

    STATUS_PENDING = "pending"
    STATUS_VALIDATING = "validating"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_VALIDATING, "Validating"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="user_stickers",
        on_delete=models.CASCADE,
    )
    sticker = models.ForeignKey(
        Sticker,
        related_name="user_stickers",
        on_delete=models.CASCADE,
    )
    photo = models.ImageField(upload_to="user_stickers/", blank=True, null=True)
    photo_url = models.URLField(blank=True)
    comment = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    validated = models.BooleanField(default=False)
    validated_at = models.DateTimeField(blank=True, null=True)
    validation_notes = models.JSONField(blank=True, null=True)
    validation_score = models.FloatField(null=True, blank=True)
    unlocked_photo = models.ImageField(upload_to="user_stickers/", null=True, blank=True)
    unlocked_at = models.DateTimeField(null=True, blank=True)
    detected_make = models.CharField(max_length=100, blank=True)
    detected_model = models.CharField(max_length=100, blank=True)
    detected_generation = models.CharField(max_length=100, blank=True)
    detected_year_range = models.CharField(max_length=100, blank=True)
    fun_fact = models.TextField(blank=True)
    user_message = models.TextField(blank=True)
    location_label = models.CharField(max_length=255, blank=True)
    location_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "sticker")
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.user} - {self.sticker}"


class FriendRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
    ]

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="friend_requests_sent",
        on_delete=models.CASCADE,
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="friend_requests_received",
        on_delete=models.CASCADE,
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["from_user", "to_user"],
                name="unique_friend_request_pair",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.from_user} -> {self.to_user} ({self.status})"


class ChatMessage(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="messages_sent",
        on_delete=models.CASCADE,
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="messages_received",
        on_delete=models.CASCADE,
    )
    text = models.TextField(blank=True)
    file = models.FileField(upload_to="chat_files/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.sender} -> {self.recipient} ({self.created_at})"
