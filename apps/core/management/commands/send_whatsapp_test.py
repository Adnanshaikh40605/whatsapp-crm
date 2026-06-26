import json
import os

import requests
from django.core.management.base import BaseCommand, CommandError


GRAPH_API_VERSION = "v21.0"


class Command(BaseCommand):
    help = "Send a WhatsApp Cloud API test message using Meta credentials."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Recipient phone number, e.g. 9372792693 or 919372792693")
        parser.add_argument(
            "--phone-number-id",
            default=os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""),
            help="Meta Phone Number ID. Defaults to WHATSAPP_PHONE_NUMBER_ID.",
        )
        parser.add_argument(
            "--access-token",
            default=os.getenv("WHATSAPP_ACCESS_TOKEN", ""),
            help="Permanent access token. Defaults to WHATSAPP_ACCESS_TOKEN.",
        )
        parser.add_argument(
            "--country-code",
            default="91",
            help="Country code to prepend when the recipient number is local. Default: 91.",
        )
        parser.add_argument(
            "--template",
            default="hello_world",
            help="Approved template name to send. Default: hello_world.",
        )
        parser.add_argument(
            "--language",
            default="en_US",
            help="Template language code. Default: en_US.",
        )
        parser.add_argument(
            "--text",
            default="",
            help="Send free-form text instead of a template. Requires a valid 24-hour customer service window.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the request without calling Meta.",
        )

    def handle(self, *args, **options):
        phone_number_id = options["phone_number_id"].strip()
        access_token = options["access_token"].strip()
        recipient = self.normalize_phone(options["to"], options["country_code"])

        if not phone_number_id:
            raise CommandError("Missing --phone-number-id or WHATSAPP_PHONE_NUMBER_ID.")
        if not access_token:
            raise CommandError("Missing --access-token or WHATSAPP_ACCESS_TOKEN.")

        payload = self.build_payload(
            recipient=recipient,
            text=options["text"],
            template=options["template"],
            language=options["language"],
        )
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run only. No message sent."))
            self.stdout.write(f"POST {url}")
            self.stdout.write(json.dumps(payload, indent=2))
            return

        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
            timeout=30,
        )

        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text}

        if not response.ok:
            raise CommandError(json.dumps(data, indent=2))

        self.stdout.write(self.style.SUCCESS("WhatsApp API accepted the message."))
        self.stdout.write(json.dumps(data, indent=2))

    @staticmethod
    def normalize_phone(phone: str, country_code: str) -> str:
        digits = "".join(ch for ch in phone if ch.isdigit())
        country_code = "".join(ch for ch in country_code if ch.isdigit())

        if not digits:
            raise CommandError("Recipient phone number is empty.")
        if digits.startswith("00"):
            return digits[2:]
        if digits.startswith(country_code) and len(digits) > len(country_code) + 7:
            return digits
        if len(digits) == 10 and country_code:
            return f"{country_code}{digits}"
        return digits

    @staticmethod
    def build_payload(recipient: str, text: str, template: str, language: str) -> dict:
        if text:
            return {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": text},
            }

        return {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": language},
            },
        }
