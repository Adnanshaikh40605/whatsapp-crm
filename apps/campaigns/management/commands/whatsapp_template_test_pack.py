"""Create the 3 acceptance-test WhatsApp templates, submit to Meta, and send to a test number."""

import json
import os
import tempfile

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.campaigns.meta import MetaTemplateService, build_template_send_components
from apps.campaigns.models import MediaAsset, WhatsAppTemplate
from apps.core.whatsapp_service import WhatsAppService
from apps.crm.models import Contact
from apps.inbox.models import Conversation, Message
from apps.organizations.models import Organization

TEST_PHONE = "919372792693"

TEST_TEMPLATES = [
    {
        "name": "login_otp",
        "category": WhatsAppTemplate.Category.AUTHENTICATION,
        "language": "en_US",
        "body": "Your verification code is {{1}}.",
        "variables": ["458921"],
        "footer": "",
        "buttons": [{"type": "OTP", "otp_type": "COPY_CODE", "text": "Copy code"}],
        "send_params": ["458921"],
        "auth_format": True,
    },
    {
        "name": "booking_confirmation",
        "category": WhatsAppTemplate.Category.UTILITY,
        "language": "en_US",
        "body": (
            "Hello {{1}},\n\n"
            "Your booking {{2}} has been confirmed.\n\n"
            "Check-in: {{3}}\n\n"
            "Thank you for choosing us."
        ),
        "variables": ["Adnan", "BKG1024", "10 July 2026"],
        "footer": "",
        "buttons": [],
        "send_params": ["Adnan", "BKG1024", "10 July 2026"],
    },
    {
        "name": "summer_offer",
        "category": WhatsAppTemplate.Category.MARKETING,
        "language": "en_US",
        "header_format": "IMAGE",
        "body": (
            "Hello {{1}},\n\n"
            "Enjoy up to 30% OFF on your next booking.\n\n"
            "Limited time offer."
        ),
        "variables": ["Adnan"],
        "footer": "VacationBNA",
        "buttons": [
            {"type": "URL", "text": "Book Now", "url": "https://vacationbna.com", "example": ["https://vacationbna.com"]},
            {"type": "PHONE_NUMBER", "text": "Call Us", "phone_number": "+919372792693"},
        ],
        "send_params": ["Adnan"],
        "needs_image": True,
    },
]


