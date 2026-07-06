from django.core.management.base import BaseCommand
from django.conf import settings

from apps.inbox.models import Message
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = "Print inbox webhook health: env config, org linkage, message counts."

    def handle(self, *args, **options):
        self.stdout.write(f"WHATSAPP_WEBHOOK_URL: {settings.WHATSAPP_WEBHOOK_URL}")
        self.stdout.write(f"META_APP_ID set: {bool(settings.META_APP_ID)}")
        self.stdout.write(f"META_APP_SECRET set: {bool(settings.META_APP_SECRET)}")
        self.stdout.write(f"WHATSAPP_VERIFY_TOKEN: {settings.WHATSAPP_VERIFY_TOKEN}")

        inbound = Message.objects.filter(direction=Message.Direction.INBOUND).count()
        outbound = Message.objects.filter(direction=Message.Direction.OUTBOUND).count()
        self.stdout.write(f"Messages in DB — inbound: {inbound}, outbound: {outbound}")

        for org in Organization.objects.filter(is_active=True, whatsapp_connected=True):
            self.stdout.write(
                f"Org {org.name}: phone_number_id={org.whatsapp_phone_number_id} "
                f"waba={org.whatsapp_business_account_id}"
            )

        if inbound == 0:
            self.stdout.write(
                self.style.WARNING(
                    "No inbound messages in database. Meta is likely not delivering webhooks. "
                    "Confirm Meta Console: messages field subscribed + app published."
                )
            )
