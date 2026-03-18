from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Allow authenticated users to read, but only staff can write.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return request.user and request.user.is_staff
