import csv
import io
import json
import re
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Avg, Count, F, Min, Max, Q
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone
from openpyxl import Workbook

from apps.campaigns.models import Campaign, CampaignClickEvent, CampaignRecipient
from apps.inbox.models import Conversation


FAILURE_CODE_MAP = {
    "131026": "Template missing or unavailable",
    "131047": "User blocked business",
    "131051": "Unsupported message type",
    "131052": "Media download error",
    "131053": "Media upload error",
    "130472": "User's number is part of an experiment",
    "131000": "Something went wrong",
}


def _pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def _contact_name(contact) -> str:
    parts = [contact.first_name or "", contact.last_name or ""]
    name = " ".join(p for p in parts if p).strip()
    return name or "Contact"


def _parse_failure_code(error_message: str) -> str:
    if not error_message:
        return ""
    match = re.search(r"\b(13\d{4}|130\d{3})\b", error_message)
    if match:
        return match.group(1)
    lowered = error_message.lower()
    if "invalid" in lowered and "phone" in lowered:
        return "PHONE_INVALID"
    if "blocked" in lowered:
        return "131047"
    return ""


def _failure_reason(code: str, error_message: str) -> str:
    if code in FAILURE_CODE_MAP:
        return FAILURE_CODE_MAP[code]
    if code == "PHONE_INVALID":
        return "Phone invalid"
    return error_message or "Unknown error"


def _can_retry(code: str) -> bool:
    if code in {"131047"}:
        return False
    if code == "PHONE_INVALID":
        return False
    return True


def _date_range_filter(qs, field: str, preset: str, date_from: str | None, date_to: str | None):
    now = timezone.now()
    start = end = None
    if preset == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif preset == "yesterday":
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
    elif date_from or date_to:
        if date_from:
            start = timezone.make_aware(datetime.fromisoformat(date_from.replace("Z", "")))
        if date_to:
            end = timezone.make_aware(datetime.fromisoformat(date_to.replace("Z", "")))
    if start:
        qs = qs.filter(**{f"{field}__gte": start})
    if end:
        qs = qs.filter(**{f"{field}__lt": end})
    return qs


def _conversation_id_for(contact) -> str:
    conv = Conversation.objects.filter(contact=contact).order_by("-last_message_at").first()
    return str(conv.id) if conv else ""


def _duration_label(start, end) -> str:
    if not start or not end:
        return "—"
    delta = end - start
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _timeline(recipients, field: str, hours: int = 24) -> list[dict]:
    now = timezone.now()
    start = now - timedelta(hours=hours)
    buckets: dict[str, int] = {}
    for i in range(hours):
        label = (start + timedelta(hours=i + 1)).strftime("%H:00")
        buckets[label] = 0
    for recipient in recipients.filter(**{f"{field}__gte": start}):
        ts = getattr(recipient, field)
        if not ts:
            continue
        label = ts.strftime("%H:00")
        buckets[label] = buckets.get(label, 0) + 1
    return [{"label": k, "value": v} for k, v in buckets.items()]


def get_overview(campaign: Campaign) -> dict:
    recipients = campaign.recipients.select_related("contact")
    audience = campaign.total_recipients or recipients.count()
    sent = campaign.sent_count
    delivered = campaign.delivered_count
    read = campaign.read_count
    clicked = campaign.click_count
    failed = campaign.failed_count
    completed_at = recipients.aggregate(latest=Max("read_at"))["latest"] or recipients.aggregate(latest=Max("sent_at"))["latest"]
    duration = _duration_label(campaign.created_at, completed_at)

    return {
        "campaign": {
            "id": str(campaign.id),
            "name": campaign.name,
            "campaign_type": campaign.campaign_type,
            "status": campaign.status,
            "template_name": campaign.template.name if campaign.template else "",
            "template_category": campaign.template.category if campaign.template else "",
            "created_by": (
                campaign.created_by.get_full_name() or campaign.created_by.email
                if campaign.created_by else ""
            ),
            "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
            "completed_at": completed_at.isoformat() if completed_at else None,
            "duration": duration,
        },
        "summary": {
            "audience": audience,
            "sent": sent,
            "delivered": delivered,
            "read": read,
            "clicked": clicked,
            "failed": failed,
            "success_rate": _pct(sent - failed, audience),
            "delivery_rate": _pct(delivered, sent),
            "read_rate": _pct(read, delivered),
            "ctr": _pct(clicked, delivered),
        },
        "timelines": {
            "sent": _timeline(recipients, "sent_at"),
            "delivered": _timeline(recipients, "delivered_at"),
            "read": _timeline(recipients, "read_at"),
        },
    }


