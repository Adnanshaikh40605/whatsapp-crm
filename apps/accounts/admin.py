from django.contrib import admin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active", "created_at")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("-created_at",)
