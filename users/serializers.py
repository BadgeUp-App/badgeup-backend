from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from achievements.models import UserSticker
from achievements.utils import compute_user_points

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    computed_points = serializers.SerializerMethodField()
    stickers_captured = serializers.SerializerMethodField()
    rank = serializers.SerializerMethodField()
    reset_avatar = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "avatar",
            "bio",
            "points",
            "computed_points",
            "stickers_captured",
            "rank",
            "date_joined",
            "is_staff",
            "reset_avatar",
        )
        read_only_fields = ("id", "points", "computed_points", "stickers_captured", "rank", "date_joined")

    def update(self, instance, validated_data):
        request = self.context.get("request")
        if not request or not request.user.is_staff:
            validated_data.pop("is_staff", None)
        reset_avatar = validated_data.pop("reset_avatar", False)
        if reset_avatar:
            instance.avatar = None
        return super().update(instance, validated_data)

    def get_computed_points(self, obj):
        return compute_user_points(obj)

    def get_stickers_captured(self, obj):
        return UserSticker.objects.filter(
            user=obj, status=UserSticker.STATUS_APPROVED,
        ).count()

    def get_rank(self, obj):
        if obj.is_staff:
            return 0
        from django.db.models import Q, Sum
        from django.db.models.functions import Coalesce
        my_points = compute_user_points(obj)
        count_above = (
            User.objects.filter(is_staff=False)
            .exclude(id=obj.id)
            .annotate(
                total=Coalesce(
                    Sum(
                        "user_stickers__sticker__reward_points",
                        filter=Q(user_stickers__status=UserSticker.STATUS_APPROVED),
                    ),
                    0,
                )
            )
            .filter(total__gt=my_points)
            .count()
        )
        return count_above + 1


class UserCaptureSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sticker_id = serializers.IntegerField(source="sticker.id")
    sticker_name = serializers.CharField(source="sticker.name")
    album_title = serializers.CharField(source="sticker.album.title")
    unlocked_at = serializers.DateTimeField()
    reward_points = serializers.IntegerField(source="sticker.reward_points")


class PublicUserProfileSerializer(UserSerializer):
    stickers_captured = serializers.IntegerField(read_only=True)
    last_captures = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + (
            "stickers_captured",
            "last_captures",
        )

    def get_last_captures(self, obj):
        qs = (
            obj.user_stickers.filter(status=UserSticker.STATUS_APPROVED)
            .select_related("sticker__album")
            .order_by("-unlocked_at")[:5]
        )
        return UserCaptureSerializer(qs, many=True).data


class AdminUserManageSerializer(UserSerializer):
    reset_avatar = serializers.BooleanField(write_only=True, required=False)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ("reset_avatar",)
        read_only_fields = ("id", "date_joined", "computed_points", "points")

    def update(self, instance, validated_data):
        reset_avatar = validated_data.pop("reset_avatar", False)
        if reset_avatar:
            instance.avatar = None
        return super().update(instance, validated_data)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    password_confirm = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
        )

    def validate_email(self, value: str) -> str:
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate(self, attrs):
        password = attrs.get("password")
        password_confirm = attrs.pop("password_confirm", None)
        if password != password_confirm:
            raise serializers.ValidationError({"password": "Passwords do not match"})
        validate_password(password)
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user
