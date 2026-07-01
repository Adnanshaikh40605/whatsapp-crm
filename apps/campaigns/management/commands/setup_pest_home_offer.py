"""Create Wint Wealth-style pest offer template (image + text + Book Now button) and send."""

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from apps.campaigns.meta import MetaTemplateService, build_template_send_components
from apps.campaigns.models import MediaAsset, WhatsAppTemplate
from apps.campaigns.promo import get_promo_image_path
from apps.core.whatsapp_service import WhatsAppService
from apps.organizations.models import Organization

TEMPLATE_NAME = "pest_home_offer"
BODY = (
    "Hello {{1}},\n\n"
    "Your pest control service offer is live today:\n\n"
    "✅ Mosquito & termite treatment\n"
    "✅ Same-day booking available\n"
    "✅ Up to 30% OFF this season\n\n"
    "Tap below to book your inspection."
)
VARIABLES = ["Adnan"]


class Command(BaseCommand):
    help = "Create pest_home_offer utility template (Wint-style) and send to a phone"

    def add_arguments(self, parser):
        parser.add_argument("org_name", type=str)
        parser.add_argument("--phone", default="919372792693")
        parser.add_argument("--submit-only", action="store_true")

    def handle(self, *args, **options):
        org = Organization.objects.filter(name__icontains=options["org_name"].strip(), is_active=True).first()
        if not org:
            raise CommandError("Organization not found")

        image_path = get_promo_image_path()
        if not image_path:
            raise CommandError("Promo image not found in static/promo/pest_mosquito.png")

        with open(image_path, "rb") as handle:
            img_bytes = handle.read()

        asset, _ = MediaAsset.objects.update_or_create(
            organization=org,
            name="pest_home_offer_header",
            defaults={"asset_type": "image", "mime_type": "image/png"},
        )
        asset.meta_media_id = ""
        asset.file.save("pest_mosquito.png", ContentFile(img_bytes), save=True)

        components = [
            {"type": "HEADER", "format": "IMAGE"},
            {
                "type": "BODY",
                "text": BODY,
                "example": {"body_text": [VARIABLES]},
            },
            {"type": "FOOTER", "text": "Pest Control 99"},
            {
                "type": "BUTTONS",
                "buttons": [
                    {
                        "type": "URL",
                        "text": "Book Now",
                        "url": "https://vacationbna.com",
                        "example": ["https://vacationbna.com"],
                    },
                ],
            },
        ]

        tpl, created = WhatsAppTemplate.objects.update_or_create(
            organization=org,
            name=TEMPLATE_NAME,
            language="en_US",
            defaults={
                "category": WhatsAppTemplate.Category.UTILITY,
                "status": WhatsAppTemplate.Status.DRAFT,
                "body": BODY,
                "footer": "Pest Control 99",
                "variables": VARIABLES,
                "components": components,
                "header": {"format": "IMAGE"},
                "buttons": components[-1]["buttons"],
                "media_asset": asset,
            },
        )
        self.stdout.write(f"{'Created' if created else 'Updated'} template: {TEMPLATE_NAME}")

        meta = MetaTemplateService(org)
        existing = WhatsAppTemplate.objects.filter(
            organization=org, name=TEMPLATE_NAME, language="en_US",
        ).first()
        if existing and existing.status not in {WhatsAppTemplate.Status.APPROVED, WhatsAppTemplate.Status.PENDING}:
            meta.attach_header_media(tpl, image_path)
            result = meta.create_template(tpl)
            if result.get("error"):
                self.stdout.write(self.style.ERROR(f"Meta submit error: {result['error']}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Submitted — status: {result.get('status', 'pending')}"))

        meta.sync_templates()
        tpl.refresh_from_db()
        self.stdout.write(f"Current status: {tpl.status}")

        if options["submit_only"] or tpl.status != WhatsAppTemplate.Status.APPROVED:
            return

        phone = options["phone"]
        if len(phone) == 10:
            phone = f"91{phone}"

        wa = WhatsAppService(org)
        components_send = build_template_send_components(tpl, VARIABLES, wa=wa)
        send = wa.send_template(phone, tpl.name, tpl.language, components_send)
        if send.get("error"):
            raise CommandError(send["error"])
        self.stdout.write(self.style.SUCCESS(f"Sent Wint-style template to {phone}: {send.get('messages')}"))
