from django.contrib import admin

from apps.invoices.models import Invoice


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "title", "status", "total", "amount_paid", "organization")
