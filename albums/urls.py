from django.urls import path

from .views import AlbumDetailView, AlbumListCreateView, StickerDetailView, MatchAlbumPhotoView, StickerMessageView

urlpatterns = [
    path("", AlbumListCreateView.as_view(), name="album-list-create"),
    path("<int:pk>/", AlbumDetailView.as_view(), name="album-detail"),
    path("<int:pk>/match-photo/", MatchAlbumPhotoView.as_view(), name="album-match-photo"),
    path("stickers/<int:pk>/", StickerDetailView.as_view(), name="sticker-detail"),
    path("stickers/<int:pk>/message/", StickerMessageView.as_view(), name="sticker-message"),
]
