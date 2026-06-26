from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Conversation(TenantModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PENDING = "pending", "Pending"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    contact = models.ForeignKey(
        "crm.Contact",
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_conversations",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    tags = models.JSONField(default=list, blank=True)
    priority = models.CharField(max_length=10, default="normal")
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_message_preview = models.CharField(max_length=255, blank=True)
    unread_count = models.PositiveIntegerField(default=0)
    is_bot_active = models.BooleanField(default=True)
    sla_due_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "assigned_to"]),
            models.Index(fields=["organization", "last_message_at"]),
        ]

    def __str__(self):
        return f"Conversation with {self.contact}"


class Message(TenantModel):
    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        SMS = "sms", "SMS"

    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"

    class MessageType(models.TextChoices):
        TEXT = "text", "Text"
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        AUDIO = "audio", "Audio"
        DOCUMENT = "document", "Document"
        TEMPLATE = "template", "Template"
        INTERACTIVE = "interactive", "Interactive"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        READ = "read", "Read"
        FAILED = "failed", "Failed"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.WHATSAPP)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    message_type = models.CharField(max_length=20, choices=MessageType.choices, default=MessageType.TEXT)
    content = models.TextField(blank=True)
    media_url = models.URLField(blank=True)
    template_name = models.CharField(max_length=255, blank=True)
    whatsapp_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    provider_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_messages",
    )
    is_internal_note = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["organization", "channel", "created_at"]),
            models.Index(fields=["organization", "whatsapp_message_id"]),
            models.Index(fields=["organization", "provider_message_id"]),
            models.Index(fields=["organization", "status"]),
        ]

    def __str__(self):
        return f"{self.direction} {self.message_type} - {self.content[:50]}"


class CannedReply(TenantModel):
    title = models.CharField(max_length=255)
    content = models.TextField()
    shortcut = models.CharField(max_length=50, blank=True)
    category = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="canned_replies",
    )

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title
