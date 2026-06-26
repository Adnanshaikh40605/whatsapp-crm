from django.contrib import admin

from apps.api_platform.models import APIKey, WebhookEndpoint


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "key_prefix", "is_active", "organization")


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ("url", "is_active", "organization")
