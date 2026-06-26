from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Contact(TenantModel):
    class Source(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        WEBSITE = "website", "Website"
        REFERRAL = "referral", "Referral"
        CAMPAIGN = "campaign", "Campaign"
        MANUAL = "manual", "Manual"
        API = "api", "API"

    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField(max_length=20, db_index=True)
    whatsapp_id = models.CharField(max_length=100, blank=True, db_index=True)
    company = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    tags = models.JSONField(default=list, blank=True)
    custom_fields = models.JSONField(default=dict, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_contacts",
    )
    is_active = models.BooleanField(default=True)
    last_contacted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "phone"]),
            models.Index(fields=["organization", "email"]),
            models.Index(fields=["organization", "source"]),
            models.Index(fields=["organization", "assigned_to"]),
        ]
        unique_together = [("organization", "phone")]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip() or self.phone

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.phone


class ContactGroup(TenantModel):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    contacts = models.ManyToManyField(Contact, related_name="groups", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("organization", "name")]
        indexes = [
            models.Index(fields=["organization", "name"]),
            models.Index(fields=["organization", "category"]),
            models.Index(fields=["organization", "is_active"]),
        ]

    def __str__(self):
        return self.name

    @property
    def contact_count(self):
        return self.contacts.count()


class PipelineStage(TenantModel):
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=7, default="#6366f1")
    is_won = models.BooleanField(default=False)
    is_lost = models.BooleanField(default=False)

    class Meta:
        ordering = ["order"]
        unique_together = [("organization", "name")]

    def __str__(self):
        return self.name


class Lead(TenantModel):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="leads")
    title = models.CharField(max_length=255)
    stage = models.ForeignKey(
        PipelineStage,
        on_delete=models.SET_NULL,
        null=True,
        related_name="leads",
    )
    value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="INR")
    score = models.PositiveIntegerField(default=0)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_leads",
    )
    source = models.CharField(max_length=50, blank=True)
    expected_close_date = models.DateField(null=True, blank=True)
    custom_fields = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "stage"]),
            models.Index(fields=["organization", "assigned_to"]),
            models.Index(fields=["organization", "score"]),
            models.Index(fields=["organization", "priority"]),
        ]

    def __str__(self):
        return self.title


class Activity(TenantModel):
    class Type(models.TextChoices):
        NOTE = "note", "Note"
        CALL = "call", "Call"
        EMAIL = "email", "Email"
        MEETING = "meeting", "Meeting"
        TASK = "task", "Task"
        WHATSAPP = "whatsapp", "WhatsApp"
        FOLLOW_UP = "follow_up", "Follow Up"

    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="activities",
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="activities",
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_activities",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_activities",
    )
    is_completed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "due_at"]),
            models.Index(fields=["organization", "is_completed"]),
            models.Index(fields=["organization", "type"]),
        ]

    def __str__(self):
        return self.title
