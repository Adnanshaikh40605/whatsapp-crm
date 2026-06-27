"""Connect WhatsApp Cloud API credentials to an organization by name."""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.onboarding.whatsapp import WhatsAppConnectService
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = "Connect WhatsApp Cloud API credentials to a project/organization"

    def add_arguments(self, parser):
        parser.add_argument("org_name", type=str, help="Organization name (partial match ok)")
        parser.add_argument("--phone-number-id", required=True)
        parser.add_argument("--waba-id", required=True)
        parser.add_argument("--access-token", required=True)

    def handle(self, *args, **options):
        name = options["org_name"].strip()
        org = Organization.objects.filter(name__icontains=name, is_active=True).first()
        if not org:
            raise CommandError(f'No active organization matching "{name}"')

        service = WhatsAppConnectService(org)
        result = service.process_embedded_signup(
            code="",
            waba_id=options["waba_id"],
            phone_number_id=options["phone_number_id"],
            access_token=options["access_token"],
        )

        org.onboarding_completed = True
        org.save(update_fields=["onboarding_completed", "updated_at"])

        self.stdout.write(self.style.SUCCESS(
            f'Connected WhatsApp for "{org.name}" ({org.id})'
        ))
        self.stdout.write(f"  phone_number_id: {result['phone_number_id']}")
        self.stdout.write(f"  waba_id: {result['waba_id']}")
