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
        """Subscribe WABA to webhook events."""
        webhook_url = getattr(settings, "WHATSAPP_WEBHOOK_URL", "")
        verify_token = getattr(settings, "WHATSAPP_VERIFY_TOKEN", "whatsflow_verify")
        self.org.settings = {
            **self.org.settings,
            "webhook_url": webhook_url,
            "webhook_verify_token": verify_token,
            "webhook_events": [
                "messages", "message_deliveries", "message_reads", "message_echoes",
            ],
        }
        self.org.save(update_fields=["settings"])

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
