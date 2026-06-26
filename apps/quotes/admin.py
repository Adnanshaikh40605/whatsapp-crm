from django.contrib import admin

from apps.quotes.models import Quotation


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ("quote_number", "title", "status", "total", "organization")
