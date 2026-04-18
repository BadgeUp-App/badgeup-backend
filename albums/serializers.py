from rest_framework import serializers

from achievements.models import CapturePhoto, UserSticker

from .models import Album, ScanLog, Sticker


class StickerSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(source="image_reference", required=False, allow_null=True)
    is_unlocked = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    unlocked_photo_url = serializers.SerializerMethodField()
    capture_photos = serializers.SerializerMethodField()
    user_message = serializers.SerializerMethodField()
    fun_fact = serializers.SerializerMethodField()
    unlocked_at = serializers.SerializerMethodField()
    location_label = serializers.SerializerMethodField()
    location_lat = serializers.SerializerMethodField()
    location_lng = serializers.SerializerMethodField()
    album_title = serializers.CharField(source="album.title", read_only=True)
    album_id = serializers.IntegerField(source="album.id", read_only=True)

    class Meta:
        model = Sticker
        fields = (
            "id",
            "album",
            "name",
            "description",
            "location_lat",
            "location_lng",
            "image_reference",
            "image",
            "reward_points",
            "order",
            "rarity",
            "is_unlocked",
            "status",
            "unlocked_photo_url",
            "capture_photos",
            "user_message",
            "fun_fact",
            "unlocked_at",
            "location_label",
            "location_lat",
            "location_lng",
            "album_title",
            "album_id",
        )
        read_only_fields = ("album",)

    def get_is_unlocked(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        return obj.user_stickers.filter(
            user=request.user,
            status=UserSticker.STATUS_APPROVED,
        ).exists()

    def get_status(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        capture = obj.user_stickers.filter(user=request.user).first()
        return capture.status if capture else None

    def _get_user_sticker(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        return obj.user_stickers.filter(user=user).first()

    def get_unlocked_photo_url(self, obj):
        us = self._get_user_sticker(obj)
        if us and us.unlocked_photo:
            request = self.context.get("request")
            url = us.unlocked_photo.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_capture_photos(self, obj):
        us = self._get_user_sticker(obj)
        if not us:
            return []
        request = self.context.get("request")
        photos = us.capture_photos.all().order_by("-captured_at")
        result = []
        for cp in photos:
            url = cp.photo.url if cp.photo else None
            if url and request:
                url = request.build_absolute_uri(url)
            result.append({
                "id": cp.id,
                "url": url,
                "captured_at": cp.captured_at.isoformat() if cp.captured_at else None,
            })
        return result

    def get_user_message(self, obj):
        us = self._get_user_sticker(obj)
        return us.user_message if us and us.user_message else None

    def get_fun_fact(self, obj):
        us = self._get_user_sticker(obj)
        return us.fun_fact if us and us.fun_fact else None

    def get_unlocked_at(self, obj):
        us = self._get_user_sticker(obj)
        return us.unlocked_at.isoformat() if us and us.unlocked_at else None

    def get_location_label(self, obj):
        us = self._get_user_sticker(obj)
        return us.location_label or None if us else None

    def get_location_lat(self, obj):
        us = self._get_user_sticker(obj)
        if us and us.location_lat is not None:
            return float(us.location_lat)
        return float(obj.location_lat) if obj.location_lat is not None else None

    def get_location_lng(self, obj):
        us = self._get_user_sticker(obj)
        if us and us.location_lng is not None:
            return float(us.location_lng)
        return float(obj.location_lng) if obj.location_lng is not None else None


class StickerLocationSerializer(serializers.ModelSerializer):
    sticker_id = serializers.IntegerField(source="sticker.id", read_only=True)
    sticker_name = serializers.CharField(source="sticker.name", read_only=True)
    album_title = serializers.CharField(source="sticker.album.title", read_only=True)
    rarity = serializers.CharField(source="sticker.rarity", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = UserSticker
        fields = (
            "id",
            "sticker_id",
            "sticker_name",
            "album_title",
            "rarity",
            "username",
            "unlocked_at",
            "location_lat",
            "location_lng",
            "location_label",
        )


class AlbumSerializer(serializers.ModelSerializer):
    stickers_count = serializers.IntegerField(source="stickers.count", read_only=True)
    unlocked_count = serializers.SerializerMethodField()

    class Meta:
        model = Album
        fields = (
            "id",
            "title",
            "description",
            "theme",
            "cover_image",
            "tags",
            "custom_prompt",
            "is_premium",
            "price",
            "stickers_count",
            "unlocked_count",
        )

    def get_unlocked_count(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0
        return UserSticker.objects.filter(
            user=request.user,
            sticker__album=obj,
            status=UserSticker.STATUS_APPROVED,
        ).count()


class AlbumDetailSerializer(AlbumSerializer):
    stickers = StickerSerializer(many=True, read_only=True)

    class Meta(AlbumSerializer.Meta):
        fields = AlbumSerializer.Meta.fields + ("stickers",)


class AlbumCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Album
        fields = (
            "id",
            "title",
            "description",
            "theme",
            "tags",
            "custom_prompt",
            "cover_image",
            "is_premium",
            "price",
        )
        read_only_fields = ("id",)


class StickerCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sticker
        fields = (
            "album",
            "name",
            "description",
            "location_lat",
            "location_lng",
            "image_reference",
            "reference_photo",
            "reward_points",
            "order",
            "rarity",
        )


class ScanLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True, default="")
    sticker_name = serializers.CharField(source="matched_sticker.name", read_only=True, default=None)
    album_title = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = ScanLog
        fields = (
            "id", "username", "photo", "photo_url", "ai_response",
            "detected_items", "matched_sticker", "sticker_name",
            "album_title", "matched", "confidence", "created_at",
        )

    def get_album_title(self, obj):
        if obj.matched_sticker and obj.matched_sticker.album:
            return obj.matched_sticker.album.title
        return None

    def get_photo_url(self, obj):
        if obj.photo:
            try:
                return obj.photo.url
            except Exception:
                return None
        return None