def get_tab_stats(campaign: Campaign, tab: str) -> dict:
    recipients = campaign.recipients.select_related("contact")
    audience = campaign.total_recipients or recipients.count()
    sent = campaign.sent_count
    delivered = campaign.delivered_count
    read = campaign.read_count
    failed = campaign.failed_count
    clicks = CampaignClickEvent.objects.filter(campaign=campaign)

    if tab == "sent":
        return {
            "total": sent,
            "percent": _pct(sent, audience),
        }
    if tab == "delivered":
        delays = []
        for r in recipients.filter(delivered_at__isnull=False, sent_at__isnull=False):
            delays.append((r.delivered_at - r.sent_at).total_seconds())
        avg_delay = round(sum(delays) / len(delays), 1) if delays else 0
        return {
            "total": delivered,
            "percent": _pct(delivered, sent),
            "average_delivery_seconds": avg_delay,
            "fastest_delivery_seconds": min(delays) if delays else 0,
            "slowest_delivery_seconds": max(delays) if delays else 0,
            "delivery_success_percent": _pct(delivered, sent),
        }
    if tab == "read":
        read_times = []
        for r in recipients.filter(read_at__isnull=False, delivered_at__isnull=False):
            read_times.append((r.read_at - r.delivered_at).total_seconds())
        avg_read = round(sum(read_times) / len(read_times), 1) if read_times else 0
        return {
            "read_percent": _pct(read, delivered),
            "average_read_seconds": avg_read,
            "fastest_read_seconds": min(read_times) if read_times else 0,
            "slowest_read_seconds": max(read_times) if read_times else 0,
        }
    if tab == "clicked":
        unique = clicks.values("contact_id").distinct().count()
        total_clicks = clicks.aggregate(total=Count("id"))["total"] or 0
        button_clicks = clicks.aggregate(total=Count("click_count"))["total"] or 0
        return {
            "total_clicks": total_clicks,
            "ctr_percent": _pct(unique, delivered),
            "unique_clicks": unique,
            "button_clicks": button_clicks or total_clicks,
            "clicks_by_hour": [
                {"label": str(row["hour"])[:5] if row["hour"] else "", "value": row["value"]}
                for row in clicks.annotate(hour=TruncHour("clicked_at"))
                .values("hour")
                .annotate(value=Count("id"))
                .order_by("hour")
            ],
            "clicks_by_button": [
                {"label": row["button_name"] or "Button", "value": row["value"]}
                for row in clicks.values("button_name")
                .annotate(value=Count("id"))
                .order_by("-value")
            ],
            "clicks_by_day": [
                {"label": str(row["day"]), "value": row["value"]}
                for row in clicks.annotate(day=TruncDate("clicked_at"))
                .values("day")
                .annotate(value=Count("id"))
                .order_by("day")
            ],
        }
    if tab == "failed":
        permanent = 0
        retryable = 0
        for r in recipients.filter(status=CampaignRecipient.Status.FAILED):
            code = r.failure_code or _parse_failure_code(r.error_message)
            if _can_retry(code):
                retryable += 1
            else:
                permanent += 1
        return {
            "failed_percent": _pct(failed, audience),
            "total_failed": failed,
            "retry_available": retryable,
            "permanent_failure": permanent,
        }
    return {}


