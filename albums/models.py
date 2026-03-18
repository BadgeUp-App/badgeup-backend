import os
from uuid import uuid4

from django.db import models
from django.utils.text import slugify


def _generate_filename(prefix: str, base: str, filename: str) -> str:
    """Return a deterministic, short, slugified filename."""
    name, ext = os.path.splitext(filename)
    ext = ext or ""
    slug = slugify(base) or "file"
    return f"{prefix}{slug[:50]}-{uuid4().hex[:8]}{ext}"


def album_cover_upload(instance: "Album", filename: str) -> str:
    return _generate_filename("albums/covers/", instance.title, filename)


def sticker_image_upload(instance: "Sticker", filename: str) -> str:
    album_title = getattr(instance.album, "title", "") or "album"
    base = f"{album_title}-{instance.name}"
    return _generate_filename("stickers/reference/", base, filename)


class Album(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    theme = models.CharField(max_length=255, blank=True)
    cover_image = models.ImageField(
        upload_to=album_cover_upload,
        max_length=255,
        blank=True,
        null=True,
    )
    is_premium = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class Sticker(models.Model):
    album = models.ForeignKey(
        Album,
        related_name="stickers",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    location_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    image_reference = models.ImageField(
        upload_to=sticker_image_upload,
        max_length=255,
        blank=True,
        null=True,
    )
    reward_points = models.PositiveIntegerField(default=0)
    order = models.PositiveIntegerField(default=0)
    rarity = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]
        unique_together = ("album", "name")

    def __str__(self) -> str:
        return f"{self.album.title} - {self.name}"
