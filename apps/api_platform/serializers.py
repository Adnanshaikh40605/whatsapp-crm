import hashlib

from rest_framework import serializers

from apps.api_platform.models import APIKey, WebhookEndpoint


class APIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ("id", "name", "key_prefix", "scopes", "is_active", "last_used_at", "expires_at", "created_at")
        read_only_fields = ("id", "key_prefix", "created_at")


class APIKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    scopes = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class WebhookEndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEndpoint
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at", "failure_count", "last_triggered_at")
