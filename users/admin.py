from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User
from achievements.utils import compute_user_points


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("BadgeUp Profile", {"fields": ("avatar", "bio", "points", "computed_points_display")}),
    )
    readonly_fields = ("computed_points_display",)
    list_display = ("username", "email", "first_name", "last_name", "points", "computed_points_display", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name")

    def computed_points_display(self, obj):
        return compute_user_points(obj)
    computed_points_display.short_description = "Computed Points"
