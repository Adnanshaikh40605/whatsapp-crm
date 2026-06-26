from django.contrib import admin

from apps.billing.models import (
    ConversationCharge,
    PlanLimit,
    Subscription,
    UsageRecord,
    Wallet,
    WalletTransaction,
)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "status", "current_period_end")


@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ("organization", "metric", "count", "period_start")


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("organization", "balance_display", "currency", "is_low", "updated_at")
    readonly_fields = ("balance_cents", "updated_at", "created_at")


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "type", "amount_cents", "balance_after_cents", "created_at")
    list_filter = ("type",)


@admin.register(ConversationCharge)
class ConversationChargeAdmin(admin.ModelAdmin):
    list_display = ("organization", "category", "country_code", "amount_cents", "charged_at")
    list_filter = ("category",)


@admin.register(PlanLimit)
class PlanLimitAdmin(admin.ModelAdmin):
    list_display = ("plan", "seats", "channels", "monthly_free_conversations")
