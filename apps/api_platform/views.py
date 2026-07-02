import hashlib

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.api_platform.models import APIKey, WebhookEndpoint
from apps.api_platform.serializers import (
    APIKeyCreateSerializer,
    APIKeySerializer,
    APIKeyUpdateSerializer,
    EMBED_DEFAULT_SCOPES,
    WebhookEndpointSerializer,
    resolve_expires_at,
)
from apps.core.exceptions import APIResponse
from apps.core.permissions import IsOwnerOrAdmin


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class APIKeyViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return APIKey.objects.select_related("created_by", "organization").all()

    def get_serializer_class(self):
        if self.action == "create":
            return APIKeyCreateSerializer
        if self.action in {"partial_update", "update"}:
            return APIKeyUpdateSerializer
        return APIKeySerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = APIKeySerializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return APIResponse.success(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return APIResponse.success(APIKeySerializer(instance).data)

    def create(self, request, *args, **kwargs):
        ser = APIKeyCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        raw_key = APIKey.generate_key()
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        expires_at = resolve_expires_at(ser.validated_data.get("expiry", "never"))
        api_key = APIKey.objects.create(
            organization=request.organization,
            name=ser.validated_data["name"],
            key_prefix=raw_key[:12],
            key_hash=key_hash,
            scopes=ser.validated_data.get("scopes") or list(EMBED_DEFAULT_SCOPES),
            expires_at=expires_at,
            created_by=request.user,
        )
        return APIResponse.success(
            {"key": APIKeySerializer(api_key).data, "secret": raw_key},
            message="API key created. Copy the secret now — it won't be shown again.",
            status_code=201,
        )

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        ser = APIKeyUpdateSerializer(instance, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return APIResponse.success(
            APIKeySerializer(instance).data,
            message="API key updated.",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        name = instance.name
        instance.delete()
        return APIResponse.success(message=f'API key "{name}" deleted.')

    @action(detail=True, methods=["post"])
    def regenerate(self, request, pk=None):
        instance = self.get_object()
        raw_key = APIKey.generate_key()
        instance.key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        instance.key_prefix = raw_key[:12]
        instance.last_used_at = None
        instance.last_used_ip = None
        instance.is_active = True
        instance.save(
            update_fields=["key_hash", "key_prefix", "last_used_at", "last_used_ip", "is_active", "updated_at"]
        )
        return APIResponse.success(
            {"key": APIKeySerializer(instance).data, "secret": raw_key},
            message="API key regenerated. Copy the new secret now — it won't be shown again.",
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
