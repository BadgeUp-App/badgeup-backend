from rest_framework import serializers

from users.models import User

from .models import ChatMessage, FriendRequest, UserSticker
from .utils import compute_user_points


class UserSummarySerializer(serializers.ModelSerializer):

    computed_points = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "avatar",
            "points",
            "computed_points",
        )

    def get_computed_points(self, user):
        return compute_user_points(user)


class MemberSerializer(serializers.ModelSerializer):
    computed_points = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "avatar",
            "points",
            "computed_points",
        )

    def get_computed_points(self, user):
        return compute_user_points(user)


class UserStickerSerializer(serializers.ModelSerializer):
    sticker = serializers.PrimaryKeyRelatedField(read_only=True)
    album = serializers.SerializerMethodField()

    class Meta:
        model = UserSticker
        fields = (
            "id",
            "sticker",
            "album",
            "photo",
            "photo_url",
            "comment",
            "status",
            "validated",
            "validated_at",
            "validation_score",
            "validation_notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "status",
            "validated",
            "validated_at",
            "validation_score",
            "validation_notes",
            "created_at",
            "updated_at",
            "album",
        )

    def get_album(self, obj):
        return obj.sticker.album_id


class StickerUnlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSticker
        fields = ("photo", "photo_url", "comment")

    def validate(self, attrs):
        photo = attrs.get("photo")
        photo_url = attrs.get("photo_url")
        if not photo and not photo_url:
            raise serializers.ValidationError("Provide at least photo or photo_url.")
        return attrs


class FriendRequestSerializer(serializers.ModelSerializer):
    from_user = UserSummarySerializer(read_only=True)
    to_user = UserSummarySerializer(read_only=True)

    class Meta:
        model = FriendRequest
        fields = (
            "id",
            "from_user",
            "to_user",
            "status",
            "created_at",
            "responded_at",
        )


class MemberWithRelationSerializer(MemberSerializer):
    relationship_status = serializers.SerializerMethodField()
    friend_request_id = serializers.SerializerMethodField()

    class Meta(MemberSerializer.Meta):
        fields = MemberSerializer.Meta.fields + ("relationship_status", "friend_request_id")

    def get_relationship_status(self, obj):
        relationship_map = self.context.get("relationship_map", {})
        rel = relationship_map.get(obj.id) or {}
        return rel.get("status", "none")

    def get_friend_request_id(self, obj):
        relationship_map = self.context.get("relationship_map", {})
        rel = relationship_map.get(obj.id) or {}
        return rel.get("request_id")


class ChatMessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.IntegerField(source="sender.id", read_only=True)
    recipient_id = serializers.IntegerField(source="recipient.id", read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = (
            "id",
            "sender_id",
            "recipient_id",
            "text",
            "file",
            "file_url",
            "created_at",
        )
        read_only_fields = ("id", "sender_id", "recipient_id", "created_at", "file_url")

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and hasattr(obj.file, "url"):
            url = obj.file.url
            if request:
                return request.build_absolute_uri(url)
            return url
        return None

    def validate(self, attrs):
        text = (attrs.get("text") or "").strip()
        file = attrs.get("file")
        if not text and not file:
            raise serializers.ValidationError("Envía texto o adjunta un archivo.")
        return attrs


class UserStickerHistorySerializer(serializers.ModelSerializer):
    sticker_id = serializers.IntegerField(source="sticker.id", read_only=True)
    sticker_name = serializers.CharField(source="sticker.name", read_only=True)
    album_title = serializers.CharField(source="sticker.album.title", read_only=True)

    class Meta:
        model = UserSticker
        fields = (
            "id",
            "sticker_id",
            "sticker_name",
            "album_title",
            "unlocked_at",
        )
