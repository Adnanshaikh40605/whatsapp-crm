from django.contrib import admin

from apps.core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "resource_type", "resource_id", "user", "organization", "created_at")
    list_filter = ("action", "resource_type", "organization")
    search_fields = ("resource_id", "user__email")
    readonly_fields = ("created_at",)
