"""Create and submit pest_ecard_test as UTILITY (same content as approved business-details style)."""

from django.core.management.base import BaseCommand, CommandError

from apps.campaigns.meta import MetaTemplateService
from apps.campaigns.models import WhatsAppTemplate
from apps.core.models import set_current_organization
from apps.organizations.models import Organization

TEMPLATE_NAME = "pest_ecard_test"
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
# Static URL — same pattern as approved Utility template pest_business_details
BROCHURE_URL = "https://www.pestcontrol99.com/e-card/"


class Command(BaseCommand):
    help = "Create/submit pest_ecard_test as UTILITY with Call Now + E-Brochure"

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
                "example": [BROCHURE_URL],
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
                "meta_status": "",
                "whatsapp_template_id": "",
                "rejected_reason": "",
                "header": {"type": "HEADER", "format": "TEXT", "text": HEADER_TEXT},
                "body": BODY,
                "footer": FOOTER,
                "buttons": buttons,
                "variables": [],
                "components": components,
                "examples": {},
                "template_type": "standard",
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if created else 'Updated'} local {TEMPLATE_NAME} category=UTILITY"
            )
        )

        meta = MetaTemplateService(org)
        result = meta.create_template(tpl)
        if result.get("error"):
            self.stdout.write(self.style.ERROR(f"Meta submit error: {result['error']}"))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Submitted as UTILITY — id={result.get('id')} "
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
