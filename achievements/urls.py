from django.urls import path

from .views import (
    FriendRemoveView,
    FriendRequestAcceptView,
    FriendRequestCancelView,
    FriendRequestListCreateView,
    FriendRequestRejectView,
    FriendsListView,
    MemberListView,
    StickerUnlockView,
    UserStickerHistoryView,
    ChatMessageView,
)

urlpatterns = [
    path("stickers/<int:pk>/unlock/", StickerUnlockView.as_view(), name="sticker-unlock"),
    path("captures/history/", UserStickerHistoryView.as_view(), name="user-sticker-history"),
    path("friends/", FriendsListView.as_view(), name="friends-list"),
    path("friends/members/", MemberListView.as_view(), name="friends-members"),
    path("friends/requests/", FriendRequestListCreateView.as_view(), name="friend-requests"),
    path(
        "friends/requests/<int:pk>/accept/",
        FriendRequestAcceptView.as_view(),
        name="friend-request-accept",
    ),
    path(
        "friends/requests/<int:pk>/reject/",
        FriendRequestRejectView.as_view(),
        name="friend-request-reject",
    ),
    path(
        "friends/requests/<int:pk>/cancel/",
        FriendRequestCancelView.as_view(),
        name="friend-request-cancel",
    ),
    path(
        "friends/<int:pk>/remove/",
        FriendRemoveView.as_view(),
        name="friend-remove",
    ),
    path("chat/<int:other_id>/", ChatMessageView.as_view(), name="chat-messages"),
]