class Command(BaseCommand):
    help = "Create login_otp, booking_confirmation, and summer_offer templates; submit and send tests"

    def add_arguments(self, parser):
        parser.add_argument("org_name", type=str, help="Organization name (partial match)")
        parser.add_argument("--phone", default=TEST_PHONE, help="Recipient phone (default: 919372792693)")
        parser.add_argument("--skip-submit", action="store_true", help="Only save locally, do not submit to Meta")
        parser.add_argument("--skip-send", action="store_true", help="Create/submit only, do not send messages")
        parser.add_argument("--send-only", action="store_true", help="Only send already-approved templates")

    def handle(self, *args, **options):
        org = Organization.objects.filter(name__icontains=options["org_name"].strip(), is_active=True).first()
        if not org:
            raise CommandError(f'No organization matching "{options["org_name"]}"')

        if not org.whatsapp_phone_number_id or not org.whatsapp_access_token:
            raise CommandError(f'"{org.name}" is missing WhatsApp credentials.')

        phone = self.normalize_phone(options["phone"])
        meta = MetaTemplateService(org)
        wa = WhatsAppService(org)
        results = []

        contact, _ = Contact.objects.update_or_create(
            organization=org,
            phone=phone,
            defaults={"first_name": "Adnan", "source": Contact.Source.MANUAL, "is_active": True},
        )

        for spec in TEST_TEMPLATES:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {spec['name']} ==="))
            template = self.upsert_template(org, spec)

            if not options["send_only"] and not options["skip_submit"]:
                existing = WhatsAppTemplate.objects.filter(
                    organization=org, name=spec["name"], language=spec["language"],
                ).first()
                if existing and existing.status in {
                    WhatsAppTemplate.Status.APPROVED,
                    WhatsAppTemplate.Status.PENDING,
                } and existing.whatsapp_template_id:
                    self.stdout.write(self.style.WARNING(
                        f"Skipping Meta submit — template already {existing.status} on Meta."
                    ))
                elif spec.get("needs_image"):
                    image_path = self.ensure_promo_image()
                    upload = meta.attach_header_media(template, image_path)
                    if upload.get("error"):
                        self.stdout.write(self.style.WARNING(f"Image upload warning: {upload['error']}"))
                    else:
                        self.stdout.write(self.style.SUCCESS(f"Header media uploaded: {upload.get('handle', '')[:40]}..."))
                    template.refresh_from_db()

                submit = meta.create_template(template)
                if submit.get("error"):
                    self.stdout.write(self.style.ERROR(f"Meta submit failed: {json.dumps(submit['error'], indent=2)}"))
                    results.append({"name": spec["name"], "submit": "failed", "error": submit["error"]})
                    continue
                self.stdout.write(self.style.SUCCESS(f"Submitted to Meta — status: {submit.get('status', 'pending')}"))
                template.refresh_from_db()

            meta.sync_templates()
            template = WhatsAppTemplate.objects.get(pk=template.pk)

            if template.status != WhatsAppTemplate.Status.APPROVED:
                self.stdout.write(self.style.WARNING(
                    f"Template status is '{template.status}' — Meta approval may take minutes. "
                    "Re-run with --send-only after approval."
                ))
                results.append({"name": spec["name"], "status": template.status, "send": "skipped"})
                if options["skip_send"]:
                    continue
                if template.status != WhatsAppTemplate.Status.APPROVED:
                    continue

            if options["skip_send"]:
                results.append({"name": spec["name"], "status": template.status, "send": "skipped"})
                continue

            components = build_template_send_components(template, spec.get("send_params"), wa)
            send_result = wa.send_template(phone, template.name, template.language, components)
            if send_result.get("error"):
                self.stdout.write(self.style.ERROR(f"Send failed: {json.dumps(send_result['error'], indent=2)}"))
                results.append({"name": spec["name"], "send": "failed", "error": send_result["error"]})
                continue

            wa_id = (send_result.get("messages") or [{}])[0].get("id", "")
            conversation, _ = Conversation.objects.get_or_create(
                organization=org, contact=contact, defaults={"status": Conversation.Status.OPEN},
            )
            Message.objects.create(
                organization=org,
                conversation=conversation,
                channel=Message.Channel.WHATSAPP,
                direction=Message.Direction.OUTBOUND,
                message_type=Message.MessageType.TEMPLATE,
                content=f"Template: {template.name}",
                template_name=template.name,
                whatsapp_message_id=wa_id,
                status=Message.Status.SENT if wa_id else Message.Status.PENDING,
                metadata={"meta_response": send_result, "template_test_pack": True},
            )
            now = timezone.now()
            conversation.last_message_at = now
            conversation.last_message_preview = f"Template: {template.name}"[:255]
            conversation.save(update_fields=["last_message_at", "last_message_preview", "updated_at"])

            self.stdout.write(self.style.SUCCESS(f"Sent to {phone} — wamid: {wa_id or 'n/a'}"))
            results.append({"name": spec["name"], "status": template.status, "send": "ok", "wamid": wa_id})

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Summary ==="))
        self.stdout.write(json.dumps(results, indent=2))

    def upsert_template(self, org: Organization, spec: dict) -> WhatsAppTemplate:
        components = []
        if spec.get("header_format"):
            components.append({"type": "HEADER", "format": spec["header_format"]})

        if spec.get("auth_format"):
            components.append({"type": "BODY", "add_security_recommendation": True})
        else:
            body_component = {"type": "BODY", "text": spec["body"]}
            if spec.get("variables"):
                body_component["example"] = {"body_text": [spec["variables"]]}
            components.append(body_component)

        if spec.get("footer"):
            components.append({"type": "FOOTER", "text": spec["footer"]})
        if spec.get("buttons"):
            components.append({"type": "BUTTONS", "buttons": spec["buttons"]})

        media_asset = None
        if spec.get("needs_image"):
            media_asset, _ = MediaAsset.objects.get_or_create(
                organization=org,
                name="summer_offer_header",
                defaults={
                    "asset_type": MediaAsset.AssetType.IMAGE,
                    "mime_type": "image/jpeg",
                },
            )
            if not media_asset.file:
                image_path = self.ensure_promo_image()
                with open(image_path, "rb") as handle:
                    media_asset.file.save("summer_offer.jpg", ContentFile(handle.read()), save=True)

        template, created = WhatsAppTemplate.objects.update_or_create(
            organization=org,
            name=spec["name"],
            language=spec["language"],
            defaults={
                "category": spec["category"],
                "status": WhatsAppTemplate.Status.DRAFT,
                "body": spec["body"],
                "footer": spec.get("footer", ""),
                "buttons": spec.get("buttons", []),
                "variables": spec.get("variables", []),
                "components": components,
                "examples": {"body_text": [spec.get("variables", [])]} if spec.get("variables") else {},
                "header": {"format": spec["header_format"]} if spec.get("header_format") else {},
                "media_asset": media_asset,
            },
        )
        action = "Created" if created else "Updated"
        self.stdout.write(f"{action} local template: {template.name}")
        return template

    @staticmethod
    def ensure_promo_image() -> str:
        path = os.path.join(tempfile.gettempdir(), "whatsflow_summer_offer.jpg")
        if os.path.isfile(path) and os.path.getsize(path) > 1000:
            return path

        # Minimal valid JPEG (1x1) — avoids external download SSL issues on macOS Python
        minimal_jpeg = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
            0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
            0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
            0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
            0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x37, 0xFF, 0xD9,
        ])
        with open(path, "wb") as handle:
            handle.write(minimal_jpeg)
        return path

    @staticmethod
    def normalize_phone(phone: str) -> str:
        digits = "".join(ch for ch in phone if ch.isdigit())
        if digits.startswith("91") and len(digits) == 12:
            return digits
        if len(digits) == 10:
            return f"91{digits}"
        return digits
