import logging
import mimetypes
import os
import tempfile
from datetime import datetime, timezone as dt_timezone

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _safe_response_json(response) -> dict:
    try:
        return response.json()
    except ValueError:
        return {"error": {"message": response.text[:500] or "Invalid response from Meta API"}}


def _format_meta_error(error) -> str:
    if isinstance(error, dict):
        nested = error.get("error") if isinstance(error.get("error"), dict) else error
        if isinstance(nested, dict):
            user_msg = nested.get("error_user_msg") or nested.get("error_user_title")
            message = nested.get("message")
            # Prefer actionable Meta user messages over the generic "unknown error" text.
            if user_msg:
                return str(user_msg)
            if message and "unknown error" not in str(message).lower():
                return str(message)
            if message:
                details = nested.get("error_data") or nested.get("error_subcode") or nested.get("fbtrace_id")
                return f"{message}" + (f" ({details})" if details else "")
            return str(nested)
        return str(error.get("message") or error)
    return str(error)

META_VERTICALS = [
    ("TRAVEL", "Travel"),
    ("HOTEL", "Hotel"),
    ("VACATION_RENTAL", "Vacation Rental"),
    ("REAL_ESTATE", "Real Estate"),
    ("RESTAURANT", "Restaurant"),
    ("RETAIL", "Shopping"),
    ("PROF_SERVICES", "Professional Services"),
    ("EDU", "Education"),
    ("HEALTH", "Healthcare"),
    ("AUTO", "Automotive"),
    ("HOME_SERVICES", "Home Services"),
    ("OTHER", "Technology"),
    ("BEAUTY", "Beauty"),
    ("FINANCE", "Finance"),
    ("GROCERY", "Grocery"),
    ("ENTERTAINMENT", "Entertainment"),
    ("NONPROFIT", "Nonprofit"),
    ("GOVT", "Government"),
    ("UNDEFINED", "Other"),
]

VERTICAL_LABELS = {code: label for code, label in META_VERTICALS}
LABEL_TO_VERTICAL = {label.lower(): code for code, label in META_VERTICALS}
LABEL_TO_VERTICAL.update({
    "shopping": "RETAIL",
    "technology": "OTHER",
    "home services": "HOME_SERVICES",
    "professional services": "PROF_SERVICES",
    "education": "EDU",
    "healthcare": "HEALTH",
    "automotive": "AUTO",
    "real estate": "REAL_ESTATE",
    "vacation rental": "VACATION_RENTAL",
})


