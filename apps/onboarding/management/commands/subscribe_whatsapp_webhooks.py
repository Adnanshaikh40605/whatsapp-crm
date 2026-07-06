from django.core.management.base import BaseCommand

from apps.onboarding.whatsapp import WhatsAppConnectService
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = "Subscribe Meta app + WABA webhooks for WhatsApp inbound messages and delivery status."

    def handle(self, *args, **options):
        app_result = WhatsAppConnectService.subscribe_whatsapp_webhooks()
        if app_result.get("ok"):
            self.stdout.write(self.style.SUCCESS(f"App webhook subscription OK: {app_result}"))
        else:
            self.stdout.write(self.style.ERROR(f"App webhook subscription failed: {app_result}"))

        orgs = Organization.objects.filter(
            whatsapp_connected=True,
            is_active=True,
        ).exclude(whatsapp_business_account_id="")

        for org in orgs:
            waba_result = WhatsAppConnectService.subscribe_waba_to_app(org)
            if waba_result.get("ok"):
                self.stdout.write(self.style.SUCCESS(f"WABA subscribed: {org.name} -> {waba_result}"))
            else:
                self.stdout.write(self.style.WARNING(f"WABA subscribe skipped/failed: {org.name} -> {waba_result}"))
