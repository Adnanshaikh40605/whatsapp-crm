"""Wallet metering — converts WhatsApp conversation events into wallet debits.

Pricing here is a simplified, transparent stand-in for Meta's per-country,
per-category conversation rates. Replace ``RATE_TABLE`` with synced Meta rates
when wiring real billing. Amounts are in integer cents (USD by default).
"""
from __future__ import annotations

from apps.billing.models import ConversationCharge, Wallet, WalletTransaction

# Default per-conversation price in cents, by category. Service window is free.
DEFAULT_RATES_CENTS = {
    ConversationCharge.Category.MARKETING: 3,
    ConversationCharge.Category.UTILITY: 1,
    ConversationCharge.Category.AUTHENTICATION: 1,
    ConversationCharge.Category.SERVICE: 0,
}

# Optional per-country overrides (ISO country code -> {category: cents}).
COUNTRY_RATES_CENTS = {
    "IN": {  # India — illustrative cheaper utility/marketing rates
        ConversationCharge.Category.MARKETING: 1,
        ConversationCharge.Category.UTILITY: 0,
        ConversationCharge.Category.AUTHENTICATION: 0,
    },
}


def price_for(category: str, country_code: str = "") -> int:
    country = (country_code or "").upper()
    if country in COUNTRY_RATES_CENTS and category in COUNTRY_RATES_CENTS[country]:
        return COUNTRY_RATES_CENTS[country][category]
    return DEFAULT_RATES_CENTS.get(category, 0)


def meter_conversation(organization, wa_conversation_id: str, category: str, country_code: str = ""):
    """Idempotently charge a single WhatsApp conversation window.

    Returns the ConversationCharge (existing or newly created). Debits the
    wallet exactly once per (organization, wa_conversation_id). Safe to call
    repeatedly from webhook handlers.
    """
    amount = price_for(category, country_code)
    charge, created = ConversationCharge.objects.get_or_create(
        organization=organization,
        wa_conversation_id=wa_conversation_id,
        defaults={"category": category, "country_code": country_code, "amount_cents": amount},
    )
    if not created:
        return charge  # already billed for this conversation window

    if amount > 0:
        wallet, _ = Wallet.objects.get_or_create(organization=organization)
        wallet.post_transaction(
            txn_type=WalletTransaction.Type.DEBIT,
            amount_cents=amount,
            reference=f"conversation:{category}:{country_code}",
            conversation_charge=charge,
        )
    return charge
