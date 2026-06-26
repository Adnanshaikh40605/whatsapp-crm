from django.urls import path

from apps.billing.views import (
    SubscriptionView,
    UsageView,
    WalletTopUpView,
    WalletTransactionsView,
    WalletView,
)

urlpatterns = [
    path("subscription/", SubscriptionView.as_view(), name="subscription"),
    path("usage/", UsageView.as_view(), name="usage"),
    path("wallet/", WalletView.as_view(), name="wallet"),
    path("wallet/topup/", WalletTopUpView.as_view(), name="wallet-topup"),
    path("wallet/transactions/", WalletTransactionsView.as_view(), name="wallet-transactions"),
]
