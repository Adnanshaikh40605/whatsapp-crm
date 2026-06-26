"""SMS provider client with a Twilio-compatible implementation."""

import logging
from uuid import uuid4

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SMSService:
    def __init__(self, organization):
        self.org = organization
        self.provider = settings.SMS_PROVIDER
        self.from_number = settings.SMS_FROM_NUMBER
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.messaging_service_sid = settings.TWILIO_MESSAGING_SERVICE_SID

    @property
    def is_configured(self):
        if self.provider != "twilio":
            return False
        return bool(
            self.account_sid
            and self.auth_token
            and (self.from_number or self.messaging_service_sid)
        )

    def send_text(self, to: str, body: str) -> dict:
        if not self.is_configured:
            return {
                "simulated": True,
                "provider": self.provider,
                "sid": f"sim_sms_{uuid4().hex}",
                "to": to,
                "body": body,
            }

        payload = {"To": to, "Body": body}
        if self.messaging_service_sid:
            payload["MessagingServiceSid"] = self.messaging_service_sid
        else:
            payload["From"] = self.from_number

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        try:
            response = requests.post(
                url,
                data=payload,
                auth=(self.account_sid, self.auth_token),
                timeout=30,
            )
            data = response.json()
            if not response.ok:
                logger.error("SMS provider error: %s", data)
                return {"error": data}
            return data
        except requests.RequestException as exc:
            logger.exception("SMS send failed")
            return {"error": str(exc)}
