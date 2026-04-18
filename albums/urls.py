from django.urls import path

from .views import (
    AlbumDetailView,
    AlbumListCreateView,
    MatchAlbumPhotoView,
    ScanLogListView,
    StickerDetailView,
    StickerMessageView,
    StickerReferenceUploadView,
)

urlpatterns = [
    path("", AlbumListCreateView.as_view(), name="album-list-create"),
    path("<int:pk>/", AlbumDetailView.as_view(), name="album-detail"),
    path("<int:pk>/match-photo/", MatchAlbumPhotoView.as_view(), name="album-match-photo"),
    path("stickers/<int:pk>/", StickerDetailView.as_view(), name="sticker-detail"),
    path("stickers/<int:pk>/message/", StickerMessageView.as_view(), name="sticker-message"),
    path("stickers/<int:pk>/references/", StickerReferenceUploadView.as_view(), name="sticker-references"),
    path("scan-logs/", ScanLogListView.as_view(), name="scan-log-list"),
]