def serialize_recipient(recipient: CampaignRecipient, tab: str) -> dict:
    contact = recipient.contact
    code = recipient.failure_code or _parse_failure_code(recipient.error_message)
    base = {
        "id": str(recipient.id),
        "name": _contact_name(contact),
        "phone": contact.phone,
        "conversation_id": _conversation_id_for(contact),
        "status": recipient.status,
    }
    if tab in {"sent", "overview"}:
        return {
            **base,
            "sent_at": recipient.sent_at.isoformat() if recipient.sent_at else None,
            "channel": "WhatsApp",
        }
    if tab == "delivered":
        delay = None
        if recipient.delivered_at and recipient.sent_at:
            delay = (recipient.delivered_at - recipient.sent_at).total_seconds()
        return {
            **base,
            "sent_at": recipient.sent_at.isoformat() if recipient.sent_at else None,
            "delivered_at": recipient.delivered_at.isoformat() if recipient.delivered_at else None,
            "delivery_delay_seconds": delay,
        }
    if tab == "read":
        read_time = None
        if recipient.read_at and recipient.delivered_at:
            read_time = (recipient.read_at - recipient.delivered_at).total_seconds()
        return {
            **base,
            "sent_at": recipient.sent_at.isoformat() if recipient.sent_at else None,
            "delivered_at": recipient.delivered_at.isoformat() if recipient.delivered_at else None,
            "read_at": recipient.read_at.isoformat() if recipient.read_at else None,
            "time_to_read_seconds": read_time,
            "is_read": bool(recipient.read_at),
        }
    if tab == "failed":
        return {
            **base,
            "failed_at": recipient.updated_at.isoformat(),
            "failure_code": code,
            "failure_reason": _failure_reason(code, recipient.error_message),
            "can_retry": _can_retry(code),
        }
    return base


def serialize_click_event(event: CampaignClickEvent) -> dict:
    return {
        "id": str(event.id),
        "name": _contact_name(event.contact),
        "phone": event.contact.phone,
        "button_type": event.button_type,
        "button_name": event.button_name,
        "button_url": event.button_url,
        "clicked_at": event.clicked_at.isoformat(),
        "click_count": event.click_count,
        "conversation_id": _conversation_id_for(event.contact),
    }


def get_recipients(
    campaign: Campaign,
    tab: str,
    *,
    search: str = "",
    preset: str = "",
    date_from: str | None = None,
    date_to: str | None = None,
    read_filter: str = "",
    page: int = 1,
    page_size: int = 25,
) -> dict:
    if tab == "clicked":
        qs = CampaignClickEvent.objects.filter(campaign=campaign).select_related("contact")
        if search:
            qs = qs.filter(
                Q(contact__first_name__icontains=search)
                | Q(contact__last_name__icontains=search)
                | Q(contact__phone__icontains=search)
                | Q(button_name__icontains=search)
            )
        qs = _date_range_filter(qs, "clicked_at", preset, date_from, date_to)
        total = qs.count()
        offset = (page - 1) * page_size
        rows = [serialize_click_event(e) for e in qs.order_by("-clicked_at")[offset:offset + page_size]]
        return {"results": rows, "total": total, "page": page, "page_size": page_size}

    qs = campaign.recipients.select_related("contact")
    if tab == "sent":
        qs = qs.filter(status__in=[
            CampaignRecipient.Status.SENT,
            CampaignRecipient.Status.DELIVERED,
            CampaignRecipient.Status.READ,
            CampaignRecipient.Status.CLICKED,
            CampaignRecipient.Status.REPLIED,
        ])
        qs = _date_range_filter(qs, "sent_at", preset, date_from, date_to)
    elif tab == "delivered":
        qs = qs.filter(delivered_at__isnull=False)
        qs = _date_range_filter(qs, "delivered_at", preset, date_from, date_to)
    elif tab == "read":
        if read_filter == "not_read":
            qs = qs.filter(read_at__isnull=True, delivered_at__isnull=False)
        else:
            qs = qs.filter(read_at__isnull=False)
        qs = _date_range_filter(qs, "read_at", preset, date_from, date_to)
    elif tab == "failed":
        qs = qs.filter(status=CampaignRecipient.Status.FAILED)
        qs = _date_range_filter(qs, "updated_at", preset, date_from, date_to)

    if search:
        qs = qs.filter(
            Q(contact__first_name__icontains=search)
            | Q(contact__last_name__icontains=search)
            | Q(contact__phone__icontains=search)
        )

    total = qs.count()
    offset = (page - 1) * page_size
    rows = [serialize_recipient(r, tab) for r in qs.order_by("-updated_at")[offset:offset + page_size]]
    return {"results": rows, "total": total, "page": page, "page_size": page_size}


