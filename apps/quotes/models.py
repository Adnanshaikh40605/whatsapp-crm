from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Quotation(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        VIEWED = "viewed", "Viewed"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    quote_number = models.CharField(max_length=50, db_index=True)
    lead = models.ForeignKey(
        "crm.Lead", on_delete=models.SET_NULL, null=True, blank=True, related_name="quotations"
    )
    contact = models.ForeignKey(
        "crm.Contact", on_delete=models.SET_NULL, null=True, blank=True, related_name="quotations"
    )
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    line_items = models.JSONField(default=list)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="INR")
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    valid_until = models.DateField(null=True, blank=True)
    sent_via_whatsapp = models.BooleanField(default=False)
    pdf_url = models.URLField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="quotations"
    )

    class Meta:
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "quote_number"]),
        ]
        unique_together = [("organization", "quote_number")]

    def __str__(self):
        return f"{self.quote_number} - {self.title}"

    def calculate_totals(self):
        subtotal = sum(
            float(item.get("quantity", 1)) * float(item.get("unit_price", 0))
            for item in self.line_items
        )
        self.subtotal = subtotal
        self.tax_amount = (subtotal - float(self.discount)) * float(self.tax_rate) / 100
        self.total = subtotal - float(self.discount) + float(self.tax_amount)
