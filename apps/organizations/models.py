import re
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Organization(models.Model):
    class ProjectType(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"
        OTHER = "other", "Other"

    class Plan(models.TextChoices):
        INTERNAL = "internal", "Internal"
        FREE = "free", "Free"
        STARTER = "starter", "Starter"
        GROWTH = "growth", "Growth"
        ENTERPRISE = "enterprise", "Enterprise"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    project_type = models.CharField(max_length=20, choices=ProjectType.choices, default=ProjectType.WHATSAPP)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_organizations",
    )
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.INTERNAL)
    industry = models.CharField(max_length=100, blank=True)
    team_size = models.CharField(max_length=50, blank=True)
    logo = models.ImageField(upload_to="org_logos/", blank=True, null=True)
    website = models.URLField(blank=True)
    org_timezone = models.CharField(max_length=50, default="UTC")
    whatsapp_phone_number_id = models.CharField(max_length=100, blank=True)
    whatsapp_business_account_id = models.CharField(max_length=100, blank=True)
    whatsapp_access_token = models.TextField(blank=True)
    whatsapp_connected = models.BooleanField(default=False)
    whatsapp_connected_at = models.DateTimeField(null=True, blank=True)
    meta_app_id = models.CharField(max_length=100, blank=True)
    onboarding_completed = models.BooleanField(default=False)
    onboarding_step = models.PositiveSmallIntegerField(default=1)
    onboarding_data = models.JSONField(default=dict, blank=True)
    ai_config = models.JSONField(default=dict, blank=True)
    branding = models.JSONField(default=dict, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    white_label_domain = models.CharField(max_length=255, blank=True)
    custom_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["project_type", "is_active"]),
            models.Index(fields=["plan", "is_active"]),
        ]

    def __str__(self):
        return self.name

    @staticmethod
    def generate_slug(name):
        base = slugify(name) or "org"
        slug = base
        counter = 1
        while Organization.objects.filter(slug=slug).exists():
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    def get_plan_limits(self):
        from django.conf import settings
        if getattr(settings, "INTERNAL_MODE", True):
            return settings.UNLIMITED_PLAN_LIMITS
        return settings.DEFAULT_PLAN_LIMITS.get(self.plan, settings.DEFAULT_PLAN_LIMITS["free"])


class OrganizationMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MANAGER = "manager", "Manager"
        AGENT = "agent", "Agent"
        ACCOUNTANT = "accountant", "Accountant"
        FINANCE = "finance", "Finance User"
        MARKETING = "marketing", "Marketing"
        VIEWER = "viewer", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.AGENT)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_invites",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("organization", "user")]
        indexes = [
            models.Index(fields=["organization", "role"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user.email} @ {self.organization.name} ({self.role})"
