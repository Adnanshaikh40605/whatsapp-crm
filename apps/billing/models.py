import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Subscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past Due"
        CANCELLED = "cancelled", "Cancelled"
        TRIALING = "trialing", "Trialing"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.CharField(max_length=20, default="free")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIALING)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField(null=True, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.organization.name} - {self.plan}"


class UsageRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="usage_records",
    )
    metric = models.CharField(max_length=50)
    count = models.PositiveIntegerField(default=0)
    period_start = models.DateField()
    period_end = models.DateField()

    class Meta:
        unique_together = [("organization", "metric", "period_start")]
        indexes = [models.Index(fields=["organization", "metric", "period_start"])]

    def __str__(self):
        return f"{self.organization.name} - {self.metric}: {self.count}"


class Wallet(models.Model):
    """Prepaid balance an organization draws down as it sends WhatsApp messages."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="wallet",
    )
    # Money stored in integer minor units (cents) to avoid float drift.
    balance_cents = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="USD")
    low_balance_threshold_cents = models.BigIntegerField(default=500)
    auto_topup_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.organization.name} wallet: {self.balance_display}"

    @property
    def balance(self):
        return self.balance_cents / 100

    @property
    def balance_display(self):
        return f"{self.currency} {self.balance:.2f}"

    @property
    def is_low(self):
        return self.balance_cents <= self.low_balance_threshold_cents

    def post_transaction(self, *, txn_type, amount_cents, reference="", gateway_payment_id="", conversation_charge=None):
        """Atomically adjust the balance and record a ledger entry.

        Credits (topup/refund/positive adjustment) increase the balance,
        debits decrease it. ``amount_cents`` is always supplied as a positive int.
        """
        from django.db import transaction

        signed = amount_cents if txn_type in (
            WalletTransaction.Type.TOPUP,
            WalletTransaction.Type.REFUND,
            WalletTransaction.Type.ADJUSTMENT,
        ) else -amount_cents

        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(pk=self.pk)
            wallet.balance_cents += signed
            wallet.save(update_fields=["balance_cents", "updated_at"])
            self.balance_cents = wallet.balance_cents
            return WalletTransaction.objects.create(
                wallet=wallet,
                type=txn_type,
                amount_cents=amount_cents,
                balance_after_cents=wallet.balance_cents,
                reference=reference,
                gateway_payment_id=gateway_payment_id,
                conversation_charge=conversation_charge,
            )


class WalletTransaction(models.Model):
    class Type(models.TextChoices):
        TOPUP = "topup", "Top-up"
        DEBIT = "debit", "Debit"
        REFUND = "refund", "Refund"
        ADJUSTMENT = "adjustment", "Adjustment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    type = models.CharField(max_length=20, choices=Type.choices)
    amount_cents = models.BigIntegerField()
    balance_after_cents = models.BigIntegerField()
    reference = models.CharField(max_length=255, blank=True)
    gateway_payment_id = models.CharField(max_length=255, blank=True)
    conversation_charge = models.ForeignKey(
        "billing.ConversationCharge",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["wallet", "-created_at"])]

    def __str__(self):
        return f"{self.type} {self.amount_cents}c"


class ConversationCharge(models.Model):
    """One row per billable 24-hour WhatsApp conversation window (Meta pricing model)."""

    class Category(models.TextChoices):
        MARKETING = "marketing", "Marketing"
        UTILITY = "utility", "Utility"
        AUTHENTICATION = "authentication", "Authentication"
        SERVICE = "service", "Service"  # free-form in service window — billed at 0

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="conversation_charges",
    )
    wa_conversation_id = models.CharField(max_length=128)
    category = models.CharField(max_length=20, choices=Category.choices)
    country_code = models.CharField(max_length=4, blank=True)
    amount_cents = models.BigIntegerField(default=0)
    charged_at = models.DateTimeField(default=timezone.now)

    class Meta:
        # Meta charges once per conversation window; dedupe on the conversation id.
        unique_together = [("organization", "wa_conversation_id")]
        indexes = [models.Index(fields=["organization", "charged_at"])]

    def __str__(self):
        return f"{self.category} {self.amount_cents}c ({self.country_code})"


class PlanLimit(models.Model):
    """Per-plan entitlements enforced across the app (seats, channels, free conversations)."""

    plan = models.CharField(max_length=20, unique=True)
    seats = models.IntegerField(default=1)  # -1 = unlimited
    channels = models.IntegerField(default=1)
    monthly_free_conversations = models.IntegerField(default=0)
    features = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"PlanLimit<{self.plan}>"
