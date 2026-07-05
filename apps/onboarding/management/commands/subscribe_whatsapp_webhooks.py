from django.core.management.base import BaseCommand

from apps.onboarding.whatsapp import WhatsAppConnectService


class Command(BaseCommand):
    help = "Subscribe Meta app webhooks for WhatsApp inbound messages and delivery status."

    def handle(self, *args, **options):
        result = WhatsAppConnectService.subscribe_whatsapp_webhooks()
        if result.get("ok"):
            self.stdout.write(self.style.SUCCESS(f"Webhook subscription OK: {result}"))
        else:
            self.stdout.write(self.style.ERROR(f"Webhook subscription failed: {result}"))
