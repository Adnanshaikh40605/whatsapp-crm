from django.utils import timezone

from apps.automation.models import BotFlow, FollowUpSequence, Workflow
from apps.campaigns.models import WhatsAppTemplate
from apps.crm.models import PipelineStage
from apps.onboarding.data.industry_packs import DEFAULT_PIPELINE, INDUSTRY_AI_PROFILES, INDUSTRY_PACKS
from apps.onboarding.models import InstalledPack


class WorkspaceBootstrap:
    """Bootstrap CRM, inbox, and automations for a new organization."""

    def __init__(self, organization):
        self.org = organization

    def setup_default_pipeline(self):
        stages = []
        profile = INDUSTRY_AI_PROFILES.get(self.org.industry, {})
        stage_names = profile.get("pipeline_stages") or [s["name"] for s in DEFAULT_PIPELINE]

        for i, name in enumerate(stage_names):
            defaults = next((s for s in DEFAULT_PIPELINE if s["name"] == name), {})
            stage, _ = PipelineStage.objects.get_or_create(
                organization=self.org,
                name=name,
                defaults={
                    "order": i,
                    "color": defaults.get("color", "#6366f1"),
                    "is_won": name.lower() in ("won", "completed", "enrolled"),
                    "is_lost": name.lower() in ("lost", "cancelled"),
                },
            )
            stages.append(stage)
        return stages

    def setup_default_automations(self):
        Workflow.objects.get_or_create(
            organization=self.org,
            name="Auto-assign new leads",
            defaults={
                "trigger": Workflow.Trigger.NEW_LEAD,
                "flow_definition": {"actions": [{"type": "assign_round_robin"}]},
                "is_active": True,
            },
        )
        Workflow.objects.get_or_create(
            organization=self.org,
            name="Welcome message on new chat",
            defaults={
                "trigger": Workflow.Trigger.NEW_MESSAGE,
                "flow_definition": {"actions": [{"type": "send_welcome"}]},
                "is_active": True,
            },
        )


class PackInstaller:
    """One-click install industry automation packs."""

    def __init__(self, organization):
        self.org = organization

    def install(self, pack_id):
        pack = next((p for p in INDUSTRY_PACKS if p["id"] == pack_id), None)
        if not pack:
            raise ValueError(f"Pack {pack_id} not found")

        if InstalledPack.objects.filter(organization=self.org, pack_id=pack_id).exists():
            return {"status": "already_installed", "pack": pack["name"]}

        # Install pipeline stages
        for i, stage_name in enumerate(pack.get("pipeline_stages", [])):
            PipelineStage.objects.get_or_create(
                organization=self.org,
                name=stage_name,
                defaults={"order": i, "color": "#6366f1"},
            )

        # Install bot flows
        flows_created = []
        for flow_def in pack.get("flows", []):
            flow_data = self._build_flow_data(flow_def)
            flow, created = BotFlow.objects.get_or_create(
                organization=self.org,
                title=flow_def["title"],
                defaults={
                    "start_trigger": flow_def["trigger"],
                    "trigger_type": "keyword",
                    "is_active": True,
                    "flow_data": flow_data,
                },
            )
            if created:
                flows_created.append(flow.title)

        # Install templates
        templates_created = []
        for tpl in pack.get("templates", []):
            template, created = WhatsAppTemplate.objects.get_or_create(
                organization=self.org,
                name=tpl["name"],
                language="en_US",
                defaults={
                    "category": tpl["category"],
                    "status": "approved",
                    "body": tpl["body"],
                },
            )
            if created:
                templates_created.append(template.name)

        # Install follow-up sequence
        FollowUpSequence.objects.get_or_create(
            organization=self.org,
            name=f"{pack['name']} Follow-up",
            defaults={
                "steps": [
                    {"day": 1, "message": "Hi! Just following up on your inquiry. Can we help you further?"},
                    {"day": 3, "message": "We have a special offer for you! Reply YES to learn more."},
                    {"day": 7, "message": "Last chance! Book now and get priority service."},
                ],
                "is_active": True,
            },
        )

        InstalledPack.objects.create(
            organization=self.org,
            pack_id=pack_id,
            pack_name=pack["name"],
            industry=pack["industry"],
        )

        self.org.industry = pack["industry"]
        self.org.onboarding_data = {
            **self.org.onboarding_data,
            "installed_pack": pack_id,
            "welcome_message": pack.get("welcome_message", ""),
        }
        self.org.save()

        return {
            "status": "installed",
            "pack": pack["name"],
            "flows": flows_created,
            "templates": templates_created,
        }

    def _build_flow_data(self, flow_def):
        nodes = [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 50, "y": 200},
                "data": {"trigger": flow_def["trigger"]},
            }
        ]
        edges = []
        prev_id = "start"
        for i, step in enumerate(flow_def.get("steps", [])):
            node_id = f"step_{i}"
            nodes.append({
                "id": node_id,
                "type": "options" if step not in ("lead_capture", "confirm", "send_quote") else "lead",
                "position": {"x": 280 + i * 250, "y": 150},
                "data": {"title": step.replace("_", " ").title()},
            })
            edges.append({"id": f"e{i}", "source": prev_id, "target": node_id})
            prev_id = node_id
        return {"nodes": nodes, "edges": edges}


