from django.contrib import admin

from apps.inbox.models import CannedReply, Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("contact", "status", "assigned_to", "last_message_at", "organization")
    list_filter = ("status",)
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "direction", "message_type", "status", "created_at")


@admin.register(CannedReply)
class CannedReplyAdmin(admin.ModelAdmin):
    list_display = ("title", "shortcut", "category", "organization")
