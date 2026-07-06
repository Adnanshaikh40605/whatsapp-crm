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
                    "Confirm Meta Console: app is LIVE (not dev_mode) + messages field subscribed."
                )
            )

        app_id = settings.META_APP_ID
        if app_id and settings.META_APP_SECRET:
            try:
                import requests

                resp = requests.get(
                    f"https://graph.facebook.com/v21.0/{app_id}",
                    params={
                        "fields": "app_status,is_live",
                        "access_token": f"{app_id}|{settings.META_APP_SECRET}",
                    },
                    timeout=15,
                )
                if resp.ok:
                    data = resp.json()
                    self.stdout.write(
                        f"Meta app_status={data.get('app_status')} is_live={data.get('is_live')}"
                    )
                    if data.get("app_status") == "dev_mode" or not data.get("is_live"):
                        self.stdout.write(
                            self.style.ERROR(
                                "BLOCKER: Meta app is in dev_mode. Real customer webhooks "
                                "will NOT arrive until you switch the app to Live in Meta Console."
                            )
                        )
            except Exception as exc:
                self.stdout.write(f"Could not check Meta app mode: {exc}")
