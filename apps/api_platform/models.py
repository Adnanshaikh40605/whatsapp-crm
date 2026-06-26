import secrets

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class APIKey(TenantModel):
    name = models.CharField(max_length=100)
    key_prefix = models.CharField(max_length=8)
    key_hash = models.CharField(max_length=128)
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="api_keys"
    )

    class Meta:
        indexes = [models.Index(fields=["organization", "is_active"])]

    @staticmethod
    def generate_key():
        return f"wf_{secrets.token_urlsafe(32)}"

    def __str__(self):
        return f"{self.name} ({self.key_prefix}...)"


class WebhookEndpoint(TenantModel):
    url = models.URLField()
    events = models.JSONField(default=list)
    secret = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    failure_count = models.PositiveIntegerField(default=0)
    last_triggered_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.url
