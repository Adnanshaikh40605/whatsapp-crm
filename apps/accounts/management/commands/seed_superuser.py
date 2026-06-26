from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from apps.automation.models import BotFlow, BotReply
from apps.campaigns.models import Campaign, WhatsAppTemplate
from apps.crm.models import PipelineStage
from apps.onboarding.services import WorkspaceBootstrap
from apps.organizations.models import Organization, OrganizationMembership

User = get_user_model()

COMPANIES = [
    {
        "name": "Driver On Hire",
        "slug": "driver-on-hire",
        "industry": "driver_service",
        "templates": [
            {"name": "driver_booking_confirm", "category": "utility", "body": "Your ride is confirmed! Driver {{1}} arrives at {{2}}."},
            {"name": "driver_arriving", "category": "utility", "body": "Driver is 5 min away. Vehicle: {{1}}, Contact: {{2}}."},
        ],
        "flow": {
            "title": "Driver Booking Flow",
            "trigger": "book",
            "nodes": [
                {"id": "start", "type": "start", "position": {"x": 50, "y": 200}, "data": {"trigger": "book"}},
                {"id": "pickup", "type": "options", "position": {"x": 280, "y": 200}, "data": {"title": "Pickup Location", "options": ["Mumbai", "Pune", "Airport"]}},
                {"id": "confirm", "type": "lead", "position": {"x": 530, "y": 200}, "data": {"title": "Booking Confirmed", "message": "We'll assign a driver shortly!"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "pickup"},
                {"id": "e2", "source": "pickup", "target": "confirm"},
            ],
        },
    },
    {
        "name": "Pest Control 99",
        "slug": "pest-control-99",
        "industry": "pest_control",
        "templates": [
            {"name": "pest_inspection_booking", "category": "utility", "body": "Hi {{1}}, inspection confirmed for {{2}} at {{3}}."},
            {"name": "pest_monsoon_offer", "category": "marketing", "body": "Monsoon Special! 20% off termite treatment. Reply YES to book."},
            {"name": "customer_service_inquiry", "category": "utility", "body": "Hello {{1}}, how can we help with your pest problem today?"},
        ],
        "flow": {
            "title": "Pest Control Lead Flow",
            "trigger": "hi",
            "nodes": [
                {"id": "start", "type": "start", "position": {"x": 50, "y": 200}, "data": {"trigger": "hi"}},
                {"id": "location", "type": "options", "position": {"x": 280, "y": 150}, "data": {"title": "Select Location", "options": ["Mumbai", "Pune", "Thane"]}},
                {"id": "services", "type": "options", "position": {"x": 530, "y": 100}, "data": {"title": "Mumbai Services", "options": ["Termite", "Rodent", "Cockroach"]}},
                {"id": "property", "type": "options", "position": {"x": 780, "y": 150}, "data": {"title": "Property Type", "options": ["1 BHK", "2 BHK", "3 BHK"]}},
                {"id": "lead", "type": "lead", "position": {"x": 1030, "y": 200}, "data": {"title": "Lead Confirmation", "message": "Thank you! Our team will contact you shortly."}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "location"},
                {"id": "e2", "source": "location", "target": "services"},
                {"id": "e3", "source": "services", "target": "property"},
                {"id": "e4", "source": "property", "target": "lead"},
            ],
        },
    },
    {
        "name": "Vacation BNA",
        "slug": "vacation-bna",
        "industry": "resort",
        "templates": [
            {"name": "resort_booking_confirm", "category": "utility", "body": "Booking confirmed! Ref: {{1}}. Check-in: {{2}}. Total: {{3}}."},
            {"name": "resort_availability", "category": "marketing", "body": "Rooms available for {{1}}! Starting at {{2}}/night. Reply BOOK to reserve."},
        ],
        "flow": {
            "title": "Resort Booking Flow",
            "trigger": "book",
            "nodes": [
                {"id": "start", "type": "start", "position": {"x": 50, "y": 200}, "data": {"trigger": "book"}},
                {"id": "dates", "type": "options", "position": {"x": 280, "y": 200}, "data": {"title": "Select Dates", "options": ["This Weekend", "Next Week", "Custom Dates"]}},
                {"id": "room", "type": "options", "position": {"x": 530, "y": 200}, "data": {"title": "Room Type", "options": ["Deluxe", "Suite", "Villa"]}},
                {"id": "confirm", "type": "lead", "position": {"x": 780, "y": 200}, "data": {"title": "Booking Inquiry", "message": "We'll send availability and pricing shortly!"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "dates"},
                {"id": "e2", "source": "dates", "target": "room"},
                {"id": "e3", "source": "room", "target": "confirm"},
            ],
        },
    },
]

DEFAULT_STAGES = [
    ("New Lead", "#6366f1", False, False),
    ("Qualified", "#8b5cf6", False, False),
    ("Interested", "#a855f7", False, False),
    ("Follow-Up", "#d946ef", False, False),
    ("Won", "#22c55e", True, False),
    ("Lost", "#ef4444", False, True),
]


class Command(BaseCommand):
    help = "Seed internal multi-company setup: owner account + all businesses"

    def handle(self, *args, **options):
        email = "test@gmail.com"
        password = "1234"

        # Deactivate legacy single-tenant seed org
        Organization.objects.filter(slug="test-org").update(is_active=False)

        owner, _ = User.objects.get_or_create(
            email=email,
            defaults={"first_name": "test", "last_name": "", "is_staff": True, "is_superuser": True},
        )
        owner.first_name = "test"
        owner.last_name = ""
        owner.set_password(password)
        owner.is_staff = True
        owner.is_superuser = True
        owner.save()

        for i, company_data in enumerate(COMPANIES):
            org, created = Organization.objects.update_or_create(
                slug=company_data["slug"],
                defaults={
                    "name": company_data["name"],
                    "owner": owner,
                    "industry": company_data["industry"],
                    "plan": Organization.Plan.INTERNAL,
                    "onboarding_completed": True,
                    "whatsapp_connected": False,
                },
            )

            OrganizationMembership.objects.update_or_create(
                organization=org,
                user=owner,
                defaults={
                    "role": OrganizationMembership.Role.OWNER,
                    "is_active": True,
                    "is_default": i == 0,
                },
            )

            bootstrap = WorkspaceBootstrap(org)
            if created or not PipelineStage.objects.filter(organization=org).exists():
                for order, (name, color, is_won, is_lost) in enumerate(DEFAULT_STAGES):
                    PipelineStage.objects.get_or_create(
                        organization=org, name=name,
                        defaults={"order": order, "color": color, "is_won": is_won, "is_lost": is_lost},
                    )
                bootstrap.setup_default_automations()

            for tpl in company_data["templates"]:
                WhatsAppTemplate.objects.update_or_create(
                    organization=org, name=tpl["name"], language="en_US",
                    defaults={"category": tpl["category"], "status": "approved", "body": tpl["body"]},
                )

            flow_def = company_data["flow"]
            flow, _ = BotFlow.objects.update_or_create(
                organization=org, title=flow_def["title"],
                defaults={
                    "start_trigger": flow_def["trigger"],
                    "trigger_type": "keyword",
                    "is_active": True,
                    "flow_data": {"nodes": flow_def["nodes"], "edges": flow_def["edges"]},
                    "created_by": owner,
                },
            )

            BotReply.objects.filter(organization=org, bot_flow=flow).delete()
            for node in flow_def["nodes"]:
                if node["type"] == "start":
                    continue
                BotReply.objects.create(
                    organization=org, bot_flow=flow, node_id=node["id"],
                    title=node["data"].get("title", node["id"]),
                    reply_type="interactive" if node["type"] == "options" else "simple",
                    content=node["data"].get("message", ""),
                    options=node["data"].get("options", []),
                    position_x=node["position"]["x"], position_y=node["position"]["y"],
                )

            tpl = WhatsAppTemplate.objects.filter(organization=org).first()
            if tpl:
                Campaign.objects.update_or_create(
                    organization=org, name=f"{org.slug}_welcome_campaign",
                    defaults={
                        "template": tpl, "status": "executed",
                        "total_recipients": 10, "sent_count": 10,
                        "delivered_count": 9, "read_count": 7,
                        "created_by": owner,
                    },
                )

            self.stdout.write(self.style.SUCCESS(f"  ✓ {org.name} ({org.industry})"))

        self.stdout.write(self.style.SUCCESS(f"\nInternal multi-company setup complete"))
        self.stdout.write(self.style.SUCCESS(f"Owner login: {owner.first_name} / {password}"))
        self.stdout.write(self.style.SUCCESS(f"Companies: {', '.join(c['name'] for c in COMPANIES)}"))
