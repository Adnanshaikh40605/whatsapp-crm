"""Add a contact and send a WhatsApp test message for an organization."""

import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.campaigns.meta import MetaTemplateService
from apps.campaigns.models import WhatsAppTemplate
from apps.core.whatsapp_service import WhatsAppService
from apps.crm.models import Contact
from apps.inbox.models import Conversation, Message
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = "Create a contact and send a WhatsApp test template for a project"

    def add_arguments(self, parser):
        parser.add_argument("org_name", type=str, help="Organization name (partial match ok)")
        parser.add_argument("phone", type=str, help="Recipient phone, e.g. 9372792693")
        parser.add_argument(
            "--template",
            default="",
            help="Template name. Defaults to first approved UTILITY template, then hello_world.",
        )
        parser.add_argument(
            "--text",
            default="",
            help="Send free-form text instead of a template (requires open 24h window).",
        )
        parser.add_argument(
            "--name",
            default="Test Contact",
            help="Contact display name",
        )
        parser.add_argument(
            "--country-code",
            default="91",
            help="Country code when phone is 10 digits. Default: 91.",
        )

    def handle(self, *args, **options):
        org = Organization.objects.filter(
            name__icontains=options["org_name"].strip(),
            is_active=True,
        ).first()
        if not org:
            raise CommandError(f'No active organization matching "{options["org_name"]}"')

        if not org.whatsapp_phone_number_id or not org.whatsapp_access_token:
            raise CommandError(f'"{org.name}" is missing WhatsApp Cloud API credentials.')

        phone = self.normalize_phone(options["phone"], options["country_code"])
        first_name = options["name"].strip() or "Test Contact"

        contact, created = Contact.objects.update_or_create(
            organization=org,
            phone=phone,
            defaults={
                "first_name": first_name,
                "source": Contact.Source.MANUAL,
                "is_active": True,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Contact {"created" if created else "updated"}: {contact.full_name} ({phone})'
            )
        )

        wa = WhatsAppService(org)
        if options["text"]:
            result = wa.send_text(phone, options["text"])
            message_type = Message.MessageType.TEXT
            content = options["text"]
            template_name = ""
        else:
            template_name, language = self.resolve_template(org, options["template"].strip())
            self.stdout.write(f"Sending template: {template_name} ({language})")
            result = wa.send_template(phone, template_name, language)
            message_type = Message.MessageType.TEMPLATE
            content = f"Template: {template_name}"

        if result.get("error"):
            raise CommandError(json.dumps(result["error"], indent=2))

        conversation, _ = Conversation.objects.get_or_create(
            organization=org,
            contact=contact,
            defaults={"status": Conversation.Status.OPEN},
        )
        wa_message_id = ""
        messages = result.get("messages") or []
        if messages:
            wa_message_id = messages[0].get("id", "")

        message = Message.objects.create(
            organization=org,
            conversation=conversation,
            channel=Message.Channel.WHATSAPP,
            direction=Message.Direction.OUTBOUND,
            message_type=message_type,
            content=content,
            template_name=template_name,
            whatsapp_message_id=wa_message_id,
            status=Message.Status.SENT if wa_message_id else Message.Status.PENDING,
            metadata={"meta_response": result},
        )

        now = timezone.now()
        conversation.last_message_at = now
        conversation.last_message_preview = content[:255]
        conversation.save(update_fields=["last_message_at", "last_message_preview", "updated_at"])
        contact.last_contacted_at = now
        contact.save(update_fields=["last_contacted_at", "updated_at"])

        self.stdout.write(self.style.SUCCESS("WhatsApp API accepted the message."))
        self.stdout.write(f"  message_id: {message.id}")
        self.stdout.write(f"  whatsapp_message_id: {wa_message_id or 'n/a'}")
        self.stdout.write(json.dumps(result, indent=2))

    def resolve_template(self, org, preferred: str) -> tuple[str, str]:
        if preferred:
            tpl = WhatsAppTemplate.objects.filter(
                organization=org, name=preferred, status=WhatsAppTemplate.Status.APPROVED
            ).first()
            if tpl:
                return tpl.name, tpl.language or "en_US"

        sync = MetaTemplateService(org).sync_templates()
        if sync.get("error"):
            self.stdout.write(self.style.WARNING(f"Template sync warning: {sync['error']}"))

        approved = WhatsAppTemplate.objects.filter(
            organization=org,
            status=WhatsAppTemplate.Status.APPROVED,
        ).order_by("category", "name")

        utility = approved.filter(category=WhatsAppTemplate.Category.UTILITY).first()
        if utility:
            return utility.name, utility.language or "en_US"

        any_tpl = approved.first()
        if any_tpl:
            return any_tpl.name, any_tpl.language or "en_US"

        if preferred:
            return preferred, "en_US"
        return "hello_world", "en_US"

    @staticmethod
    def normalize_phone(phone: str, country_code: str) -> str:
        digits = "".join(ch for ch in phone if ch.isdigit())
        country_code = "".join(ch for ch in country_code if ch.isdigit())
        if not digits:
            raise CommandError("Phone number is empty.")
        if digits.startswith("00"):
            return digits[2:]
        if digits.startswith(country_code) and len(digits) > len(country_code) + 7:
            return digits
        if len(digits) == 10 and country_code:
            return f"{country_code}{digits}"
        return digits
