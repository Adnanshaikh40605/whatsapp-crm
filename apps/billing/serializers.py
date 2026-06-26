from rest_framework import serializers

from apps.billing.models import (
    ConversationCharge,
    Subscription,
    UsageRecord,
    Wallet,
    WalletTransaction,
)


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = "__all__"


class UsageRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageRecord
        fields = "__all__"


class WalletSerializer(serializers.ModelSerializer):
    balance = serializers.FloatField(read_only=True)
    balance_display = serializers.CharField(read_only=True)
    is_low = serializers.BooleanField(read_only=True)

    class Meta:
        model = Wallet
        fields = (
            "id",
            "balance_cents",
            "balance",
            "balance_display",
            "currency",
            "low_balance_threshold_cents",
            "is_low",
            "auto_topup_enabled",
            "updated_at",
        )
        read_only_fields = ("id", "balance_cents", "updated_at")


class WalletTransactionSerializer(serializers.ModelSerializer):
    amount = serializers.SerializerMethodField()

    class Meta:
        model = WalletTransaction
        fields = (
            "id",
            "type",
            "amount_cents",
            "amount",
            "balance_after_cents",
            "reference",
            "gateway_payment_id",
            "created_at",
        )

    def get_amount(self, obj):
        return obj.amount_cents / 100


class ConversationChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationCharge
        fields = (
            "id",
            "wa_conversation_id",
            "category",
            "country_code",
            "amount_cents",
            "charged_at",
        )


class TopUpSerializer(serializers.Serializer):
    amount_cents = serializers.IntegerField(min_value=100)  # min $1.00
    gateway_payment_id = serializers.CharField(required=False, allow_blank=True)