class AISetupAssistant:
    """Generate workspace configuration from business description."""

    INDUSTRY_KEYWORDS = {
        "pest_control": ["pest", "termite", "rodent", "cockroach", "fumigation", "insect"],
        "driver_service": ["driver", "cab", "taxi", "airport", "transfer", "chauffeur"],
        "real_estate": ["property", "real estate", "flat", "apartment", "bhk", "rent", "buy home"],
        "clinic": ["clinic", "hospital", "doctor", "medical", "health", "patient", "dental"],
        "resort": ["resort", "hotel", "hospitality", "booking", "vacation", "stay"],
        "education": ["education", "school", "college", "course", "training", "institute", "academy"],
    }

    def detect_industry(self, description: str) -> str:
        desc_lower = description.lower()
        scores = {}
        for industry, keywords in self.INDUSTRY_KEYWORDS.items():
            scores[industry] = sum(1 for kw in keywords if kw in desc_lower)
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "general"

    def generate_setup(self, organization, business_description: str, qualification_questions: list = None):
        industry = self.detect_industry(business_description)
        profile = INDUSTRY_AI_PROFILES.get(industry, INDUSTRY_AI_PROFILES.get("pest_control"))

        organization.industry = industry
        organization.ai_config = {
            "business_description": business_description,
            "industry": industry,
            "welcome_message": profile["welcome_message"],
            "qualification_questions": qualification_questions or profile["qualification_questions"],
            "ai_enabled": True,
            "human_takeover_after": 3,
        }
        organization.onboarding_data = {
            **organization.onboarding_data,
            "ai_generated": True,
            "tags": profile.get("tags", []),
        }
        organization.save()

        bootstrap = WorkspaceBootstrap(organization)
        bootstrap.setup_default_pipeline()

        # Create welcome bot flow
        BotFlow.objects.get_or_create(
            organization=organization,
            title=f"{industry.replace('_', ' ').title()} Welcome Flow",
            defaults={
                "start_trigger": "hi",
                "trigger_type": "keyword",
                "is_active": True,
                "flow_data": {
                    "nodes": [
                        {"id": "start", "type": "start", "position": {"x": 50, "y": 200}, "data": {"trigger": "hi"}},
                        {"id": "welcome", "type": "message", "position": {"x": 280, "y": 200}, "data": {"message": profile["welcome_message"]}},
                    ],
                    "edges": [{"id": "e1", "source": "start", "target": "welcome"}],
                },
            },
        )

        # Follow-up sequence
        follow_up_days = profile.get("follow_up_days", [1, 3, 7])
        FollowUpSequence.objects.get_or_create(
            organization=organization,
            name="AI Generated Follow-up",
            defaults={
                "steps": [
                    {"day": d, "message": f"Follow-up day {d}: Checking in on your inquiry. How can we help?"}
                    for d in follow_up_days
                ],
                "is_active": True,
            },
        )

        return {
            "industry": industry,
            "welcome_message": profile["welcome_message"],
            "pipeline_stages": profile["pipeline_stages"],
            "qualification_questions": organization.ai_config["qualification_questions"],
            "tags": profile.get("tags", []),
            "suggested_pack": industry,
        }


class AICampaignBuilder:
    """Generate campaign from natural language description."""

    def generate(self, organization, prompt: str):
        prompt_lower = prompt.lower()
        is_offer = any(w in prompt_lower for w in ["offer", "discount", "sale", "promo", "special"])
        is_reminder = any(w in prompt_lower for w in ["reminder", "follow", "followup"])
        is_seasonal = any(w in prompt_lower for w in ["monsoon", "summer", "winter", "festival", "diwali", "christmas"])

        industry = organization.industry or "general"
        service = industry.replace("_", " ")

        if is_seasonal:
            campaign_name = f"Seasonal {service.title()} Campaign"
            message = f"Special seasonal offer on {service}! Limited time discount. Reply YES to avail."
            template_name = f"seasonal_{industry}_offer"
        elif is_offer:
            campaign_name = f"{service.title()} Special Offer"
            message = f"Exclusive offer on {service}! Get up to 20% off. Book now — limited slots available."
            template_name = f"{service.replace(' ', '_')}_offer"
        elif is_reminder:
            campaign_name = f"{service.title()} Reminder Campaign"
            message = f"Hi {{{{1}}}}, this is a friendly reminder about your pending {service} inquiry. Reply to continue."
            template_name = f"{service.replace(' ', '_')}_reminder"
        else:
            campaign_name = prompt[:60].title()
            message = f"Hello {{{{1}}}}! {prompt}. Reply for more details."
            template_name = f"campaign_{organization.slug[:20]}"

        return {
            "campaign_name": campaign_name,
            "message_content": message,
            "template": {
                "name": template_name,
                "category": "marketing" if is_offer or is_seasonal else "utility",
                "body": message,
                "language": "en_US",
            },
            "audience_filter": {"tags": [], "stage": None},
            "schedule_suggestion": "Send immediately for best engagement" if is_offer else "Schedule for tomorrow 10 AM",
            "follow_up_sequence": [
                {"day": 1, "message": "Did you see our message? Reply YES to learn more."},
                {"day": 3, "message": "Last chance for this offer! Don't miss out."},
            ],
            "cta_buttons": ["YES", "Tell me more", "Not interested"],
        }
