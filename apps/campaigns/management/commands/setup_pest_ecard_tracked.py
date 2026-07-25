"""Submit pest_ecard_tracked utility template with dynamic E-Brochure URL for click tracking."""

from django.core.management.base import BaseCommand, CommandError

from apps.campaigns.meta import MetaTemplateService
from apps.campaigns.models import WhatsAppTemplate
from apps.core.models import set_current_organization
from apps.organizations.models import Organization

TEMPLATE_NAME = "pest_ecard_tracked"
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
# Dynamic suffix {{1}} = tracking token → https://api.driveronhire.ai/r/<token>
TRACK_BASE = "https://api.driveronhire.ai/r/"
EXAMPLE_TOKEN = "demoTrackToken01"


class Command(BaseCommand):
    help = "Create/submit pest_ecard_tracked template (dynamic E-Brochure URL for click tracking)"

    def add_arguments(self, parser):
        parser.add_argument("org_name", type=str, nargs="?", default="Pest Control")
        parser.add_argument("--submit-only", action="store_true")

    def handle(self, *args, **options):
        org = (
            Organization.objects.filter(name__icontains=options["org_name"].strip(), is_active=True)
            .order_by("name")
            .first()
        )
        if not org:
            raise CommandError(f"Organization not found for: {options['org_name']}")

        set_current_organization(org)
        dynamic_url = f"{TRACK_BASE}{{{{1}}}}"
        example_url = f"{TRACK_BASE}{EXAMPLE_TOKEN}"

        buttons = [
            {
                "type": "PHONE_NUMBER",
                "text": "Call Now",
                "phone_number": PHONE,
            },
            {
                "type": "URL",
                "text": "E-Brochure",
                "url": dynamic_url,
                "example": [example_url],
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
                "examples": {"button_url": [example_url]},
                "template_type": "standard",
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Updated'} local template {TEMPLATE_NAME} "
                f"url={dynamic_url}"
            )
        )

        if options["submit_only"] or tpl.status != WhatsAppTemplate.Status.APPROVED:
            meta = MetaTemplateService(org)
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

        self.stdout.write(f"Status: {tpl.status} meta={tpl.meta_status} id={tpl.whatsapp_template_id}")
        self.stdout.write(
            "After APPROVED, Pest CRM send with track_ecard=true and template_name=pest_ecard_tracked"
        )
