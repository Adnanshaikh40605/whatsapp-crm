from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.api_platform.models import APIKey, WebhookEndpoint

EMBED_DEFAULT_SCOPES = ("embed", "inbox", "read", "write", "customers")

EXPIRY_CHOICES = {
    "never": None,
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "1y": timedelta(days=365),
}


class APIKeySerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = APIKey
        fields = (
            "id",
            "name",
            "key_prefix",
            "scopes",
            "is_active",
            "last_used_at",
            "last_used_ip",
            "expires_at",
            "created_at",
            "created_by_name",
            "organization_name",
        )
        read_only_fields = fields

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return "—"
        name = f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return name or obj.created_by.username or obj.created_by.email or "—"


class APIKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    scopes = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    expiry = serializers.ChoiceField(
        choices=[("never", "Never"), ("30d", "30 Days"), ("90d", "90 Days"), ("1y", "1 Year")],
        required=False,
        default="never",
    )

    def validate_scopes(self, value):
        return value or list(EMBED_DEFAULT_SCOPES)


def resolve_expires_at(expiry: str):
    delta = EXPIRY_CHOICES.get(expiry or "never")
    if not delta:
        return None
    return timezone.now() + delta


class APIKeyUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ("name", "is_active")


class WebhookEndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEndpoint
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at", "failure_count", "last_triggered_at")
