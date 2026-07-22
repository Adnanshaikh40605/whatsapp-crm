import logging
import mimetypes
import os

import requests
from django.conf import settings
from django.utils import timezone

from apps.campaigns.models import MediaAsset, WhatsAppTemplate

logger = logging.getLogger(__name__)


def _safe_response_json(response) -> dict:
    try:
        return response.json()
    except ValueError:
        return {"error": {"message": response.text[:500] or "Invalid response from Meta API"}}


def format_meta_template_error(error) -> str:
    """Turn Meta Graph API error payloads into a clear user-facing string."""
    if isinstance(error, dict):
        nested = error.get("error") if isinstance(error.get("error"), dict) else error
        if isinstance(nested, dict):
            user_msg = nested.get("error_user_msg") or nested.get("error_user_title")
            message = nested.get("message")
            parts = []
            if user_msg:
                parts.append(str(user_msg))
            elif message:
                parts.append(str(message))
            error_data = nested.get("error_data")
            if isinstance(error_data, dict):
                details = error_data.get("details") or error_data.get("blame_field_specs")
                if details:
                    parts.append(str(details))
            elif error_data:
                parts.append(str(error_data))
            if parts:
                return " — ".join(parts)
            return str(nested)
        return str(error.get("message") or error)
    return str(error)


