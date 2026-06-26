from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Workflow(TenantModel):
    class Trigger(models.TextChoices):
        NEW_LEAD = "new_lead", "New Lead"
        NEW_MESSAGE = "new_message", "New Message"
        STAGE_CHANGE = "stage_change", "Stage Change"
        TAG_ADDED = "tag_added", "Tag Added"
        CAMPAIGN_CLICKED = "campaign_clicked", "Campaign Clicked"
        NO_REPLY = "no_reply", "No Reply"
        SCHEDULE = "schedule", "Schedule"
        MANUAL = "manual", "Manual"

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    trigger = models.CharField(max_length=30, choices=Trigger.choices)
    trigger_config = models.JSONField(default=dict, blank=True)
    flow_definition = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    run_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="workflows",
    )

    class Meta:
        indexes = [models.Index(fields=["organization", "trigger", "is_active"])]

    def __str__(self):
        return self.name


class FollowUpSequence(TenantModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    steps = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class FollowUpExecution(TenantModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    sequence = models.ForeignKey(FollowUpSequence, on_delete=models.CASCADE, related_name="executions")
    lead = models.ForeignKey("crm.Lead", on_delete=models.CASCADE, related_name="follow_ups")
    current_step = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "status", "next_run_at"])]


class BotFlow(TenantModel):
    class TriggerType(models.TextChoices):
        KEYWORD = "keyword", "Keyword Match"
        ANY_MESSAGE = "any_message", "Any Message"
        TEMPLATE_REPLY = "template_reply", "Template Reply"
        BUTTON_CLICK = "button_click", "Button Click"

    title = models.CharField(max_length=255)
    start_trigger = models.CharField(max_length=255, help_text="e.g. hi, hello")
    trigger_type = models.CharField(
        max_length=20, choices=TriggerType.choices, default=TriggerType.KEYWORD
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    flow_data = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="bot_flows",
    )

    class Meta:
        indexes = [
            models.Index(fields=["organization", "is_active"]),
            models.Index(fields=["organization", "start_trigger"]),
        ]

    def __str__(self):
        return self.title


class BotReply(TenantModel):
    class ReplyType(models.TextChoices):
        SIMPLE = "simple", "Simple Bot Reply"
        MEDIA = "media", "Media Bot Reply"
        INTERACTIVE = "interactive", "Advance Interactive Bot Reply"

    bot_flow = models.ForeignKey(
        BotFlow,
        on_delete=models.CASCADE,
        related_name="replies",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    reply_type = models.CharField(max_length=20, choices=ReplyType.choices, default=ReplyType.SIMPLE)
    content = models.TextField(blank=True)
    media_url = models.URLField(blank=True)
    media_type = models.CharField(max_length=20, blank=True)
    buttons = models.JSONField(default=list, blank=True)
    options = models.JSONField(default=list, blank=True)
    node_id = models.CharField(max_length=100, blank=True)
    position_x = models.FloatField(default=0)
    position_y = models.FloatField(default=0)
    next_node_id = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "bot_flow", "reply_type"])]

    def __str__(self):
        return self.title