def _report_rows(campaign: Campaign, tab: str) -> tuple[list[str], list[list[Any]]]:
    if tab == "overview":
        overview = get_overview(campaign)
        headers = ["metric", "value"]
        rows = [[k, v] for k, v in overview["summary"].items()]
        return headers, rows
    data = get_recipients(campaign, tab, page=1, page_size=10000)
    rows = data["results"]
    if not rows:
        return [], []
    headers = list(rows[0].keys())
    return headers, [[row.get(h) for h in headers] for row in rows]


def export_report(campaign: Campaign, tab: str, fmt: str) -> tuple[bytes, str, str]:
    headers, rows = _report_rows(campaign, tab)
    safe_name = re.sub(r"[^\w\-]+", "_", campaign.name)[:40]
    filename = f"Campaign_{tab.capitalize()}_{safe_name}"

    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(rows)
        return buffer.getvalue().encode("utf-8"), f"{filename}.csv", "text/csv"

    if fmt in {"xlsx", "excel"}:
        wb = Workbook()
        ws = wb.active
        ws.title = tab.capitalize()
        ws.append(headers)
        for row in rows:
            ws.append(row)
        stream = io.BytesIO()
        wb.save(stream)
        return (
            stream.getvalue(),
            f"{filename}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # JSON fallback for PDF placeholder — frontend can print overview
    payload = {
        "campaign": campaign.name,
        "tab": tab,
        "exported_at": timezone.now().isoformat(),
        "stats": get_tab_stats(campaign, tab) if tab != "overview" else get_overview(campaign)["summary"],
        "rows": rows,
    }
    return json.dumps(payload, indent=2).encode("utf-8"), f"{filename}.json", "application/json"


def track_campaign_click(org, contact, button_id: str, button_title: str, raw_msg: dict):
    from apps.campaigns.models import CampaignClickEvent, CampaignRecipient

    recipient = (
        CampaignRecipient.objects.filter(
            organization=org,
            contact=contact,
            status__in=[
                CampaignRecipient.Status.SENT,
                CampaignRecipient.Status.DELIVERED,
                CampaignRecipient.Status.READ,
            ],
        )
        .select_related("campaign", "campaign__template")
        .order_by("-sent_at")
        .first()
    )
    if not recipient:
        return

    button_url = ""
    button_type = "quick_reply"
    template = recipient.campaign.template
    if template and template.buttons:
        for btn in template.buttons:
            if str(btn.get("text", "")).lower() == button_title.lower() or btn.get("id") == button_id:
                button_type = btn.get("type", "quick_reply")
                button_url = btn.get("url", "")
                button_title = btn.get("text", button_title)
                break

    now = timezone.now()
    event, created = CampaignClickEvent.objects.get_or_create(
        organization=org,
        campaign=recipient.campaign,
        recipient=recipient,
        contact=contact,
        button_name=button_title or button_id,
        defaults={
            "button_type": button_type,
            "button_url": button_url,
            "clicked_at": now,
            "click_count": 1,
        },
    )
    if not created:
        event.click_count += 1
        event.clicked_at = now
        event.save(update_fields=["click_count", "clicked_at", "updated_at"])

    recipient.status = CampaignRecipient.Status.CLICKED
    recipient.clicked_at = now
    recipient.save(update_fields=["status", "clicked_at", "updated_at"])

    campaign = recipient.campaign
    campaign.click_count = CampaignClickEvent.objects.filter(campaign=campaign).values("contact").distinct().count()
    campaign.save(update_fields=["click_count", "updated_at"])
