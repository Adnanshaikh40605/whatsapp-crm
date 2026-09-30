"""DriverOnHire WhatsApp driver-booking conversation.

Collects the same fields as the website. Does not calculate price.
Confirmed requests are saved as a CRM lead (source=whatsapp). If
DRIVERONHIRE_BOOKING_API_URL is set, that existing API is called and its
booking id is shown. No second pricing engine or booking database.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

SESSION_KEY = "doh_booking"
SESSION_MINUTES = 45

TRIGGERS = {"hi", "hello", "hey", "start", "book", "book driver", "menu"}

CARS = [
    ("hatchback", "Hatchback"),
    ("sedan", "Sedan"),
    ("suv", "SUV"),
    ("luxury", "Luxury"),
    ("sedan_luxury", "Sedan Luxury"),
    ("suv_luxury", "SUV Luxury"),
]
TRANSMISSIONS = [("automatic", "Automatic"), ("manual", "Manual")]
DUTY = [("2", "2 Hours"), ("4", "4 Hours"), ("8", "8 Hours")]


def is_driveronhire_org(org) -> bool:
    name = (getattr(org, "name", "") or "").lower().replace(" ", "")
    return "driveronhire" in name or name in {"doh", "driveronhire"}


def handle_booking_message(org, conversation, contact, content: str, button_id: str = "", raw: dict | None = None):
    if not is_driveronhire_org(org):
        return []
    session = dict((conversation.metadata or {}).get(SESSION_KEY) or {})
    if _expired(session):
        session = {}
        _save(conversation, session)
        if not _is_trigger(content, button_id):
            return [_buttons(
                "Your previous booking session has expired.\nWould you like to start again?",
                [("menu_book", "Start Booking"), ("menu_home", "Main Menu")],
            )]

    if session.get("human"):
        if _is_trigger(content, button_id) or button_id == "menu_home":
            session = {}
            _save(conversation, session)
        else:
            return []

    text = (content or "").strip()
    low = text.lower()
    choice = button_id or ""

    if choice in {"menu_support", "support"} or low in {"talk to support", "support", "agent"}:
        session["human"] = True
        _save(conversation, session)
        return [{"type": "text", "body": "Connecting you to a DriverOnHire agent. Automated booking is paused until you send Main Menu or Hi."}]

    if low in {"cancel", "stop"} or choice == "cancel_booking":
        _save(conversation, {})
        return [{"type": "text", "body": "Booking cancelled. Send Hi whenever you want to start again."}]

    if low in {"restart", "start again", "main menu", "menu"} or choice == "menu_home" or _is_trigger(text, choice):
        if choice in {"menu_bookings",} or low == "my booking":
            return _my_bookings(org, contact)
        session = {"step": "menu", "data": {}, "history": []}
        _save(conversation, session)
        return [_main_menu()]

    if choice == "menu_bookings" or low == "my booking":
        return _my_bookings(org, contact)

    if not session.get("step"):
        if button_id == "menu_book":
            session = {"step": "service", "data": {}, "history": ["menu"]}
            _save(conversation, session)
            return _prompt(session)
        if button_id == "menu_home":
            session = {"step": "menu", "data": {}, "history": []}
            _save(conversation, session)
            return [_main_menu()]
        return []

    if low in {"back", "go back"} or choice == "back":
        history = session.get("history") or []
        if history:
            session["step"] = history.pop()
            session["history"] = history
            _save(conversation, session)
            return _prompt(session)
        session["step"] = "menu"
        _save(conversation, session)
        return [_main_menu()]

    return _advance(org, conversation, contact, session, text, choice, raw or {})


def _advance(org, conversation, contact, session, text, choice, raw):
    step = session.get("step") or "menu"
    data = session.setdefault("data", {})

    if step == "menu":
        if choice == "menu_book" or text.lower() in {"book a driver", "book"}:
            _go(session, "service")
        else:
            _save(conversation, session)
            return [_main_menu()]
    elif step == "service":
        mapping = {
            "svc_local": ("local", "local_trip"),
            "svc_out": ("outstation", "pickup"),
            "svc_drop": ("outstation_drop", "pickup"),
            "svc_perm": ("permanent", "name"),
        }
        picked = mapping.get(choice)
        if not picked:
            _save(conversation, session)
            return _prompt(session)
        data["booking_type"] = picked[0]
        _go(session, picked[1])
    elif step == "local_trip":
        if choice == "trip_round":
            data["trip_type"] = "round_trip"
        elif choice == "trip_one":
            data["trip_type"] = "one_way"
        else:
            _save(conversation, session)
            return _prompt(session)
        _go(session, "pickup")
    elif step == "pickup":
        loc = _location_text(text, raw)
        if not loc:
            _save(conversation, session)
            return [{"type": "text", "body": "Please type a pickup location or share your location pin."}]
        data["pickup_location"] = loc
        nxt = "visiting" if data.get("trip_type") != "one_way" and data.get("booking_type") != "outstation_drop" else "drop"
        if data.get("booking_type") == "outstation":
            nxt = "visiting"
        _go(session, nxt)
    elif step in {"visiting", "drop"}:
        loc = _location_text(text, raw)
        if not loc:
            _save(conversation, session)
            return [{"type": "text", "body": "Please enter the location."}]
        data["visiting_location" if step == "visiting" else "drop_location"] = loc
        if data.get("booking_type") == "local":
            _go(session, "duty")
        elif data.get("booking_type") == "outstation_drop":
            _go(session, "name")
        else:
            _go(session, "start_date")
    elif step == "duty":
        hours = choice.replace("duty_", "") if choice.startswith("duty_") else ""
        if hours not in {"2", "4", "8"}:
            _save(conversation, session)
            return _prompt(session)
        data["duty_hours"] = int(hours)
        _go(session, "date")
    elif step == "date":
        parsed = _parse_date(text)
        if not parsed:
            _save(conversation, session)
            return [{"type": "text", "body": "Enter a valid date (DD/MM/YYYY or YYYY-MM-DD), not in the past."}]
        data["booking_date"] = parsed
        _go(session, "time")
    elif step == "start_date":
        parsed = _parse_date(text)
        if not parsed:
            _save(conversation, session)
            return [{"type": "text", "body": "Enter the start date as DD/MM/YYYY."}]
        data["start_date"] = parsed
        _go(session, "end_date")
    elif step == "end_date":
        parsed = _parse_date(text)
        if not parsed or parsed < data.get("start_date", parsed):
            _save(conversation, session)
            return [{"type": "text", "body": "Enter an end date on or after the start date (DD/MM/YYYY)."}]
        data["end_date"] = parsed
        _go(session, "time")
    elif step == "time":
        parsed = _parse_time(text)
        if not parsed:
            _save(conversation, session)
            return [{"type": "text", "body": "Enter time like 08:00 AM or 14:30."}]
        data["booking_time"] = parsed
        _go(session, "car")
    elif step == "car":
        car = next((c for c in CARS if c[0] == choice or c[1].lower() == text.lower()), None)
        if not car:
            _save(conversation, session)
            return _prompt(session)
        data["car_type"] = car[0]
        data["car_label"] = car[1]
        _go(session, "transmission")
    elif step == "transmission":
        tx = next((t for t in TRANSMISSIONS if t[0] == choice or t[1].lower() == text.lower()), None)
        if not tx:
            _save(conversation, session)
            return _prompt(session)
        data["transmission_type"] = tx[0]
        data["transmission_label"] = tx[1]
        _go(session, "summary")
    elif step == "name":
        if len(text) < 2:
            _save(conversation, session)
            return [{"type": "text", "body": "Please enter your full name."}]
        data["customer_name"] = text
        data["mobile"] = data.get("mobile") or contact.phone
        _go(session, "mobile_confirm")
    elif step == "mobile_confirm":
        if choice == "use_number":
            data["mobile"] = contact.phone
            _go(session, "email" if data.get("booking_type") == "permanent" else "start_date")
        elif choice == "change_number":
            _go(session, "mobile")
        else:
            _save(conversation, session)
            return _prompt(session)
    elif step == "mobile":
        digits = re.sub(r"\D", "", text)
        if len(digits) < 10:
            _save(conversation, session)
            return [{"type": "text", "body": "Enter a valid mobile number (at least 10 digits)."}]
        data["mobile"] = digits
        _go(session, "email" if data.get("booking_type") == "permanent" else "start_date")
    elif step == "email":
        if text.lower() in {"skip", "no"}:
            data["email"] = ""
        elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text):
            _save(conversation, session)
            return [{"type": "text", "body": "Enter a valid email, or send Skip."}]
        else:
            data["email"] = text
        _go(session, "requirement")
    elif step == "requirement":
        data["message"] = text
        _go(session, "summary")
    elif step == "summary":
        if choice == "confirm":
            return _confirm(org, conversation, contact, session)
        if choice == "change":
            _go(session, "change")
        else:
            _save(conversation, session)
            return _prompt(session)
    elif step == "change":
        field_map = {
            "chg_pickup": "pickup",
            "chg_dest": "visiting" if data.get("visiting_location") else "drop",
            "chg_duty": "duty",
            "chg_date": "date" if data.get("booking_type") == "local" else "start_date",
            "chg_time": "time",
            "chg_car": "car",
            "chg_tx": "transmission",
        }
        if choice == "back_summary":
            _go(session, "summary", remember=False)
        elif choice in field_map:
            session["return_to_summary"] = True
            _go(session, field_map[choice])
        else:
            _save(conversation, session)
            return _prompt(session)
    else:
        session["step"] = "menu"

    if session.get("return_to_summary") and session.get("step") not in {
        "pickup", "visiting", "drop", "duty", "date", "time", "start_date", "end_date", "car", "transmission",
    }:
        session["return_to_summary"] = False
        session["step"] = "summary"

    _save(conversation, session)
    return _prompt(session)


def _confirm(org, conversation, contact, session):
    if session.get("request_id"):
        _save(conversation, session)
        return [{"type": "text", "body": f"This request is already saved: {session['request_id']}"}]
    data = session.get("data") or {}
    from apps.crm.models import Lead, PipelineStage

    stage = PipelineStage.objects.filter(organization=org).order_by("order").first()
    title = f"WhatsApp {data.get('booking_type', 'booking')}"
    lead = Lead.objects.create(
        organization=org,
        contact=contact,
        title=title,
        stage=stage,
        source="whatsapp",
        notes=_summary_text(data, contact),
        custom_fields={"flow": "driver_booking", "channel": "whatsapp", **data},
    )
    request_id = f"DOH-WA-{str(lead.id).split('-')[0].upper()}"
    api_id = _call_booking_api(contact, data, request_id)
    lead.custom_fields = {**lead.custom_fields, "request_id": request_id, "external_booking_id": api_id or ""}
    lead.save(update_fields=["custom_fields", "updated_at"])
    session["request_id"] = api_id or request_id
    session["step"] = "done"
    _save(conversation, session)
    ref = api_id or request_id
    return [_buttons(
        "Booking request received.\n\n"
        f"Reference:\n{ref}\n\n"
        f"{_summary_text(data, contact)}\n\n"
        "Our team will process this and update you on WhatsApp.",
        [("menu_bookings", "My Booking"), ("menu_home", "Main Menu"), ("menu_support", "Talk to Support")],
    )]


def _call_booking_api(contact, data, request_id):
    url = getattr(settings, "DRIVERONHIRE_BOOKING_API_URL", "") or ""
    if not url:
        return ""
    headers = {"Content-Type": "application/json"}
    token = getattr(settings, "DRIVERONHIRE_BOOKING_API_TOKEN", "") or ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.post(
            url,
            json={"idempotency_key": request_id, "phone": contact.phone, "source": "whatsapp", **data},
            headers=headers,
            timeout=20,
        )
        body = response.json() if response.content else {}
        if not response.ok:
            logger.warning("DriverOnHire booking API failed: %s", body)
            return ""
        return str(body.get("booking_id") or body.get("id") or "")
    except requests.RequestException as exc:
        logger.warning("DriverOnHire booking API error: %s", exc)
        return ""


def _my_bookings(org, contact):
    from apps.crm.models import Lead

    leads = list(
        Lead.objects.filter(organization=org, contact=contact, source="whatsapp").order_by("-created_at")[:8]
    )
    if not leads:
        return [_buttons("No WhatsApp booking requests yet.", [("menu_book", "Book a Driver"), ("menu_home", "Main Menu")])]
    lines = ["Your recent WhatsApp booking requests:\n"]
    for lead in leads:
        fields = lead.custom_fields or {}
        ref = fields.get("external_booking_id") or fields.get("request_id") or str(lead.id)[:8]
        when = fields.get("booking_date") or fields.get("start_date") or lead.created_at.date().isoformat()
        lines.append(f"• {ref}\n  {when} • {fields.get('car_label') or fields.get('booking_type') or lead.title}")
    return [_buttons("\n".join(lines), [("menu_home", "Main Menu"), ("menu_book", "Book a Driver")])]


def _prompt(session):
    step = session.get("step")
    data = session.get("data") or {}
    phone = data.get("mobile") or ""
    if step == "menu":
        return [_main_menu()]
    if step == "service":
        return [{
            "type": "list",
            "body": "Please select your driver service:",
            "button": "Services",
            "sections": [{"title": "Services", "rows": [
                {"id": "svc_local", "title": "Local Mumbai", "description": ""},
                {"id": "svc_out", "title": "Outstation", "description": ""},
                {"id": "svc_drop", "title": "Outstation Drop", "description": ""},
                {"id": "svc_perm", "title": "Permanent Driver", "description": ""},
            ]}],
        }]
    if step == "local_trip":
        return [_buttons("Local Mumbai Driver\nPlease select your trip type:", [("trip_round", "Round Trip"), ("trip_one", "One Way")])]
    if step == "pickup":
        return [{"type": "text", "body": "Please enter your pickup location, or share your WhatsApp location pin."}]
    if step == "visiting":
        return [{"type": "text", "body": "Where are you travelling to?"}]
    if step == "drop":
        return [{"type": "text", "body": "Please enter the drop location."}]
    if step == "duty":
        return [_buttons("Select duty hours:", [("duty_2", "2 Hours"), ("duty_4", "4 Hours"), ("duty_8", "8 Hours")])]
    if step == "date":
        return [{"type": "text", "body": "Please enter your booking date (DD/MM/YYYY)."}]
    if step == "start_date":
        return [{"type": "text", "body": "Please enter the start date (DD/MM/YYYY)."}]
    if step == "end_date":
        return [{"type": "text", "body": "Please enter the end date (DD/MM/YYYY)."}]
    if step == "time":
        return [{"type": "text", "body": "Please enter the reporting time (example 08:00 AM)."}]
    if step == "car":
        return [{
            "type": "list",
            "body": "Select car type:",
            "button": "Car type",
            "sections": [{"title": "Cars", "rows": [
                {"id": key, "title": label[:24], "description": ""} for key, label in CARS
            ]}],
        }]
    if step == "transmission":
        return [_buttons("Select transmission:", [("automatic", "Automatic"), ("manual", "Manual")])]
    if step == "name":
        return [{"type": "text", "body": "Please enter your name."}]
    if step == "mobile_confirm":
        shown = phone or "your WhatsApp number"
        return [_buttons(
            f"We will use this mobile number:\n{shown}",
            [("use_number", "Use This Number"), ("change_number", "Change Number")],
        )]
    if step == "mobile":
        return [{"type": "text", "body": "Enter the mobile number to use."}]
    if step == "email":
        return [{"type": "text", "body": "Enter your email, or send Skip."}]
    if step == "requirement":
        return [{"type": "text", "body": "Tell us your permanent driver requirement."}]
    if step == "summary":
        return [_buttons(
            "Please review your booking:\n\n" + _summary_text(data, None) + "\n\nPlease confirm your details.",
            [("confirm", "Confirm Booking"), ("change", "Change Details"), ("cancel_booking", "Cancel")],
        )]
    if step == "change":
        return [{
            "type": "list",
            "body": "What would you like to change?",
            "button": "Change",
            "sections": [{"title": "Fields", "rows": [
                {"id": "chg_pickup", "title": "Pickup", "description": ""},
                {"id": "chg_dest", "title": "Destination", "description": ""},
                {"id": "chg_duty", "title": "Duty Hours", "description": ""},
                {"id": "chg_date", "title": "Date", "description": ""},
                {"id": "chg_time", "title": "Time", "description": ""},
                {"id": "chg_car", "title": "Car Type", "description": ""},
                {"id": "chg_tx", "title": "Transmission", "description": ""},
                {"id": "back_summary", "title": "Back to Summary", "description": ""},
            ]}],
        }]
    return [_main_menu()]


def _main_menu():
    return {
        "type": "buttons",
        "body": "DriverOnHire\nWelcome! How can we help you today?",
        "buttons": [
            {"id": "menu_book", "title": "Book a Driver"},
            {"id": "menu_bookings", "title": "My Booking"},
            {"id": "menu_support", "title": "Talk to Support"},
        ],
    }


def _buttons(body, pairs):
    return {"type": "buttons", "body": body, "buttons": [{"id": i, "title": t} for i, t in pairs[:3]]}


def _summary_text(data, contact) -> str:
    lines = [
        f"Service: {(data.get('booking_type') or '').replace('_', ' ').title()}",
    ]
    if data.get("trip_type"):
        lines.append(f"Trip: {data['trip_type'].replace('_', ' ').title()}")
    if data.get("pickup_location"):
        lines.append(f"Pickup: {data['pickup_location']}")
    if data.get("visiting_location"):
        lines.append(f"Visiting: {data['visiting_location']}")
    if data.get("drop_location"):
        lines.append(f"Drop: {data['drop_location']}")
    if data.get("duty_hours"):
        lines.append(f"Duty: {data['duty_hours']} Hours")
    if data.get("booking_date"):
        lines.append(f"Date: {data['booking_date']}")
    if data.get("start_date"):
        lines.append(f"Start: {data['start_date']}")
    if data.get("end_date"):
        lines.append(f"End: {data['end_date']}")
    if data.get("booking_time"):
        lines.append(f"Time: {data['booking_time']}")
    if data.get("car_label"):
        lines.append(f"Car: {data['car_label']}")
    if data.get("transmission_label"):
        lines.append(f"Transmission: {data['transmission_label']}")
    if data.get("customer_name"):
        lines.append(f"Name: {data['customer_name']}")
    mobile = data.get("mobile") or (getattr(contact, "phone", "") if contact else "")
    if mobile:
        lines.append(f"Mobile: {mobile}")
    if data.get("email"):
        lines.append(f"Email: {data['email']}")
    if data.get("message"):
        lines.append(f"Requirement: {data['message']}")
    return "\n".join(lines)


def _go(session, step, remember=True):
    if remember and session.get("step") and session.get("step") != step:
        session.setdefault("history", []).append(session["step"])
    session["step"] = step


def _save(conversation, session):
    session["updated_at"] = timezone.now().isoformat()
    conversation.metadata = {**(conversation.metadata or {}), SESSION_KEY: session}
    conversation.save(update_fields=["metadata", "updated_at"])


def _expired(session) -> bool:
    raw = session.get("updated_at")
    if not raw or not session.get("step"):
        return False
    try:
        stamp = datetime.fromisoformat(raw)
        if timezone.is_naive(stamp):
            stamp = timezone.make_aware(stamp, timezone.get_current_timezone())
    except ValueError:
        return False
    return timezone.now() - stamp > timedelta(minutes=SESSION_MINUTES)


def _is_trigger(text: str, button_id: str) -> bool:
    return (text or "").strip().lower() in TRIGGERS


def _location_text(text: str, raw: dict) -> str:
    if raw.get("type") == "location":
        loc = raw.get("location") or {}
        label = loc.get("name") or loc.get("address")
        if label:
            return str(label)[:255]
        if loc.get("latitude") is not None:
            return f"{loc.get('latitude')}, {loc.get('longitude')}"
    cleaned = re.sub(r"^\[Location\]\s*", "", text or "").strip()
    return cleaned[:255]


def _parse_date(text: str) -> str:
    text = (text or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            day = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if day < timezone.localdate():
            return ""
        return day.isoformat()
    return ""


def _parse_time(text: str) -> str:
    raw = (text or "").strip().upper().replace(".", ":")
    for fmt in ("%I:%M %p", "%I %p", "%H:%M", "%H%M"):
        try:
            return datetime.strptime(raw, fmt).strftime("%I:%M %p")
        except ValueError:
            continue
    return ""
