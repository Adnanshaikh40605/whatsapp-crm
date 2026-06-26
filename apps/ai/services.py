"""AI services for agents, workflow generation, and business insights."""

import re
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone


INDUSTRY_AGENTS = {
    "driver_service": {
        "welcome": "Welcome to Driver On Hire! I'll help you book a driver.",
        "questions": ["Pickup Location", "Drop Location", "Date", "Time", "Hours Required"],
        "qualify_keywords": ["driver", "hire", "pickup", "drop", "airport", "ride"],
    },
    "pest_control": {
        "welcome": "Hi! I'm from Pest Control 99. What pest problem can we help with?",
        "questions": ["Location", "Property Type", "Pest Type", "Preferred Date"],
        "qualify_keywords": ["pest", "termite", "cockroach", "rodent", "inspection"],
    },
    "resort": {
        "welcome": "Welcome to Vacation BNA! Looking for a getaway?",
        "questions": ["Check-in Date", "Check-out Date", "Room Type", "Guests"],
        "qualify_keywords": ["book", "room", "villa", "weekend", "stay", "resort"],
    },
}


class AIAgentService:
    def __init__(self, organization):
        self.org = organization
        self.config = organization.ai_config or {}
        self.profile = INDUSTRY_AGENTS.get(organization.industry, {})

    def chat(self, message: str, industry: str = "") -> dict:
        msg = message.lower().strip()
        welcome = self.config.get("welcome_message") or self.profile.get("welcome", "How can I help you today?")
        collected = self._extract_info(msg)

        if any(w in msg for w in ["price", "cost", "rate", "charge", "how much"]):
            return {
                "reply": "I can share pricing based on your requirements. " + self._next_question(collected),
                "intent": "pricing",
                "create_lead": False,
                "lead_score_delta": 15,
            }

        if any(w in msg for w in ["book", "appointment", "schedule", "visit", "callback"]):
            return {
                "reply": "Happy to schedule! " + self._next_question(collected),
                "intent": "booking",
                "create_lead": True,
                "lead_title": f"Booking inquiry — {self.org.name}",
                "lead_score_delta": 25,
            }

        if self._is_qualified(msg, collected):
            return {
                "reply": "Perfect! I've noted your details. Our team will confirm shortly. Thank you!",
                "intent": "qualified",
                "create_lead": True,
                "lead_title": f"Qualified lead — {self.org.name}",
                "lead_score_delta": 40,
            }

        if any(w in msg for w in self.profile.get("qualify_keywords", [])):
            return {
                "reply": self._next_question(collected),
                "intent": "qualifying",
                "create_lead": False,
                "lead_score_delta": 20,
            }

        return {
            "reply": welcome,
            "intent": "general",
            "create_lead": False,
            "lead_score_delta": 5,
        }

    def _extract_info(self, msg: str) -> dict:
        info = {}
        if re.search(r"\b(mumbai|pune|thane|delhi|airport)\b", msg):
            info["location"] = True
        if re.search(r"\b(today|tomorrow|monday|tuesday|weekend|\d{1,2}[/-]\d{1,2})\b", msg):
            info["date"] = True
        if re.search(r"\b(\d{1,2}\s*(am|pm|:\d{2}))\b", msg):
            info["time"] = True
        if re.search(r"\b(1 bhk|2 bhk|3 bhk|villa|suite|deluxe)\b", msg):
            info["property"] = True
        return info

    def _is_qualified(self, msg: str, collected: dict) -> bool:
        questions = self.profile.get("questions", [])
        if not questions:
            return False
        return len(collected) >= min(2, len(questions))

    def _next_question(self, collected: dict) -> str:
        questions = self.profile.get("questions", ["What service do you need?", "Your location?"])
        for q in questions:
            key = q.lower().split()[0]
            if key not in str(collected).lower():
                return f"Could you share your {q}?"
        return "Anything else you'd like to add?"


