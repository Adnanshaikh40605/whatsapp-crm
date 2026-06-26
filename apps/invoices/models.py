from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Invoice(TenantModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        PAID = "paid", "Paid"
        PARTIAL = "partial", "Partially Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    invoice_number = models.CharField(max_length=50, db_index=True)
    quotation = models.ForeignKey(
        "quotes.Quotation", on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices"
    )
    contact = models.ForeignKey(
        "crm.Contact", on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices"
    )
    title = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    line_items = models.JSONField(default=list)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="INR")
    due_date = models.DateField(null=True, blank=True)
    payment_link = models.URLField(blank=True)
    gst_number = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    sent_via_whatsapp = models.BooleanField(default=False)
    pdf_url = models.URLField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="invoices"
    )

    class Meta:
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "due_date"]),
        ]
        unique_together = [("organization", "invoice_number")]

    @property
    def balance_due(self):
        return float(self.total) - float(self.amount_paid)

    def calculate_totals(self):
        subtotal = sum(
            float(item.get("quantity", 1)) * float(item.get("unit_price", 0))
            for item in self.line_items
        )
        self.subtotal = subtotal
        self.tax_amount = (subtotal - float(self.discount)) * float(self.tax_rate) / 100
        self.total = subtotal - float(self.discount) + float(self.tax_amount)
