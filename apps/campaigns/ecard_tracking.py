"""E-card / E-Brochure click tracking via unique redirect tokens."""

from __future__ import annotations

import secrets

from django.conf import settings
from django.utils import timezone

from apps.campaigns.models import ECardClick, ECardTrackedLink
from apps.embed_api.services import normalize_phone

DEFAULT_ECARD_DESTINATION = "https://www.pestcontrol99.com/e-card/"


def public_api_base() -> str:
    base = getattr(settings, "PUBLIC_BASE_URL", "") or ""
    if base:
        return base.rstrip("/")
    return "https://api.driveronhire.ai"


def tracking_redirect_url(token: str) -> str:
    return f"{public_api_base()}/r/{token}"


def create_tracked_link(
    *,
    organization,
    phone: str,
    destination_url: str = DEFAULT_ECARD_DESTINATION,
    customer_name: str = "",
    external_id: str = "",
    template_name: str = "",
    created_by=None,
) -> ECardTrackedLink:
    token = secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:20]
    return ECardTrackedLink.objects.create(
        organization=organization,
        token=token,
        phone=normalize_phone(phone),
        customer_name=(customer_name or "").strip()[:255],
        external_id=str(external_id or "").strip()[:100],
        destination_url=(destination_url or DEFAULT_ECARD_DESTINATION).strip(),
        template_name=(template_name or "").strip()[:255],
        created_by=created_by,
    )


def record_click(link: ECardTrackedLink, *, ip: str | None = None, user_agent: str = "") -> ECardClick:
    click = ECardClick.objects.create(
        organization=link.organization,
        link=link,
        phone=link.phone,
        customer_name=link.customer_name,
        external_id=link.external_id,
        ip_address=ip,
        user_agent=(user_agent or "")[:500],
    )
    link.click_count = (link.click_count or 0) + 1
    link.last_clicked_at = timezone.now()
    link.save(update_fields=["click_count", "last_clicked_at", "updated_at"])
    return click


def serialize_click(click: ECardClick) -> dict:
    return {
        "id": str(click.id),
        "phone": click.phone,
        "customer_name": click.customer_name,
        "external_id": click.external_id,
        "clicked_at": click.clicked_at.isoformat() if click.clicked_at else None,
        "destination_url": click.link.destination_url if click.link_id else "",
        "template_name": click.link.template_name if click.link_id else "",
        "token": click.link.token if click.link_id else "",
    }


def serialize_link(link: ECardTrackedLink) -> dict:
    return {
        "id": str(link.id),
        "token": link.token,
        "phone": link.phone,
        "customer_name": link.customer_name,
        "external_id": link.external_id,
        "destination_url": link.destination_url,
        "template_name": link.template_name,
        "tracking_url": tracking_redirect_url(link.token),
        "click_count": link.click_count,
        "last_clicked_at": link.last_clicked_at.isoformat() if link.last_clicked_at else None,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def find_url_button_index(template) -> int | None:
    """Return 0-based index of the first URL button in the template."""
    buttons = template.buttons or []
    if isinstance(buttons, list):
        for idx, btn in enumerate(buttons):
            if not isinstance(btn, dict):
                continue
            btn_type = str(btn.get("type") or "").upper()
            if btn_type in {"URL", "WEBSITE"}:
                return idx
    components = template.components or []
    for component in components:
        if not isinstance(component, dict):
            continue
        if str(component.get("type") or "").upper() != "BUTTONS":
            continue
        for idx, btn in enumerate(component.get("buttons") or []):
            if not isinstance(btn, dict):
                continue
            btn_type = str(btn.get("type") or "").upper()
            if btn_type in {"URL", "WEBSITE"}:
                return idx
    return None


def url_button_is_dynamic(template, index: int) -> bool:
    """True if the URL button at index contains a Meta {{1}} placeholder."""
    buttons = template.buttons or []
    if isinstance(buttons, list) and 0 <= index < len(buttons):
        btn = buttons[index]
        if isinstance(btn, dict):
            url = str(btn.get("url") or "")
            return "{{1}}" in url or "{{ 1 }}" in url
    components = template.components or []
    for component in components:
        if not isinstance(component, dict):
            continue
        if str(component.get("type") or "").upper() != "BUTTONS":
            continue
        btns = component.get("buttons") or []
        if 0 <= index < len(btns) and isinstance(btns[index], dict):
            url = str(btns[index].get("url") or "")
            return "{{1}}" in url or "{{ 1 }}" in url
    return False