class AIWorkflowGenerator:
    @staticmethod
    def generate(prompt: str, organization) -> dict:
        prompt_lower = prompt.lower()
        steps = []

        if "day" in prompt_lower or "follow" in prompt_lower:
            days = 7
            match = re.search(r"(\d+)\s*day", prompt_lower)
            if match:
                days = int(match.group(1))
            for i in range(days):
                steps.append({
                    "day": i + 1,
                    "delay_days": 1 if i > 0 else 0,
                    "message": AIWorkflowGenerator._day_message(i + 1, organization.industry),
                    "stop_on_reply": True,
                })
            return {
                "name": f"Follow-up sequence ({days} days)",
                "type": "follow_up_sequence",
                "steps": steps,
                "trigger": "no_reply",
            }

        if "welcome" in prompt_lower or "new lead" in prompt_lower:
            return {
                "name": "New Lead Welcome Workflow",
                "type": "workflow",
                "trigger": "new_lead",
                "actions": [
                    {"type": "send_message", "message": "Thanks for reaching out! We'll get back to you shortly."},
                    {"type": "add_tag", "tag": "new_lead"},
                ],
            }

        if "campaign" in prompt_lower and "click" in prompt_lower:
            return {
                "name": "Campaign Click Follow-up",
                "type": "workflow",
                "trigger": "campaign_clicked",
                "actions": [
                    {"type": "send_message", "message": "Thanks for your interest! Can I help you with more details?"},
                    {"type": "add_tag", "tag": "campaign_clicked"},
                ],
            }

        return {
            "name": "Custom Automation",
            "type": "workflow",
            "trigger": "new_message",
            "actions": [{"type": "send_welcome"}],
            "description": f"Generated from: {prompt[:100]}",
        }

    @staticmethod
    def _day_message(day: int, industry: str) -> str:
        messages = {
            1: "Thank you for your interest! We're here to help.",
            2: "Just checking in — did you have any questions?",
            3: "We have a special offer running this week. Interested?",
            5: "Last chance to avail our exclusive offer!",
            7: "Final follow-up from our team. Reply anytime!",
        }
        if industry == "pest_control" and day == 3:
            return "Monsoon pest control offer — 20% off! Reply YES to book."
        if industry == "resort" and day == 3:
            return "Weekend villa availability — reply BOOK for details!"
        return messages.get(day, f"Follow-up day {day} — we're here if you need us!")


class AIBusinessInsights:
    @staticmethod
    def generate(organization) -> dict:
        from apps.crm.models import Lead, Contact
        from apps.campaigns.models import Campaign
        from apps.inbox.models import Conversation, Message

        now = timezone.now()
        week_ago = now - timedelta(days=7)

        hot_leads = Lead.objects.filter(
            organization=organization, is_archived=False, score__gte=50,
        ).count()

        missed_leads = Conversation.objects.filter(
            organization=organization,
            unread_count__gt=0,
            status=Conversation.Status.OPEN,
        ).count()

        stale_leads = Lead.objects.filter(
            organization=organization,
            is_archived=False,
            updated_at__lt=week_ago,
        ).exclude(
            stage__is_won=True,
        ).count()

        best_campaign = (
            Campaign.objects.filter(organization=organization, is_archived=False)
            .order_by("-read_count", "-reply_count")
            .first()
        )

        follow_up_opportunities = Lead.objects.filter(
            organization=organization,
            is_archived=False,
            stage__name__in=["Follow-Up", "Interested", "New Lead"],
        ).count()

        suggestions = []
        if missed_leads > 0:
            suggestions.append(f"Reply to {missed_leads} unread conversations to recover leads")
        if stale_leads > 0:
            suggestions.append(f"Start follow-up sequences for {stale_leads} stale leads")
        if hot_leads > 0:
            suggestions.append(f"Prioritize {hot_leads} hot leads — assign senior agents")
        if not suggestions:
            suggestions.append("Launch a bulk campaign to re-engage inactive contacts")

        return {
            "missed_leads": missed_leads,
            "hot_leads": hot_leads,
            "follow_up_opportunities": follow_up_opportunities,
            "stale_leads": stale_leads,
            "best_campaign": {
                "name": best_campaign.name if best_campaign else None,
                "read_count": best_campaign.read_count if best_campaign else 0,
                "reply_count": best_campaign.reply_count if best_campaign else 0,
            },
            "conversion_suggestions": suggestions,
            "revenue_opportunities": [
                "Send promotional campaign to contacts inactive 30+ days",
                "Enable AI agent on all open conversations",
                "Activate 5-day follow-up sequence for new leads",
            ],
            "total_contacts": Contact.objects.filter(organization=organization).count(),
        }
