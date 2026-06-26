from django.contrib import admin

from apps.automation.models import BotFlow, BotReply, FollowUpExecution, FollowUpSequence, Workflow


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ("name", "trigger", "is_active", "organization")


@admin.register(FollowUpSequence)
class FollowUpSequenceAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "organization")


@admin.register(FollowUpExecution)
class FollowUpExecutionAdmin(admin.ModelAdmin):
    list_display = ("sequence", "lead", "status", "next_run_at")


@admin.register(BotFlow)
class BotFlowAdmin(admin.ModelAdmin):
    list_display = ("title", "start_trigger", "is_active", "organization")


@admin.register(BotReply)
class BotReplyAdmin(admin.ModelAdmin):
    list_display = ("title", "reply_type", "bot_flow", "organization")
