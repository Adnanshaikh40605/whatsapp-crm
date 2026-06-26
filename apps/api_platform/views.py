import hashlib

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.exceptions import APIResponse
from apps.core.permissions import IsOrganizationMember, IsOwnerOrAdmin
from apps.api_platform.models import APIKey, WebhookEndpoint
from apps.api_platform.serializers import (
    APIKeyCreateSerializer,
    APIKeySerializer,
    WebhookEndpointSerializer,
)


class APIKeyViewSet(viewsets.ModelViewSet):
    serializer_class = APIKeySerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        return APIKey.objects.all()

    def create(self, request, *args, **kwargs):
        ser = APIKeyCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        raw_key = APIKey.generate_key()
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        api_key = APIKey.objects.create(
            organization=request.organization,
            name=ser.validated_data["name"],
            key_prefix=raw_key[:8],
            key_hash=key_hash,
            scopes=ser.validated_data.get("scopes", ["read", "write"]),
            created_by=request.user,
        )
        return APIResponse.success(
            {"key": APIKeySerializer(api_key).data, "secret": raw_key},
            message="API key created. Copy the secret now — it won't be shown again.",
        )


class WebhookEndpointViewSet(viewsets.ModelViewSet):
    serializer_class = WebhookEndpointSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        return WebhookEndpoint.objects.all()

    def perform_create(self, serializer):
        import secrets
        serializer.save(
            organization=self.request.organization,
            secret=secrets.token_urlsafe(32),
        )