class MetaTemplateService:
    GRAPH_API = "https://graph.facebook.com/v21.0"

    def __init__(self, organization):
        self.org = organization

    @property
    def is_configured(self):
        return bool(self.org.whatsapp_business_account_id and self.org.whatsapp_access_token)

    def _headers(self):
        return {"Authorization": f"Bearer {self.org.whatsapp_access_token}"}

    def create_template(self, template: WhatsAppTemplate) -> dict:
        if not self.is_configured:
            return {"error": "WhatsApp Business Account is not connected."}

        payload = self._build_payload(template)
        url = f"{self.GRAPH_API}/{self.org.whatsapp_business_account_id}/message_templates"
        response = requests.post(url, headers=self._headers(), json=payload, timeout=60)
        data = response.json()
        if not response.ok:
            logger.warning("Meta template create failed: %s", data)
            return {"error": data}
        self._apply_meta_response(template, data)
        return data

    def sync_templates(self) -> dict:
        if not self.is_configured:
            return {"error": "WhatsApp Business Account is not connected."}

        items: list[dict] = []
        url = f"{self.GRAPH_API}/{self.org.whatsapp_business_account_id}/message_templates"
        params = {
            "fields": "id,name,status,language,category,components,quality_score,rejected_reason",
            "limit": 100,
        }

        # Page through Meta results so sync is complete, not just the first 100.
        while url:
            response = requests.get(url, headers=self._headers(), params=params, timeout=30)
            data = response.json()
            if not response.ok:
                logger.warning("Meta template sync failed: %s", data)
                return {"error": data}
            items.extend(data.get("data") or [])
            next_url = (data.get("paging") or {}).get("next")
            url = next_url
            params = None  # next URL already contains query params

        synced = 0
        seen_keys: set[tuple[str, str]] = set()
        seen_meta_ids: set[str] = set()

        for item in items:
            name = (item.get("name") or "").strip()
            language = item.get("language") or "en_US"
            if not name:
                continue
            seen_keys.add((name, language))
            meta_id = str(item.get("id") or "").strip()
            if meta_id:
                seen_meta_ids.add(meta_id)

            defaults = self._defaults_from_meta(item)
            WhatsAppTemplate.objects.update_or_create(
                organization=self.org,
                name=name,
                language=language,
                defaults=defaults,
            )
            synced += 1

        # Remove CRM copies that Meta no longer returns.
        # Keep pure local drafts (no Meta ID) so unfinished work is not wiped.
        removed = 0
        local_qs = WhatsAppTemplate.objects.filter(organization=self.org).exclude(
            whatsapp_template_id=""
        )
        for template in local_qs:
            key = (template.name, template.language)
            meta_id = str(template.whatsapp_template_id or "").strip()
            still_on_meta = (meta_id and meta_id in seen_meta_ids) or key in seen_keys
            if not still_on_meta:
                template.delete()
                removed += 1

        return {
            "synced_count": synced,
            "removed_count": removed,
            "raw": {"count": len(items)},
        }

    def refresh_template(self, template: WhatsAppTemplate) -> dict:
        result = self.sync_templates()
        template.refresh_from_db()
        return result

    def upload_media_handle(self, file_path: str) -> dict:
        """Upload media via Meta resumable upload API; returns header_handle for templates."""
        if not os.path.isfile(file_path):
            return {"error": f"File not found: {file_path}"}

        app_id = getattr(settings, "META_APP_ID", "") or self._resolve_app_id()
        if not app_id:
            return {"error": "META_APP_ID is not configured and could not be resolved from token."}

        file_size = os.path.getsize(file_path)
        mime_type = mimetypes.guess_type(file_path)[0] or "image/jpeg"
        file_type = mime_type

        session_url = f"{self.GRAPH_API}/{app_id}/uploads"
        session_resp = requests.post(
            session_url,
            headers=self._headers(),
            params={
                "file_length": file_size,
                "file_type": file_type,
                "file_name": os.path.basename(file_path),
            },
            timeout=30,
        )
        session_data = _safe_response_json(session_resp)
        if not session_resp.ok:
            return {"error": session_data}

        upload_session_id = session_data.get("id", "")
        if not upload_session_id:
            return {"error": session_data}

        with open(file_path, "rb") as handle:
            upload_resp = requests.post(
                f"{self.GRAPH_API}/{upload_session_id}",
                headers={
                    **self._headers(),
                    "file_offset": "0",
                    "Content-Type": "application/octet-stream",
                },
                data=handle.read(),
                timeout=120,
            )
        upload_data = _safe_response_json(upload_resp)
        if not upload_resp.ok:
            return {"error": upload_data}

        handle_value = upload_data.get("h")
        if not handle_value:
            return {"error": upload_data}
        return {"handle": handle_value}

    def attach_header_media(self, template: WhatsAppTemplate, file_path: str) -> dict:
        result = self.upload_media_handle(file_path)
        if result.get("error"):
            return result

        header = dict(template.header or {})
        header["format"] = header.get("format", "IMAGE").upper()
        header["type"] = "HEADER"
        header["example"] = {"header_handle": [result["handle"]]}
        template.header = header

        components = list(template.components or [])
        replaced = False
        for idx, component in enumerate(components):
            if component.get("type") == "HEADER":
                components[idx] = {
                    "type": "HEADER",
                    "format": header["format"],
                    "example": header["example"],
                }
                replaced = True
                break
        if not replaced:
            components.insert(0, {
                "type": "HEADER",
                "format": header["format"],
                "example": header["example"],
            })

        template.components = components
        template.save(update_fields=["header", "components", "updated_at"])
        return result

    def _resolve_app_id(self) -> str:
        token = self.org.whatsapp_access_token
        if not token:
            return ""
        response = requests.get(
            f"{self.GRAPH_API}/debug_token",
            params={"input_token": token, "access_token": token},
            timeout=15,
        )
        data = response.json()
        return str(data.get("data", {}).get("app_id", ""))

    def _build_payload(self, template: WhatsAppTemplate) -> dict:
        raw_components = template.components or self._components_from_legacy_fields(template)
        components = self._normalize_components_for_meta(raw_components, template)
        return {
            "name": template.name,
            "language": template.language,
            "category": template.category.upper(),
            "components": components,
        }

    def _normalize_components_for_meta(
        self,
        components: list[dict],
        template: WhatsAppTemplate,
    ) -> list[dict]:
        normalized = []
        variables = template.variables or []

        for component in components:
            ctype = (component.get("type") or "").upper()
            if ctype == "HEADER":
                header = {"type": "HEADER", "format": (component.get("format") or "TEXT").upper()}
                if header["format"] == "TEXT" and component.get("text"):
                    header["text"] = component["text"]
                if component.get("example"):
                    header["example"] = component["example"]
                elif template.media_asset and template.media_asset.meta_media_id:
                    header["example"] = {"header_handle": [template.media_asset.meta_media_id]}
                normalized.append(header)
                continue

            if ctype == "BODY":
                if template.category == WhatsAppTemplate.Category.AUTHENTICATION:
                    normalized.append({"type": "BODY", "add_security_recommendation": True})
                    continue

                body = {"type": "BODY", "text": component.get("text") or template.body}
                example = component.get("example")
                if not example and variables:
                    body["example"] = {"body_text": [variables]}
                elif example:
                    body["example"] = example
                normalized.append(body)
                continue

            if ctype == "FOOTER":
                normalized.append({"type": "FOOTER", "text": component.get("text") or template.footer})
                continue

            if ctype == "BUTTONS":
                buttons = []
                for btn in component.get("buttons", []):
                    buttons.append(self._normalize_button(btn, template))
                if buttons:
                    normalized.append({"type": "BUTTONS", "buttons": buttons})
                continue

            normalized.append(component)
        return normalized

    def _normalize_button(self, btn: dict, template: WhatsAppTemplate) -> dict:
        btn_type = (btn.get("type") or "").upper()
        text = btn.get("text", "")

        if btn_type in {"URL", "WEBSITE"}:
            url = btn.get("url") or btn.get("value", "")
            normalized = {"type": "URL", "text": text, "url": url}
            example = btn.get("example")
            if example:
                normalized["example"] = example if isinstance(example, list) else [example]
            elif url:
                normalized["example"] = [url]
            return normalized

        if btn_type in {"PHONE_NUMBER", "PHONE"}:
            return {
                "type": "PHONE_NUMBER",
                "text": text,
                "phone_number": btn.get("phone_number") or btn.get("value", ""),
            }

        if btn_type == "COPY_CODE":
            return {
                "type": "COPY_CODE",
                "text": text or "Copy code",
                "example": btn.get("example") or btn.get("value") or (template.variables or ["123456"])[0],
            }

        if btn_type == "OTP":
            return {
                "type": "OTP",
                "otp_type": btn.get("otp_type", "COPY_CODE"),
                "text": text or "Copy code",
            }

        return {"type": "QUICK_REPLY", "text": text}

    def _components_from_legacy_fields(self, template: WhatsAppTemplate) -> list[dict]:
        components = []
        header = template.header or {}
        if header and (header.get("format") or header.get("type")):
            header_type = (header.get("format") or header.get("type") or "TEXT").upper()
            component = {"type": "HEADER", "format": header_type}
            if header_type == "TEXT" and header.get("text"):
                component["text"] = header["text"]
            if header.get("example"):
                component["example"] = header["example"]
            components.append(component)

        if template.body:
            if template.category == WhatsAppTemplate.Category.AUTHENTICATION:
                components.append({"type": "BODY", "add_security_recommendation": True})
            else:
                body = {"type": "BODY", "text": template.body}
                if template.variables:
                    body["example"] = {"body_text": [template.variables]}
                elif template.examples:
                    body["example"] = template.examples
                components.append(body)

        if template.footer:
            components.append({"type": "FOOTER", "text": template.footer})

        buttons = template.buttons or []
        if buttons:
            components.append({"type": "BUTTONS", "buttons": buttons})

        return components

    def _apply_meta_response(self, template: WhatsAppTemplate, data: dict):
        status = (data.get("status") or "").lower()
        template.whatsapp_template_id = data.get("id", template.whatsapp_template_id)
        template.meta_status = data.get("status", template.meta_status)
        if status in WhatsAppTemplate.Status.values:
            template.status = status
        elif status == "pending":
            template.status = WhatsAppTemplate.Status.PENDING
        template.last_synced_at = timezone.now()
        template.save(update_fields=[
            "whatsapp_template_id",
            "meta_status",
            "status",
            "last_synced_at",
            "updated_at",
        ])

    def _defaults_from_meta(self, item: dict) -> dict:
        components = item.get("components") or []
        body = ""
        header = {}
        footer = ""
        buttons = []
        for component in components:
            ctype = component.get("type")
            if ctype == "BODY":
                body = component.get("text", "")
            elif ctype == "HEADER":
                header = component
            elif ctype == "FOOTER":
                footer = component.get("text", "")
            elif ctype == "BUTTONS":
                buttons = component.get("buttons", [])

        status = (item.get("status") or "").lower()
        # Meta returns DISABLED / PAUSED / DELETED — keep local status as rejected only for
        # REJECTED; leave other non-standard Meta statuses as pending so UI can use meta_status.
        if status in WhatsAppTemplate.Status.values:
            local_status = status
        elif status in {"disabled", "paused", "deleted"}:
            local_status = WhatsAppTemplate.Status.REJECTED
        else:
            local_status = WhatsAppTemplate.Status.PENDING
        return {
            "category": (item.get("category") or WhatsAppTemplate.Category.UTILITY).lower(),
            "status": local_status,
            "meta_status": item.get("status", ""),
            "whatsapp_template_id": item.get("id", ""),
            "quality_rating": (item.get("quality_score") or {}).get("score", ""),
            "rejected_reason": item.get("rejected_reason", ""),
            "components": components,
            "header": header,
            "body": body,
            "footer": footer,
            "buttons": buttons,
            "last_synced_at": timezone.now(),
        }


