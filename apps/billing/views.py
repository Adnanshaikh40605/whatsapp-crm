from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.exceptions import APIResponse
from apps.core.models import get_current_organization
from apps.core.permissions import IsManagerOrAbove, IsOrganizationMember


class SubscriptionView(APIView):
    """Disabled in internal mode — no SaaS billing."""

    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        if getattr(settings, "INTERNAL_MODE", True):
            return APIResponse.success({
                "mode": "internal",
                "message": "Internal deployment — no subscription billing",
                "plan": "internal",
                "status": "active",
            })
        from apps.billing.models import Subscription
        from apps.billing.serializers import SubscriptionSerializer
        from apps.core.models import get_current_organization

        org = get_current_organization()
        subscription, _ = Subscription.objects.get_or_create(
            organization=org, defaults={"plan": org.plan},
        )
        return APIResponse.success(SubscriptionSerializer(subscription).data)


class UsageView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        if getattr(settings, "INTERNAL_MODE", True):
            return APIResponse.success([])
        from django.utils import timezone
        from apps.billing.models import UsageRecord
        from apps.billing.serializers import UsageRecordSerializer
        from apps.core.models import get_current_organization

        org = get_current_organization()
        period_start = timezone.now().date().replace(day=1)
        records = UsageRecord.objects.filter(organization=org, period_start=period_start)
        return APIResponse.success(UsageRecordSerializer(records, many=True).data)


class WalletView(APIView):
    """Prepaid wallet balance + a snapshot of recent ledger activity."""

    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        from apps.billing.models import Wallet
        from apps.billing.serializers import WalletSerializer, WalletTransactionSerializer

        org = get_current_organization()
        wallet, _ = Wallet.objects.get_or_create(organization=org)
        recent = wallet.transactions.all()[:10]
        return APIResponse.success({
            "wallet": WalletSerializer(wallet).data,
            "recent_transactions": WalletTransactionSerializer(recent, many=True).data,
        })


class WalletTopUpView(APIView):
    """Add funds to the wallet.

    NOTE: payment-gateway capture (Stripe/Razorpay) is not yet wired. This
    records the credit once a verified ``gateway_payment_id`` is supplied; until
    a gateway is connected it is intended for admin/manual top-ups only.
    """

    permission_classes = [IsAuthenticated, IsManagerOrAbove]

    def post(self, request):
        from apps.billing.models import Wallet, WalletTransaction
        from apps.billing.serializers import TopUpSerializer, WalletSerializer

        serializer = TopUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org = get_current_organization()
        wallet, _ = Wallet.objects.get_or_create(organization=org)
        txn = wallet.post_transaction(
            txn_type=WalletTransaction.Type.TOPUP,
            amount_cents=serializer.validated_data["amount_cents"],
            reference="manual_topup",
            gateway_payment_id=serializer.validated_data.get("gateway_payment_id", ""),
        )
        return APIResponse.success(
            {"wallet": WalletSerializer(wallet).data, "transaction_id": str(txn.id)},
            message="Wallet topped up",
        )


class WalletTransactionsView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        from apps.billing.models import Wallet
        from apps.billing.serializers import WalletTransactionSerializer

        org = get_current_organization()
        wallet, _ = Wallet.objects.get_or_create(organization=org)
        txns = wallet.transactions.all()[:200]
        return APIResponse.success(WalletTransactionSerializer(txns, many=True).data)
