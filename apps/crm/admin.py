from django.contrib import admin

from apps.crm.models import Activity, Contact, Lead, PipelineStage


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "email", "organization", "source")
    search_fields = ("first_name", "last_name", "phone", "email")


@admin.register(PipelineStage)
class PipelineStageAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "order", "is_won", "is_lost")


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("title", "contact", "stage", "score", "priority", "organization")
    list_filter = ("priority", "stage")


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("title", "type", "lead", "contact", "is_completed", "due_at")
