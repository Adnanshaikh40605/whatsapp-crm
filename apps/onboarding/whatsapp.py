import hashlib
import hmac
import logging

import requests
from django.conf import settings
from django.utils import timezone

from apps.onboarding.services import WorkspaceBootstrap

logger = logging.getLogger(__name__)


class WhatsAppConnectService:
    """Handle Meta Embedded Signup and webhook auto-configuration."""

    GRAPH_API = "https://graph.facebook.com/v21.0"

    def __init__(self, organization):
        self.org = organization

    def process_embedded_signup(self, code: str, waba_id: str = "", phone_number_id: str = "", access_token: str = ""):
        """
        Exchange embedded signup code for access token and configure workspace.
        In production: exchange code via Meta OAuth endpoint.
        """
        app_id = getattr(settings, "META_APP_ID", "")
        app_secret = getattr(settings, "META_APP_SECRET", "")

        token = access_token.strip()
        if code and app_id and app_secret:
            try:
                resp = requests.get(
                    f"{self.GRAPH_API}/oauth/access_token",
                    params={
                        "client_id": app_id,
                        "client_secret": app_secret,
                        "code": code,
                    },
                    timeout=15,
                )
                if resp.ok:
                    token = resp.json().get("access_token", "") or token
            except requests.RequestException as e:
                logger.warning("Meta token exchange failed: %s", e)

        # Store credentials (dev mode: accept provided IDs directly)
        self.org.whatsapp_business_account_id = waba_id
        self.org.whatsapp_phone_number_id = phone_number_id
        if token:
            self.org.whatsapp_access_token = token
        self.org.whatsapp_connected = True
        self.org.whatsapp_connected_at = timezone.now()
        self.org.onboarding_step = max(self.org.onboarding_step, 2)
        self.org.save()

        self._configure_webhook()
        bootstrap = WorkspaceBootstrap(self.org)
        bootstrap.setup_default_pipeline()
        bootstrap.setup_default_automations()

        return {
            "connected": True,
            "waba_id": waba_id,
            "phone_number_id": phone_number_id,
            "webhook_configured": True,
        }

    def _configure_webhook(self):
        """Subscribe app to WhatsApp webhook events via Meta Graph API."""
        webhook_url = getattr(settings, "WHATSAPP_WEBHOOK_URL", "")
        verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "whatsflow_verify")
        self.org.settings = {
            **(self.org.settings or {}),
            "webhook_url": webhook_url,
            "webhook_verify_token": verify_token,
            "webhook_events": ["messages"],
        }
        self.org.save(update_fields=["settings"])
        result = self.subscribe_whatsapp_webhooks()
        self.org.settings = {
            **(self.org.settings or {}),
            "webhook_subscription": result,
        }
        self.org.save(update_fields=["settings"])
        return result

    @staticmethod
    def subscribe_whatsapp_webhooks() -> dict:
        """Register callback URL with Meta for whatsapp_business_account messages."""
        app_id = getattr(settings, "META_APP_ID", "")
        app_secret = getattr(settings, "META_APP_SECRET", "")
        webhook_url = getattr(settings, "WHATSAPP_WEBHOOK_URL", "")
        verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "whatsflow_verify")

        if not app_id or not app_secret or not webhook_url:
            logger.warning(
                "WhatsApp webhook subscription skipped: missing app_id, app_secret, or webhook URL"
            )
            return {"ok": False, "error": "missing_config"}

        app_access_token = f"{app_id}|{app_secret}"
        try:
            resp = requests.post(
                f"{WhatsAppConnectService.GRAPH_API}/{app_id}/subscriptions",
                data={
                    "object": "whatsapp_business_account",
                    "callback_url": webhook_url,
                    "verify_token": verify_token,
                    "fields": "messages",
                    "access_token": app_access_token,
                },
                timeout=20,
            )
            payload = resp.json()
            if resp.ok:
                logger.info("Meta webhook subscription succeeded: %s", payload)
                return {"ok": True, "response": payload}
            logger.warning("Meta webhook subscription failed: %s", payload)
            return {"ok": False, "error": payload}
        except requests.RequestException as exc:
            logger.warning("Meta webhook subscription request failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def get_embedded_signup_config(self):
        """Return config needed for Meta Embedded Signup frontend SDK."""
        return {
            "app_id": getattr(settings, "META_APP_ID", ""),
            "config_id": getattr(settings, "META_CONFIG_ID", ""),
            "redirect_uri": getattr(settings, "META_REDIRECT_URI", ""),
            "webhook_url": getattr(settings, "WHATSAPP_WEBHOOK_URL", ""),
            "features": ["whatsapp_business_messaging"],
        }

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str) -> bool:
        secret = getattr(settings, "META_APP_SECRET", "")
        if not secret or not signature:
            return False
        expected = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
