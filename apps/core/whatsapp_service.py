"""Central Meta WhatsApp Cloud API client."""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class WhatsAppService:
    GRAPH_API = "https://graph.facebook.com/v21.0"

    def __init__(self, organization):
        self.org = organization
        self.phone_number_id = organization.whatsapp_phone_number_id
        self.access_token = organization.whatsapp_access_token

    @property
    def is_configured(self):
        return bool(self.phone_number_id and self.access_token)

    def _post(self, payload: dict) -> dict:
        if not self.is_configured:
            return {"simulated": True, **payload}

        url = f"{self.GRAPH_API}/{self.phone_number_id}/messages"
        try:
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
                json=payload,
                timeout=30,
            )
            data = resp.json()
            if not resp.ok:
                logger.error("WhatsApp API error: %s", data)
                return {"error": data}
            return data
        except requests.RequestException as exc:
            logger.exception("WhatsApp send failed")
            return {"error": str(exc)}

    def send_text(self, to: str, body: str) -> dict:
        return self._post({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        })

    def send_template(self, to: str, template_name: str, language: str = "en", components: list | None = None) -> dict:
        template = {"name": template_name, "language": {"code": language}}
        if components:
            template["components"] = components
        return self._post({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": template,
        })

    def send_interactive_buttons(self, to: str, body: str, buttons: list[dict]) -> dict:
        return self._post({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
                        for b in buttons[:3]
                    ],
                },
            },
        })

    def send_interactive_list(self, to: str, body: str, button_text: str, sections: list[dict]) -> dict:
        return self._post({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body},
                "action": {"button": button_text[:20], "sections": sections},
            },
        })

    def send_media(self, to: str, media_type: str, link: str, caption: str = "") -> dict:
        media = {"link": link}
        if caption and media_type in ("image", "video", "document"):
            media["caption"] = caption
        return self._post({
            "messaging_product": "whatsapp",
            "to": to,
            "type": media_type,
            media_type: media,
        })

    def send_carousel_template(self, to: str, template_name: str, cards: list[dict], language: str = "en") -> dict:
        """Send carousel via approved template components."""
        components = [{"type": "carousel", "cards": cards}]
        return self.send_template(to, template_name, language, components)

    @staticmethod
    def verify_signature(payload: bytes, signature: str) -> bool:
        from apps.onboarding.whatsapp import WhatsAppConnectService
        return WhatsAppConnectService.verify_webhook_signature(payload, signature)
