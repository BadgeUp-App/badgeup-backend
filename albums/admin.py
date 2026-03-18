from django.contrib import admin

from .models import Album, Sticker


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ("title", "theme", "is_premium", "price", "created_at")
    search_fields = ("title", "theme")
    list_filter = ("is_premium",)


@admin.register(Sticker)
class StickerAdmin(admin.ModelAdmin):
    list_display = ("name", "album", "reward_points", "order", "coordinates")
    list_filter = ("album",)
    search_fields = ("name", "album__title")

    @staticmethod
    def coordinates(obj):
        return f"{obj.location_lat}, {obj.location_lng}"
