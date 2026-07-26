"""Create Pest Control utility e-card template (header + body + Call/E-Brochure CTAs) and send."""

from django.core.management.base import BaseCommand, CommandError

from apps.campaigns.meta import MetaTemplateService, build_template_send_components
from apps.campaigns.models import WhatsAppTemplate
from apps.core.models import set_current_organization
from apps.core.whatsapp_service import WhatsAppService
from apps.organizations.models import Organization

TEMPLATE_NAME = "pest_business_details"
LANGUAGE = "en_US"
HEADER_TEXT = "Dear, Customer"
BODY = (
    "Thank you for your valuable time.\n\n"
    "As discussed during our call, please find the details of PestControl99.com, "
    "a Government Licensed Professional Pest Management Company.\n\n"
    "You can explore our digital business card, e-brochure, services, and contact "
    "details using the buttons below.\n\n"
    "Thank you,"
)
FOOTER = "Pest Control 99"
PHONE = "+918080748282"
# Dynamic suffix {{1}} = WhatsFlow tracking token → /r/<token>/ → e-card page
BROCHURE_URL = "https://api.driveronhire.ai/r/{{1}}"
BROCHURE_EXAMPLE = "https://api.driveronhire.ai/r/demoTrackToken01"


class Command(BaseCommand):
    help = "Create pest_business_details utility template and optionally send a test"

    def add_arguments(self, parser):
        parser.add_argument("org_name", type=str, nargs="?", default="Pest Control")
        parser.add_argument("--phone", default="919372792693")
        parser.add_argument("--submit-only", action="store_true")
        parser.add_argument("--send-only", action="store_true")

    def handle(self, *args, **options):
        org = (
            Organization.objects.filter(name__icontains=options["org_name"].strip(), is_active=True)
            .order_by("name")
            .first()
        )
        if not org:
            raise CommandError(f"Organization not found for: {options['org_name']}")

        set_current_organization(org)
        self.stdout.write(f"Org: {org.name} ({org.id})")
        self.stdout.write(
            f"WhatsApp configured: {bool(org.whatsapp_business_account_id and org.whatsapp_access_token)}"
        )

        buttons = [
            {
                "type": "PHONE_NUMBER",
                "text": "Call Now",
                "phone_number": PHONE,
            },
            {
                "type": "URL",
                "text": "E-Brochure",
                "url": BROCHURE_URL,
                "example": [BROCHURE_EXAMPLE],
            },
        ]
        components = [
            {"type": "HEADER", "format": "TEXT", "text": HEADER_TEXT},
            {"type": "BODY", "text": BODY},
            {"type": "FOOTER", "text": FOOTER},
            {"type": "BUTTONS", "buttons": buttons},
        ]

        tpl, created = WhatsAppTemplate.objects.update_or_create(
            organization=org,
            name=TEMPLATE_NAME,
            language=LANGUAGE,
            defaults={
                "category": WhatsAppTemplate.Category.UTILITY,
                "status": WhatsAppTemplate.Status.DRAFT,
                "header": {"type": "HEADER", "format": "TEXT", "text": HEADER_TEXT},
                "body": BODY,
                "footer": FOOTER,
                "buttons": buttons,
                "variables": [],
                "components": components,
                "examples": {"button_url": [BROCHURE_EXAMPLE]},
                "template_type": "standard",
            },
        )
        self.stdout.write(
            self.style.SUCCESS(f"{'Created' if created else 'Updated'} local template: {TEMPLATE_NAME}")
        )

        meta = MetaTemplateService(org)

        if options["send_only"]:
            meta.sync_templates()
            tpl.refresh_from_db()
        elif tpl.status != WhatsAppTemplate.Status.APPROVED:
            result = meta.create_template(tpl)
            if result.get("error"):
                self.stdout.write(self.style.ERROR(f"Meta submit error: {result['error']}"))
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Submitted to Meta — id={result.get('id')} status={result.get('status', 'pending')}"
                    )
                )
            meta.sync_templates()
            tpl.refresh_from_db()

        self.stdout.write(f"Current status: {tpl.status} meta_status={tpl.meta_status}")

        if options["submit_only"]:
            return

        if tpl.status != WhatsAppTemplate.Status.APPROVED:
            self.stdout.write(
                self.style.WARNING(
                    "Template is not APPROVED yet — cannot send. Wait for Meta approval, then rerun with --send-only."
                )
            )
            return

        phone = str(options["phone"]).strip().lstrip("+")
        if len(phone) == 10:
            phone = f"91{phone}"

        wa = WhatsAppService(org)
        send = wa.send_template(phone, tpl.name, tpl.language, build_template_send_components(tpl, [], wa=wa))
        if send.get("error"):
            raise CommandError(str(send["error"]))
        self.stdout.write(self.style.SUCCESS(f"Sent template to {phone}: {send.get('messages')}"))
