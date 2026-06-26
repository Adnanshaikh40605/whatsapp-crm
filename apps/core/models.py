import threading
import uuid

from django.db import models
from django.utils import timezone

_thread_locals = threading.local()


def set_current_organization(organization):
    _thread_locals.organization = organization


def get_current_organization():
    return getattr(_thread_locals, "organization", None)


def set_audit_context(user=None, ip_address=None, user_agent=None):
    _thread_locals.audit_user = user
    _thread_locals.audit_ip = ip_address
    _thread_locals.audit_user_agent = user_agent


def get_audit_context():
    return {
        "user": getattr(_thread_locals, "audit_user", None),
        "ip_address": getattr(_thread_locals, "audit_ip", None),
        "user_agent": getattr(_thread_locals, "audit_user_agent", None),
    }


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TenantQuerySet(models.QuerySet):
    def for_organization(self, organization):
        return self.filter(organization=organization)


class TenantManager(models.Manager):
    def get_queryset(self):
        qs = TenantQuerySet(self.model, using=self._db)
        organization = get_current_organization()
        if organization is not None:
            return qs.filter(organization=organization)
        return qs

    def for_organization(self, organization):
        return self.get_queryset().for_organization(organization)


class TenantModel(UUIDModel, TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        db_index=True,
    )

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True


class AuditLog(UUIDModel):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"
        LOGIN = "login", "Login"
        EXPORT = "export", "Export"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["resource_type", "resource_id"]),
        ]

    def __str__(self):
        return f"{self.action} {self.resource_type} {self.resource_id}"
