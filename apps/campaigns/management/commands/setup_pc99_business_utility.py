"""Submit pc99_business_utility — same as pc99_business_details, Utility, empty footer.

Dynamic E-Brochure URL for track_ecard:
  https://api.driveronhire.ai/r/{{1}}
"""

from django.core.management.base import BaseCommand, CommandError

from apps.campaigns.meta import MetaTemplateService
from apps.campaigns.models import WhatsAppTemplate
from apps.core.models import set_current_organization
from apps.organizations.models import Organization

TEMPLATE_NAME = "pc99_business_utility"
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
FOOTER = ""  # intentionally empty
PHONE = "+918080748282"
TRACK_BASE = "https://api.driveronhire.ai/r/"
EXAMPLE_TOKEN = "demoTrackToken01"


class Command(BaseCommand):
    help = "Create/submit pc99_business_utility (Utility, empty footer, trackable E-Brochure)"

    def add_arguments(self, parser):
        parser.add_argument("org_name", type=str, nargs="?", default="Pest Control")

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
            {"type": "PHONE_NUMBER", "text": "Call Now", "phone_number": PHONE},
            {
                "type": "URL",
                "text": "E-Brochure",
                "url": dynamic_url,
                "example": [example_url],
            },
        ]
        # Omit FOOTER component entirely when footer is empty
        components = [
            {"type": "HEADER", "format": "TEXT", "text": HEADER_TEXT},
            {"type": "BODY", "text": BODY},
            {"type": "BUTTONS", "buttons": buttons},
        ]

        tpl, created = WhatsAppTemplate.objects.update_or_create(
            organization=org,
            name=TEMPLATE_NAME,
            language=LANGUAGE,
            defaults={
                "category": WhatsAppTemplate.Category.UTILITY,
                "status": WhatsAppTemplate.Status.DRAFT,
                "meta_status": "",
                "whatsapp_template_id": "",
                "rejected_reason": "",
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
                f"{'Created' if created else 'Updated'} local {TEMPLATE_NAME} "
                f"category=UTILITY footer=empty url={dynamic_url}"
            )
        )

        meta = MetaTemplateService(org)
        result = meta.create_template(tpl)
        if result.get("error"):
            self.stdout.write(self.style.ERROR(f"Meta submit error: {result['error']}"))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Submitted — id={result.get('id')} "
                    f"status={result.get('status', 'pending')} "
                    f"category={result.get('category', 'UTILITY')}"
                )
            )

        meta.sync_templates()
        tpl.refresh_from_db()
        self.stdout.write(
            f"Final: status={tpl.status} meta={tpl.meta_status} "
            f"category={tpl.category} id={tpl.whatsapp_template_id}"
        )
        if tpl.category != WhatsAppTemplate.Category.UTILITY:
            self.stdout.write(
                self.style.WARNING(
                    "Meta reclassified category away from UTILITY. "
                    "WhatsFlow cannot force Utility when Meta marks it Marketing."
                )
            )
