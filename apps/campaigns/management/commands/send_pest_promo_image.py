"""Send pest promo image to a phone (requires open 24h window — user must reply HI first)."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile

from apps.campaigns.models import MediaAsset, WhatsAppTemplate
from apps.campaigns.meta import MetaTemplateService, build_template_send_components
from apps.core.whatsapp_service import WhatsAppService
from apps.organizations.models import Organization

from apps.campaigns.promo import get_promo_image_path


class Command(BaseCommand):
    help = "Send pest control promo image via utility template or direct image message"

    def add_arguments(self, parser):
        parser.add_argument("org_name", type=str)
        parser.add_argument("phone", type=str)
        parser.add_argument("--image", default="", help="Path to promo image PNG/JPG")
        parser.add_argument("--name", default="Adnan", help="Name for template variable")

    def handle(self, *args, **options):
        org = Organization.objects.filter(name__icontains=options["org_name"].strip(), is_active=True).first()
        if not org:
            raise CommandError("Organization not found")

        phone = "".join(ch for ch in options["phone"] if ch.isdigit())
        if len(phone) == 10:
            phone = f"91{phone}"

        image_path = options["image"] or get_promo_image_path()
        if not image_path or not Path(image_path).is_file():
            raise CommandError(f"Image not found: {image_path}")

        wa = WhatsAppService(org)
        meta = MetaTemplateService(org)
        meta.sync_templates()

        # Prefer approved utility image template
        utility_tpl = WhatsAppTemplate.objects.filter(
            organization=org, name="pest_service_update", status=WhatsAppTemplate.Status.APPROVED,
        ).first()

        if utility_tpl:
            with open(image_path, "rb") as handle:
                asset = utility_tpl.media_asset
                if asset:
                    asset.meta_media_id = ""
                    asset.file.save("pest_mosquito.png", ContentFile(handle.read()), save=True)
            components = build_template_send_components(utility_tpl, [options["name"]], wa=wa)
            result = wa.send_template(phone, utility_tpl.name, utility_tpl.language, components)
            if not result.get("error"):
                self.stdout.write(self.style.SUCCESS(f"Sent utility image template to {phone}"))
                return
            self.stdout.write(self.style.WARNING(f"Utility template send failed: {result['error']}"))

        # Direct image (works only inside 24h window after customer replies)
        upload = wa.upload_media_file(image_path, "image/png")
        if upload.get("error"):
            raise CommandError(f"Media upload failed: {upload['error']}")

        import requests

        caption = (
            f"Hello {options['name']},\n\n"
            "Here is your pest control service update.\n\n"
            "Professional treatment for mosquitoes, termites & more.\n\n"
            "Reply to book your inspection.\n\n"
            "— Pest Control 99"
        )
        url = f"https://graph.facebook.com/v21.0/{org.whatsapp_phone_number_id}/messages"
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {org.whatsapp_access_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "image",
                "image": {"id": upload["id"], "caption": caption[:1024]},
            },
            timeout=30,
        )
        data = response.json()
        if data.get("error"):
            raise CommandError(
                f"Direct image send failed: {data['error']}\n\n"
                "Tip: Reply HI to Pest Control 99 on WhatsApp first, then run this command again."
            )
        self.stdout.write(self.style.SUCCESS(f"Sent direct image to {phone}: {data.get('messages')}"))
