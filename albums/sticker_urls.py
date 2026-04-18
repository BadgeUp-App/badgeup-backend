from django.urls import path

from achievements.views import StickerUnlockView

from .views import StickerDetailView, StickerListCreateView, StickerLocationListView, StickerMessageView, StickerReferenceUploadView

urlpatterns = [
    path("", StickerListCreateView.as_view(), name="sticker-list-create"),
    path("locations/", StickerLocationListView.as_view(), name="sticker-locations"),
    path("<int:pk>/", StickerDetailView.as_view(), name="sticker-detail-global"),
    path("<int:pk>/unlock/", StickerUnlockView.as_view(), name="sticker-unlock-global"),
    path("<int:pk>/message/", StickerMessageView.as_view(), name="sticker-message-global"),
    path("<int:pk>/references/", StickerReferenceUploadView.as_view(), name="sticker-references-global"),
]
