from django.contrib import admin

from apps.campaigns.models import Campaign, WhatsAppTemplate


@admin.register(WhatsAppTemplate)
class WhatsAppTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "status", "organization")


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "total_recipients", "sent_count", "organization")