def build_template_send_components(
    template: WhatsAppTemplate,
    body_params: list[str] | None = None,
    wa: "WhatsAppService | None" = None,
) -> list[dict]:
    """Build WhatsApp send API components for a template message."""
    from apps.core.whatsapp_service import WhatsAppService

    components = []
    header = template.header or {}
    header_format = (header.get("format") or "").upper()

    if header_format == "IMAGE" and template.media_asset:
        asset = template.media_asset
        media_ref: dict = {}
        media_id = asset.meta_media_id

        if not media_id and wa and asset.file and asset.file.path:
            upload = wa.upload_media_file(asset.file.path, asset.mime_type or "image/jpeg")
            media_id = upload.get("id", "")
            if media_id:
                asset.meta_media_id = media_id
                asset.save(update_fields=["meta_media_id", "updated_at"])

        if media_id:
            media_ref = {"id": media_id}
        elif asset.file:
            image_url = asset.file.url
            if image_url.startswith("/"):
                from django.conf import settings as django_settings
                base = getattr(django_settings, "PUBLIC_BASE_URL", "") or ""
                if base:
                    image_url = f"{base.rstrip('/')}{image_url}"
            if image_url.startswith("http"):
                media_ref = {"link": image_url}

        if media_ref:
            components.append({
                "type": "header",
                "parameters": [{"type": "image", "image": media_ref}],
            })

    params = body_params if body_params is not None else (template.variables or [])
    if params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(value)} for value in params],
        })

    if template.category == WhatsAppTemplate.Category.AUTHENTICATION and params:
        components.append({
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "text": str(params[0])}],
        })

    return components