class MetaBusinessProfileService:
    GRAPH_API = "https://graph.facebook.com/v21.0"

    def __init__(self, organization):
        self.org = organization

    @property
    def is_configured(self):
        return bool(self.org.whatsapp_phone_number_id and self.org.whatsapp_access_token)

    def _headers(self):
        return {"Authorization": f"Bearer {self.org.whatsapp_access_token}"}

    def _phone_id(self):
        return self.org.whatsapp_phone_number_id

    def get_phone_number_info(self) -> dict:
        if not self.is_configured:
            return {"error": "WhatsApp is not connected."}
        url = f"{self.GRAPH_API}/{self._phone_id()}"
        response = requests.get(
            url,
            headers=self._headers(),
            params={
                "fields": (
                    "display_phone_number,verified_name,quality_rating,"
                    "code_verification_status,platform_type,status,name_status"
                ),
            },
            timeout=30,
        )
        data = _safe_response_json(response)
        if not response.ok:
            return {"error": data}
        return data

    def get_profile(self) -> dict:
        if not self.is_configured:
            return {"error": "WhatsApp is not connected."}
        url = f"{self.GRAPH_API}/{self._phone_id()}/whatsapp_business_profile"
        response = requests.get(
            url,
            headers=self._headers(),
            params={
                "fields": "about,address,description,email,profile_picture_url,websites,vertical",
            },
            timeout=30,
        )
        data = _safe_response_json(response)
        if not response.ok:
            return {"error": data}
        profile = (data.get("data") or [{}])[0] if isinstance(data.get("data"), list) else data
        return profile

    def fetch_combined(self) -> dict:
        phone = self.get_phone_number_info()
        profile = self.get_profile()
        if phone.get("error"):
            return phone
        if profile.get("error"):
            return profile

        cached = (self.org.settings or {}).get("whatsapp_profile", {})
        vertical = profile.get("vertical") or cached.get("vertical") or ""
        websites = profile.get("websites") or cached.get("websites") or []
        if isinstance(websites, str):
            websites = [websites]

        return {
            "business_name": phone.get("verified_name") or self.org.name,
            "phone_number": phone.get("display_phone_number", ""),
            "verified_name": phone.get("verified_name", ""),
            "quality_rating": phone.get("quality_rating", ""),
            "name_status": phone.get("name_status", ""),
            "phone_status": phone.get("status", ""),
            "code_verification_status": phone.get("code_verification_status", ""),
            "description": profile.get("description") or profile.get("about") or "",
            "about": profile.get("about", ""),
            "address": profile.get("address", ""),
            "email": profile.get("email", ""),
            "websites": websites[:2],
            "vertical": vertical,
            "vertical_label": VERTICAL_LABELS.get(vertical, vertical.replace("_", " ").title()),
            "profile_picture_url": profile.get("profile_picture_url", ""),
            "business_hours": cached.get("business_hours", {}),
            "cover_image_url": cached.get("cover_image_url", ""),
            "last_synced_at": cached.get("synced_at"),
            "can_edit_name": phone.get("name_status") not in {"APPROVED"},
        }

    def update_profile(self, payload: dict, logo_path: str | None = None) -> dict:
        if not self.is_configured:
            return {"error": "WhatsApp is not connected."}

        # Meta rejects empty strings for several profile fields (especially with picture updates).
        body = {"messaging_product": "whatsapp"}
        description = str(payload.get("description") or "").strip()
        address = str(payload.get("address") or "").strip()
        email = str(payload.get("email") or "").strip()
        vertical = str(payload.get("vertical") or "").strip()
        websites = payload.get("websites")

        if description:
            body["description"] = description[:512]
            body["about"] = description[:139]
        if address:
            body["address"] = address[:256]
        if email:
            body["email"] = email[:128]
        if websites is not None:
            sites = [str(s).strip() for s in websites if s and str(s).strip()][:2]
            if sites:
                body["websites"] = sites
        if vertical:
            body["vertical"] = vertical

        prepared_logo = None
        try:
            if logo_path:
                try:
                    prepared_logo = self._prepare_profile_picture(logo_path)
                except ValueError as exc:
                    return {"error": str(exc)}
                except Exception as exc:
                    logger.exception("Failed preparing profile picture")
                    return {"error": f"Could not process profile image: {exc}"}
                handle_result = self._upload_profile_picture_handle(prepared_logo)
                if handle_result.get("error"):
                    return handle_result
                body["profile_picture_handle"] = handle_result["handle"]

            if len(body) == 1:
                return {"error": "No profile fields to update."}

            url = f"{self.GRAPH_API}/{self._phone_id()}/whatsapp_business_profile"
            logger.info(
                "Updating Meta business profile org=%s fields=%s",
                self.org.id,
                sorted(k for k in body.keys() if k != "messaging_product"),
            )
            response = requests.post(url, headers=self._headers(), json=body, timeout=60)
            data = _safe_response_json(response)
            if not response.ok:
                logger.warning("Meta business profile update failed: %s", data)
                return {"error": data}
            return data
        finally:
            if prepared_logo and prepared_logo != logo_path:
                try:
                    os.unlink(prepared_logo)
                except OSError:
                    pass

    def _upload_profile_picture_handle(self, file_path: str) -> dict:
        from apps.campaigns.meta import MetaTemplateService

        return MetaTemplateService(self.org).upload_media_handle(file_path)

    @staticmethod
    def _prepare_profile_picture(file_path: str) -> str:
        """Normalize logo to a square JPEG — Meta profile pictures are picky about format."""
        from PIL import Image

        with Image.open(file_path) as image:
            image = image.convert("RGB")
            width, height = image.size
            if width < 192 or height < 192:
                raise ValueError("Profile image must be at least 192×192 pixels.")
            side = min(width, height)
            left = (width - side) // 2
            top = (height - side) // 2
            image = image.crop((left, top, left + side, top + side))
            if side > 640:
                image = image.resize((640, 640))

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp.close()
            image.save(tmp.name, format="JPEG", quality=90, optimize=True)
            return tmp.name

    def sync_and_cache(self) -> dict:
        combined = self.fetch_combined()
        if combined.get("error"):
            return combined

        now = timezone.now().isoformat()
        settings_data = dict(self.org.settings or {})
        settings_data["whatsapp_profile"] = {
            **combined,
            "synced_at": now,
        }
        self.org.settings = settings_data
        self.org.save(update_fields=["settings", "updated_at"])
        combined["last_synced_at"] = now
        return combined

    def append_audit(self, user, action: str, changes: dict | None = None):
        settings_data = dict(self.org.settings or {})
        audit = list(settings_data.get("business_profile_audit", []))
        audit.insert(0, {
            "at": timezone.now().isoformat(),
            "user": user.get_full_name() or user.email or str(user.id),
            "action": action,
            "changes": changes or {},
        })
        settings_data["business_profile_audit"] = audit[:100]
        self.org.settings = settings_data
        self.org.save(update_fields=["settings", "updated_at"])

    def get_audit_log(self) -> list:
        return list((self.org.settings or {}).get("business_profile_audit", []))

    def get_health(self) -> dict:
        phone = self.get_phone_number_info()
        settings_data = self.org.settings or {}
        webhook_url = (
            settings_data.get("whatsapp_webhook", {}).get("webhook_url")
            or settings_data.get("webhook_url")
            or getattr(settings, "WHATSAPP_WEBHOOK_URL", "")
        )
        subscription = settings_data.get("webhook_subscription", {})
        if subscription.get("ok") is True:
            webhook_status = "connected"
        elif webhook_url:
            webhook_status = "failed" if subscription.get("ok") is False else "configured"
        else:
            webhook_status = "not_configured"

        synced_at = settings_data.get("whatsapp_profile", {}).get("synced_at")
        return {
            "api_status": "connected" if self.is_configured else "not_connected",
            "webhook_status": webhook_status,
            "quality_rating": phone.get("quality_rating", "") if not phone.get("error") else "",
            "phone_status": phone.get("status", "") if not phone.get("error") else "",
            "code_verification_status": phone.get("code_verification_status", "") if not phone.get("error") else "",
            "last_sync": synced_at,
        }

    @staticmethod
    def validate_payload(data: dict) -> list[str]:
        errors = []
        desc = data.get("description", "")
        if desc and len(desc) > 256:
            errors.append("Description must be 256 characters or fewer.")
        email = data.get("email", "")
        if email and "@" not in email:
            errors.append("Enter a valid email address.")
        for site in data.get("websites") or []:
            if site and not str(site).startswith(("http://", "https://")):
                errors.append(f"Invalid website URL: {site}")
        vertical = data.get("vertical", "")
        if vertical and vertical not in VERTICAL_LABELS:
            errors.append("Select a valid business category.")
        return errors

    @staticmethod
    def save_uploaded_logo(uploaded_file) -> str:
        suffix = os.path.splitext(uploaded_file.name)[1].lower() or ".jpg"
        content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
        allowed_types = {"image/jpeg", "image/jpg", "image/png"}
        if suffix not in {".jpg", ".jpeg", ".png"} and content_type not in allowed_types:
            raise ValueError("Logo must be JPG or PNG.")
        if uploaded_file.size > 5 * 1024 * 1024:
            raise ValueError("Logo must be 5 MB or smaller.")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix if suffix in {".jpg", ".jpeg", ".png"} else ".jpg")
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        tmp.close()
        return tmp.name
