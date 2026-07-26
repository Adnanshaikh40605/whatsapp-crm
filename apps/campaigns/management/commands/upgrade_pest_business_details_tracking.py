"""Upgrade EXISTING pest_business_details to dynamic E-Brochure URL (same Meta name).

Does NOT create a new template name. Deletes + resubmits pest_business_details so
the E-Brochure button becomes:

  https://api.driveronhire.ai/r/{{1}}

Then Pest CRM can send template_name=pest_business_details + track_ecard=true.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.campaigns.meta import MetaTemplateService
from apps.campaigns.models import WhatsAppTemplate
from apps.core.models import set_current_organization
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
TRACK_BASE = "https://api.driveronhire.ai/r/"
EXAMPLE_TOKEN = "demoTrackToken01"


class Command(BaseCommand):
    help = (
        "Upgrade pest_business_details (same name) to dynamic E-Brochure URL for track_ecard"
    )

    def add_arguments(self, parser):
        parser.add_argument("org_name", type=str, nargs="?", default="Pest Control")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirm delete+resubmit of pest_business_details on Meta",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError(
                "Refusing to run without --yes. This deletes and resubmits "
                "pest_business_details on Meta (same name) with a dynamic E-Brochure URL."
            )

        org = (
            Organization.objects.filter(name__icontains=options["org_name"].strip(), is_active=True)
            .order_by("name")
            .first()
        )
        if not org:
            raise CommandError(f"Organization not found for: {options['org_name']}")

        set_current_organization(org)
        meta = MetaTemplateService(org)
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
        components = [
            {"type": "HEADER", "format": "TEXT", "text": HEADER_TEXT},
            {"type": "BODY", "text": BODY},
            {"type": "FOOTER", "text": FOOTER},
            {"type": "BUTTONS", "buttons": buttons},
        ]

        tpl = WhatsAppTemplate.objects.filter(
            organization=org, name=TEMPLATE_NAME, language=LANGUAGE
        ).first()
        if not tpl:
            tpl = WhatsAppTemplate(organization=org, name=TEMPLATE_NAME, language=LANGUAGE)

        # Delete current Meta version (static URL) so we can recreate same name.
        if tpl.pk and (tpl.whatsapp_template_id or tpl.status == WhatsAppTemplate.Status.APPROVED):
            deleted = meta.delete_template(tpl)
            if deleted.get("error"):
                self.stdout.write(self.style.ERROR(f"Meta delete error: {deleted['error']}"))
            else:
                self.stdout.write(self.style.SUCCESS("Deleted Meta pest_business_details (old static URL)"))

        tpl.category = WhatsAppTemplate.Category.UTILITY
        tpl.status = WhatsAppTemplate.Status.DRAFT
        tpl.meta_status = ""
        tpl.whatsapp_template_id = ""
        tpl.rejected_reason = ""
        tpl.header = {"type": "HEADER", "format": "TEXT", "text": HEADER_TEXT}
        tpl.body = BODY
        tpl.footer = FOOTER
        tpl.buttons = buttons
        tpl.variables = []
        tpl.components = components
        tpl.examples = {"button_url": [example_url]}
        tpl.template_type = "standard"
        tpl.save()

        self.stdout.write(self.style.SUCCESS(f"Local {TEMPLATE_NAME} set to dynamic URL {dynamic_url}"))

        result = meta.create_template(tpl)
        if result.get("error"):
            self.stdout.write(self.style.ERROR(f"Meta submit error: {result['error']}"))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Resubmitted pest_business_details — id={result.get('id')} "
                    f"status={result.get('status', 'pending')}"
                )
            )

        meta.sync_templates()
        tpl.refresh_from_db()
        self.stdout.write(
            f"Final: name={tpl.name} status={tpl.status} meta={tpl.meta_status} "
            f"category={tpl.category} id={tpl.whatsapp_template_id}"
        )
        self.stdout.write(
            "CRM: keep template_name=pest_business_details + track_ecard=true. "
            "Tracking works after Meta status is APPROVED."
        )
