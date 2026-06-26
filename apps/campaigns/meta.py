import logging

import requests
from django.utils import timezone

from apps.campaigns.models import WhatsAppTemplate

logger = logging.getLogger(__name__)


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
        response = requests.post(url, headers=self._headers(), json=payload, timeout=30)
        data = response.json()
        if not response.ok:
            logger.warning("Meta template create failed: %s", data)
            return {"error": data}
        self._apply_meta_response(template, data)
        return data

    def sync_templates(self) -> dict:
        if not self.is_configured:
            return {"error": "WhatsApp Business Account is not connected."}

        url = f"{self.GRAPH_API}/{self.org.whatsapp_business_account_id}/message_templates"
        response = requests.get(
            url,
            headers=self._headers(),
            params={
                "fields": "id,name,status,language,category,components,quality_score,rejected_reason",
                "limit": 100,
            },
            timeout=30,
        )
        data = response.json()
        if not response.ok:
            logger.warning("Meta template sync failed: %s", data)
            return {"error": data}

        synced = 0
        for item in data.get("data", []):
            defaults = self._defaults_from_meta(item)
            WhatsAppTemplate.objects.update_or_create(
                organization=self.org,
                name=item.get("name", ""),
                language=item.get("language", "en_US"),
                defaults=defaults,
            )
            synced += 1
        return {"synced_count": synced, "raw": data}

    def refresh_template(self, template: WhatsAppTemplate) -> dict:
        result = self.sync_templates()
        template.refresh_from_db()
        return result

    def _build_payload(self, template: WhatsAppTemplate) -> dict:
        components = template.components or self._components_from_legacy_fields(template)
        payload = {
            "name": template.name,
            "language": template.language,
            "category": template.category.upper(),
            "components": components,
        }
        return payload

    def _components_from_legacy_fields(self, template: WhatsAppTemplate) -> list[dict]:
        components = []
        header = template.header or {}
        if header:
            header_type = (header.get("format") or header.get("type") or "TEXT").upper()
            component = {"type": "HEADER", "format": header_type}
            if header_type == "TEXT" and header.get("text"):
                component["text"] = header["text"]
            if header.get("example"):
                component["example"] = header["example"]
            components.append(component)

        if template.body:
            body = {"type": "BODY", "text": template.body}
            if template.examples:
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
        local_status = status if status in WhatsAppTemplate.Status.values else WhatsAppTemplate.Status.PENDING
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
