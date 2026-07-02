from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class MediaAsset(TenantModel):
    class AssetType(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        DOCUMENT = "document", "Document"
        PDF = "pdf", "PDF"

    name = models.CharField(max_length=255)
    asset_type = models.CharField(max_length=20, choices=AssetType.choices)
    file = models.FileField(upload_to="whatsapp_media/")
    mime_type = models.CharField(max_length=100, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    meta_media_id = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_media_assets",
    )

    class Meta:
        indexes = [
            models.Index(fields=["organization", "asset_type"]),
            models.Index(fields=["organization", "created_at"]),
        ]

    def __str__(self):
        return self.name


class WhatsAppTemplate(TenantModel):
    class Category(models.TextChoices):
        MARKETING = "marketing", "Marketing"
        UTILITY = "utility", "Utility"
        AUTHENTICATION = "authentication", "Authentication"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending Approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    name = models.CharField(max_length=255)
    language = models.CharField(max_length=10, default="en")
    category = models.CharField(max_length=20, choices=Category.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    header = models.JSONField(default=dict, blank=True)
    body = models.TextField()
    footer = models.CharField(max_length=255, blank=True)
    buttons = models.JSONField(default=list, blank=True)
    variables = models.JSONField(default=list, blank=True)
    components = models.JSONField(default=list, blank=True)
    examples = models.JSONField(default=dict, blank=True)
    template_type = models.CharField(max_length=50, blank=True)
    whatsapp_template_id = models.CharField(max_length=255, blank=True)
    meta_status = models.CharField(max_length=50, blank=True)
    quality_rating = models.CharField(max_length=50, blank=True)
    rejected_reason = models.TextField(blank=True)
    media_asset = models.ForeignKey(
        MediaAsset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="templates",
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = [("organization", "name", "language")]
        indexes = [models.Index(fields=["organization", "status", "category"])]

    def __str__(self):
        return self.name


class Campaign(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        RUNNING = "running", "Running"
        EXECUTED = "executed", "Executed"
        COMPLETED = "completed", "Completed"
        PAUSED = "paused", "Paused"
        CANCELLED = "cancelled", "Cancelled"

    class CampaignType(models.TextChoices):
        BROADCAST = "broadcast", "Broadcast"
        MEDIA = "media", "Media Campaign"
        CAROUSEL = "carousel", "Carousel"
        RECURRING = "recurring", "Recurring"

    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        PDF = "pdf", "PDF"
        DOCUMENT = "document", "Document"
        MULTI_IMAGE = "multi_image", "Multi Image"

    name = models.CharField(max_length=255)
    campaign_type = models.CharField(
        max_length=20, choices=CampaignType.choices, default=CampaignType.BROADCAST,
    )
    media_type = models.CharField(max_length=20, choices=MediaType.choices, blank=True)
    media_config = models.JSONField(default=dict, blank=True)
    carousel_cards = models.JSONField(default=list, blank=True)
    contact_group = models.ForeignKey(
        "crm.ContactGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campaigns",
    )
    template = models.ForeignKey(
        WhatsAppTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campaigns",
    )
    message_content = models.TextField(blank=True)
    audience_filter = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    is_recurring = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False, db_index=True)
    recurrence_rule = models.CharField(max_length=255, blank=True)
    total_recipients = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    read_count = models.PositiveIntegerField(default=0)
    reply_count = models.PositiveIntegerField(default=0)
    click_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="campaigns",
    )

    class Meta:
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "scheduled_at"]),
            models.Index(fields=["organization", "is_archived"]),
        ]

    def __str__(self):
        return self.name


class CampaignRecipient(TenantModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        READ = "read", "Read"
        REPLIED = "replied", "Replied"
        CLICKED = "clicked", "Clicked"
        FAILED = "failed", "Failed"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="recipients")
    contact = models.ForeignKey("crm.Contact", on_delete=models.CASCADE, related_name="campaign_sends")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    whatsapp_message_id = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    failure_code = models.CharField(max_length=50, blank=True)

    class Meta:
        unique_together = [("campaign", "contact")]
        indexes = [models.Index(fields=["organization", "campaign", "status"])]


class CampaignClickEvent(TenantModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="click_events")
    recipient = models.ForeignKey(CampaignRecipient, on_delete=models.CASCADE, related_name="click_events")
    contact = models.ForeignKey("crm.Contact", on_delete=models.CASCADE, related_name="campaign_click_events")
    button_type = models.CharField(max_length=30, blank=True)
    button_name = models.CharField(max_length=255, blank=True)
    button_url = models.CharField(max_length=500, blank=True)
    click_count = models.PositiveIntegerField(default=1)
    clicked_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["organization", "campaign", "clicked_at"]),
            models.Index(fields=["organization", "campaign", "button_name"]),
        ]


class AdAttribution(TenantModel):
    class Source(models.TextChoices):
        FACEBOOK = "facebook", "Facebook Ads"
        INSTAGRAM = "instagram", "Instagram Ads"
        ORGANIC = "organic", "Organic"
        DIRECT = "direct", "Direct"

    source = models.CharField(max_length=20, choices=Source.choices)
    campaign_name = models.CharField(max_length=255, blank=True)
    ad_id = models.CharField(max_length=255, blank=True)
    contact = models.ForeignKey(
        "crm.Contact", on_delete=models.SET_NULL, null=True, blank=True, related_name="ad_attributions",
    )
    lead = models.ForeignKey(
        "crm.Lead", on_delete=models.SET_NULL, null=True, blank=True, related_name="ad_attributions",
    )
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    converted = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["organization", "source", "created_at"])]
