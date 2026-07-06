import json

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.inbox.models import Message
from apps.organizations.models import Organization

GRAPH_API = "https://graph.facebook.com/v21.0"


class Command(BaseCommand):
    help = "Query Meta Graph API and print webhook integration evidence (no secrets)."

    def handle(self, *args, **options):
        app_id = settings.META_APP_ID
        app_secret = settings.META_APP_SECRET
        expected_app_id = app_id

        self.stdout.write("=== WhatsFlow Meta Integration Evidence ===\n")
        self.stdout.write(f"Configured META_APP_ID: {app_id or '(missing)'}")
        self.stdout.write(f"WHATSAPP_WEBHOOK_URL: {settings.WHATSAPP_WEBHOOK_URL}")
        self.stdout.write(f"WHATSAPP_VERIFY_TOKEN: {settings.WHATSAPP_VERIFY_TOKEN}")

        inbound = Message.objects.filter(direction=Message.Direction.INBOUND).count()
        outbound = Message.objects.filter(direction=Message.Direction.OUTBOUND).count()
        self.stdout.write(f"DB messages — inbound: {inbound}, outbound: {outbound}\n")

        orgs = Organization.objects.filter(
            is_active=True, whatsapp_connected=True
        ).exclude(whatsapp_phone_number_id="")

        if not orgs.exists():
            self.stdout.write(self.style.ERROR("No connected WhatsApp org found."))
            return

        for org in orgs:
            phone_id = org.whatsapp_phone_number_id
            waba_id = org.whatsapp_business_account_id
            token = org.whatsapp_access_token

            self.stdout.write(f"--- Org: {org.name} ---")
            self.stdout.write(f"phone_number_id: {phone_id}")
            self.stdout.write(f"waba_id: {waba_id}")
            self.stdout.write(f"access_token present: {bool(token)}\n")

            if token:
                debug = self._get(
                    f"{GRAPH_API}/debug_token",
                    params={"input_token": token, "access_token": f"{app_id}|{app_secret}"},
                )
                self._print_section("1) Access token debug (which app issued this token?)", debug)
                token_data = (debug.get("data") or {}) if debug.get("ok") else {}
                if token_data.get("app_id"):
                    match = str(token_data["app_id"]) == str(expected_app_id)
                    self.stdout.write(
                        f"   Token app_id={token_data['app_id']} "
                        f"matches configured META_APP_ID={expected_app_id}: {match}\n"
                    )

            phone = self._get(
                f"{GRAPH_API}/{phone_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "fields": (
                        "display_phone_number,verified_name,quality_rating,"
                        "code_verification_status,platform_type,status,name_status,"
                        "id"
                    ),
                },
            )
            self._print_section("2) Phone number (Graph API)", phone)

            if waba_id:
                waba = self._get(
                    f"{GRAPH_API}/{waba_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"fields": "id,name,account_review_status,message_template_namespace,owner_business_info"},
                )
                self._print_section("3) WABA details", waba)

                subscribed = self._get(
                    f"{GRAPH_API}/{waba_id}/subscribed_apps",
                    headers={"Authorization": f"Bearer {token}"},
                )
                self._print_section("4) WABA subscribed_apps (which apps receive webhooks?)", subscribed)
                self._check_app_in_subscribed(subscribed, expected_app_id)

            if app_id and app_secret:
                subs = self._get(
                    f"{GRAPH_API}/{app_id}/subscriptions",
                    params={"access_token": f"{app_id}|{app_secret}"},
                )
                self._print_section("5) App webhook subscriptions", subs)
                self._check_messages_field(subs)

            self.stdout.write("")

        self.stdout.write(
            "=== Next: send a test message from customer phone, then check Railway HTTP logs "
            "for POST /api/v1/onboarding/webhooks/whatsapp/ ==="
        )

    def _get(self, url, headers=None, params=None):
        try:
            resp = requests.get(url, headers=headers or {}, params=params or {}, timeout=25)
            try:
                body = resp.json()
            except ValueError:
                body = {"raw": resp.text[:500]}
            return {"ok": resp.ok, "status": resp.status_code, "body": body}
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)}

    def _print_section(self, title, result):
        self.stdout.write(title)
        if result.get("error"):
            self.stdout.write(self.style.ERROR(f"  request error: {result['error']}"))
            return
        status = result.get("status", "?")
        body = result.get("body", {})
        self.stdout.write(f"  HTTP {status}")
        self.stdout.write(json.dumps(body, indent=2, default=str))
        self.stdout.write("")

    def _check_app_in_subscribed(self, result, expected_app_id):
        if not result.get("ok"):
            self.stdout.write(self.style.WARNING("  Could not verify WABA subscribed_apps."))
            return
        body = result.get("body") or {}
        apps = body.get("data") or []
        ids = [str(a.get("id", a.get("whatsapp_business_api_data", {}).get("id", ""))) for a in apps]
        ids = [i for i in ids if i]
        if not ids and body.get("id"):
            ids = [str(body["id"])]
        found = str(expected_app_id) in ids or any(
            str(a.get("id")) == str(expected_app_id) for a in apps
        )
        self.stdout.write(
            f"  App {expected_app_id} in subscribed_apps: {found} (listed ids: {ids or 'none'})\n"
        )

    def _check_messages_field(self, result):
        if not result.get("ok"):
            self.stdout.write(self.style.WARNING("  Could not read app subscriptions."))
            return
        body = result.get("body") or {}
        items = body.get("data") or []
        for item in items:
            obj = item.get("object", "")
            callback = item.get("callback_url", "")
            fields = [f.get("name") for f in (item.get("fields") or []) if f.get("name")]
            active = item.get("active", item.get("subscribed_fields"))
            self.stdout.write(
                f"  object={obj} active={active} callback_url={callback} fields={fields}"
            )
            if "messages" in fields:
                self.stdout.write(self.style.SUCCESS("  messages field: SUBSCRIBED"))
            else:
                self.stdout.write(self.style.ERROR("  messages field: NOT FOUND in subscription"))
