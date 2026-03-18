from django.contrib import admin

from .models import UserSticker


@admin.register(UserSticker)
class UserStickerAdmin(admin.ModelAdmin):
    list_display = ("user", "sticker", "status", "validated", "validated_at", "updated_at")
    search_fields = ("user__username", "sticker__name")
    list_filter = ("status", "validated")
