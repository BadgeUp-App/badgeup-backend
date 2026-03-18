from django.conf import settings
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from achievements.models import UserSticker
from achievements.services import analyze_car_photo
from achievements.utils import get_friend_ids, send_notification
from .models import Album, Sticker
from .permissions import IsAdminOrReadOnly
from .serializers import (
    AlbumCreateSerializer,
    AlbumDetailSerializer,
    AlbumSerializer,
    StickerCreateSerializer,
    StickerLocationSerializer,
    StickerSerializer,
)


class AlbumListCreateView(generics.ListCreateAPIView):
    queryset = Album.objects.prefetch_related("stickers").all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AlbumCreateSerializer
        return AlbumSerializer


class AlbumDetailView(generics.RetrieveUpdateAPIView):
    queryset = Album.objects.prefetch_related("stickers").all()
    permission_classes = [IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return AlbumCreateSerializer
        return AlbumDetailSerializer


class StickerDetailView(generics.RetrieveUpdateAPIView):
    queryset = Sticker.objects.select_related("album")
    permission_classes = [IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return StickerCreateSerializer
        return StickerSerializer


class StickerListCreateView(generics.ListCreateAPIView):
    queryset = Sticker.objects.select_related("album")
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        album_id = self.request.query_params.get("album")
        if album_id:
            qs = qs.filter(album_id=album_id)
        return qs

    def get_serializer_class(self):
        if self.request.method == "POST":
            return StickerCreateSerializer
        return StickerSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        return ctx

    def perform_create(self, serializer):
        sticker = serializer.save()
        send_notification(
            [],
            {
                "title": "Nuevo sticker",
                "message": f"Se agregó el sticker {sticker.name}",
                "category": "sticker_new",
            },
            broadcast=True,
        )


class StickerLocationListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StickerLocationSerializer

    def get_queryset(self):
        return (
            UserSticker.objects.filter(
                location_lat__isnull=False,
                location_lng__isnull=False,
            )
            .select_related("sticker__album", "user")
            .order_by("-unlocked_at")
        )


class MatchAlbumPhotoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not settings.USE_OPENAI_STICKER_VALIDATION or not settings.OPENAI_API_KEY:
            return Response(
                {"unlocked": False, "message": "Validación por IA deshabilitada."},
                status=status.HTTP_200_OK,
            )

        album = get_object_or_404(Album.objects.prefetch_related("stickers"), pk=pk)
        stickers = list(album.stickers.all())

        photo = request.FILES.get("photo")
        if not photo:
            return Response(
                {"detail": "Debes enviar una foto en el campo 'photo'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = analyze_car_photo(photo, stickers)
        if not result:
            return Response(
                {
                    "unlocked": False,
                    "message": "No pudimos analizar la foto. Intenta de nuevo.",
                },
                status=status.HTTP_200_OK,
            )

        recognized = bool(result.get("recognized"))
        confidence = float(result.get("confidence") or 0)
        sticker_id = result.get("sticker_id")
        fun_fact = result.get("fun_fact") or ""
        reason = result.get("reason") or ""
        car_info = {
            "make": result.get("make"),
            "model": result.get("model"),
            "generation": result.get("generation"),
            "year_range": result.get("year_range"),
        }
        lat = request.data.get("lat")
        lng = request.data.get("lng")

        if not recognized:
            return Response(
                {
                    "unlocked": False,
                    "message": fun_fact or "Uy, esta foto no parece un coche reconocible.",
                    "car": car_info,
                    "reason": reason,
                    "fun_fact": fun_fact,
                },
                status=status.HTTP_200_OK,
            )

        if not sticker_id:
            msg = (
                "Detectamos un coche "
                f"{car_info.get('make') or ''} {car_info.get('model') or ''}".strip()
                + ", pero aún no existe un sticker para este modelo en este álbum."
            )
            return Response(
                {
                    "unlocked": False,
                    "message": msg,
                    "car": car_info,
                    "reason": reason,
                    "fun_fact": fun_fact,
                },
                status=status.HTTP_200_OK,
            )

        try:
            sticker = album.stickers.get(pk=sticker_id)
        except Sticker.DoesNotExist:
            return Response(
                {
                    "unlocked": False,
                    "message": "El sticker sugerido por la IA no pertenece a este álbum.",
                    "car": car_info,
                    "reason": reason,
                    "fun_fact": fun_fact,
                },
                status=status.HTTP_200_OK,
            )

        if confidence < 0.6:
            return Response(
                {
                    "unlocked": False,
                    "message": "La IA no está lo suficientemente segura para desbloquear este sticker.",
                    "car": car_info,
                    "reason": reason,
                    "fun_fact": fun_fact,
                },
                status=status.HTTP_200_OK,
            )

        user_sticker, created = UserSticker.objects.get_or_create(
            user=request.user,
            sticker=sticker,
        )

        if user_sticker.validated and user_sticker.status == UserSticker.STATUS_APPROVED:
            serializer = StickerSerializer(
                sticker, context={"request": request, "user": request.user}
            )
            return Response(
                {
                    "unlocked": True,
                    "already_unlocked": True,
                    "sticker": serializer.data,
                    "match_score": confidence,
                    "car": car_info,
                    "reason": "Ya habías desbloqueado este sticker.",
                    "fun_fact": fun_fact,
                },
                status=status.HTTP_200_OK,
            )

        try:
            photo.seek(0)
        except Exception:
            pass

        user_sticker.unlocked_photo = photo
        user_sticker.unlocked_at = user_sticker.unlocked_at or timezone.now()
        user_sticker.validation_score = confidence
        user_sticker.validation_notes = reason
        user_sticker.detected_make = car_info.get("make") or ""
        user_sticker.detected_model = car_info.get("model") or ""
        user_sticker.detected_generation = car_info.get("generation") or ""
        user_sticker.detected_year_range = car_info.get("year_range") or ""
        user_sticker.fun_fact = fun_fact or user_sticker.fun_fact
        if lat not in (None, ""):
            try:
                user_sticker.location_lat = float(lat)
            except (TypeError, ValueError):
                pass
        if lng not in (None, ""):
            try:
                user_sticker.location_lng = float(lng)
            except (TypeError, ValueError):
                pass

        user_sticker.status = UserSticker.STATUS_APPROVED
        user_sticker.validated = True
        user_sticker.save(
            update_fields=[
                "unlocked_photo",
                "unlocked_at",
                "validation_score",
                "validation_notes",
                "detected_make",
                "detected_model",
                "detected_generation",
                "detected_year_range",
                "fun_fact",
                "location_lat",
                "location_lng",
                "status",
                "validated",
                "updated_at",
            ]
        )

        send_notification(
            get_friend_ids(request.user.id),
            {
                "title": "Captura de amigo",
                "message": f"{request.user.username} desbloqueó {sticker.name}",
                "category": "sticker_unlock",
            },
        )

        serializer = StickerSerializer(
            sticker, context={"request": request, "user": request.user}
        )
        return Response(
            {
                "unlocked": True,
                "already_unlocked": False,
                "sticker": serializer.data,
                "match_score": confidence,
                "car": car_info,
                "reason": reason,
                "fun_fact": fun_fact,
            },
            status=status.HTTP_200_OK,
        )


class StickerMessageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        message = (request.data.get("message") or "").strip()
        sticker = get_object_or_404(Sticker, pk=pk)
        user_sticker, _ = UserSticker.objects.get_or_create(
            user=request.user,
            sticker=sticker,
        )
        user_sticker.user_message = message
        user_sticker.save(update_fields=["user_message", "updated_at"])

        serializer = StickerSerializer(
            sticker,
            context={"request": request, "user": request.user},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
