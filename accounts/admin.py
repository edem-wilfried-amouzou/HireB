from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("username",)
    list_display = ("username", "email", "name", "is_staff", "date_joined")
    search_fields = ("username", "email", "name")
    readonly_fields = ("username",)
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Profil", {"fields": ("name", "email", "phone", "email_notifications")}),
        ("Droits", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "email", "name", "password1", "password2")}),
    )

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields if obj else ()
