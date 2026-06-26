"""Bot flow runtime and workflow automation engine."""

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


class BotFlowEngine:
    """Execute visual chatbot flows on inbound WhatsApp messages."""

    def __init__(self, organization, conversation, contact):
        self.org = organization
        self.conversation = conversation
        self.contact = contact
        self.session = conversation.metadata.get("bot_session", {})

    def handle_message(self, text: str, button_id: str = "") -> list[dict]:
        from apps.automation.models import BotFlow

        if not self.conversation.is_bot_active:
            return []

        flows = BotFlow.objects.filter(organization=self.org, is_active=True)
        active_flow_id = self.session.get("flow_id")

        if active_flow_id:
            flow = flows.filter(id=active_flow_id).first()
            if flow:
                return self._advance_flow(flow, text, button_id)

        for flow in flows:
            if self._matches_trigger(flow, text, button_id):
                self.session = {"flow_id": str(flow.id), "node_id": None, "answers": {}}
                return self._start_flow(flow)

        return self._try_ai_agent(text)

    def _matches_trigger(self, flow, text: str, button_id: str) -> bool:
        if flow.trigger_type == "any_message":
            return True
        if flow.trigger_type == "button_click" and button_id:
            return True
        if flow.trigger_type == "keyword":
            trigger = (flow.start_trigger or "").lower()
            return trigger in text.lower().split() or trigger in text.lower()
        return False

    def _start_flow(self, flow) -> list[dict]:
        nodes = flow.flow_data.get("nodes", [])
        edges = flow.flow_data.get("edges", [])
        start = next((n for n in nodes if n.get("type") == "start"), None)
        if not start:
            return []
        next_edge = next((e for e in edges if e["source"] == start["id"]), None)
        if not next_edge:
            return []
        next_node = next((n for n in nodes if n["id"] == next_edge["target"]), None)
        if not next_node:
            return []
        self.session["node_id"] = next_node["id"]
        self._save_session()
        return self._render_node(flow, next_node)

    def _advance_flow(self, flow, text: str, button_id: str) -> list[dict]:
        nodes = flow.flow_data.get("nodes", [])
        edges = flow.flow_data.get("edges", [])
        current_id = self.session.get("node_id")
        current = next((n for n in nodes if n["id"] == current_id), None)
        if not current:
            return self._start_flow(flow)

        answer = button_id or text
        self.session.setdefault("answers", {})[current_id] = answer

        next_id = None
        if current.get("type") == "options":
            for edge in edges:
                if edge["source"] == current_id:
                    next_id = edge["target"]
                    break
        else:
            edge = next((e for e in edges if e["source"] == current_id), None)
            next_id = edge["target"] if edge else None

        if not next_id:
            return self._complete_flow(flow)

        next_node = next((n for n in nodes if n["id"] == next_id), None)
        if not next_node:
            return self._complete_flow(flow)

        self.session["node_id"] = next_id
        self._save_session()
        return self._render_node(flow, next_node)

    def _render_node(self, flow, node: dict) -> list[dict]:
        data = node.get("data", {})
        node_type = node.get("type")

        if node_type == "lead":
            self._create_lead_from_answers(flow, data)
            self._complete_flow(flow)
            return [{"type": "text", "body": data.get("message", "Thank you! Our team will contact you shortly.")}]

        if node_type == "options":
            options = data.get("options", [])
            if len(options) <= 3:
                return [{
                    "type": "buttons",
                    "body": data.get("title", "Choose an option"),
                    "buttons": [{"id": f"opt_{i}", "title": opt} for i, opt in enumerate(options)],
                }]
            return [{
                "type": "list",
                "body": data.get("title", "Choose an option"),
                "button": "Select",
                "sections": [{"title": "Options", "rows": [
                    {"id": f"opt_{i}", "title": opt[:24], "description": ""} for i, opt in enumerate(options[:10])
                ]}],
            }]

        if node_type == "message":
            return [{"type": "text", "body": data.get("message", "")}]

        if node_type == "ai_agent":
            return self._try_ai_agent(data.get("prompt", ""))

        if node_type == "human_transfer":
            self.conversation.is_bot_active = False
            self.conversation.save(update_fields=["is_bot_active", "updated_at"])
            return [{"type": "text", "body": "Connecting you to a team member..."}]

        return [{"type": "text", "body": data.get("message", "How can I help you?")}]

    def _create_lead_from_answers(self, flow, data: dict):
        from apps.crm.models import Lead, PipelineStage

        stage = PipelineStage.objects.filter(organization=self.org).order_by("order").first()
        answers = self.session.get("answers", {})
        title = data.get("title") or f"Lead from {flow.title}"
        Lead.objects.create(
            organization=self.org,
            contact=self.contact,
            title=title,
            stage=stage,
            source="bot_flow",
            custom_fields={"flow_id": str(flow.id), "answers": answers},
        )

    def _complete_flow(self, flow):
        self.session = {}
        self._save_session()

    def _save_session(self):
        self.conversation.metadata = {**self.conversation.metadata, "bot_session": self.session}
        self.conversation.save(update_fields=["metadata", "updated_at"])

    def _try_ai_agent(self, text: str) -> list[dict]:
        from apps.ai.services import AIAgentService
        service = AIAgentService(self.org)
        result = service.chat(text, industry=self.org.industry)
        if result.get("create_lead"):
            self._create_lead_from_answers(
                type("Flow", (), {"id": "ai", "title": "AI Agent"})(),
                {"title": result.get("lead_title", "AI Qualified Lead")},
            )
        return [{"type": "text", "body": result["reply"]}]


class WorkflowEngine:
    """Dispatch automation workflows on platform events."""

    @staticmethod
    def dispatch(organization, trigger: str, context: dict):
        from apps.automation.models import Workflow

        workflows = Workflow.objects.filter(
            organization=organization, trigger=trigger, is_active=True,
        )
        for wf in workflows:
            WorkflowEngine._run(organization, wf, context)

    @staticmethod
    def _run(organization, workflow, context: dict):
        from apps.core.whatsapp_service import WhatsAppService

        actions = workflow.flow_definition.get("actions", [])
        wa = WhatsAppService(organization)

        for action in actions:
            action_type = action.get("type")
            if action_type == "send_message" and context.get("phone"):
                wa.send_text(context["phone"], action.get("message", "Hello!"))
            elif action_type == "send_welcome" and context.get("phone"):
                welcome = organization.ai_config.get("welcome_message", "Welcome! How can we help?")
                wa.send_text(context["phone"], welcome)
            elif action_type == "add_tag" and context.get("conversation_id"):
                from apps.inbox.models import Conversation
                conv = Conversation.objects.filter(id=context["conversation_id"]).first()
                if conv:
                    tags = list(conv.tags or [])
                    tag = action.get("tag", "automated")
                    if tag not in tags:
                        tags.append(tag)
                        conv.tags = tags
                        conv.save(update_fields=["tags", "updated_at"])
            elif action_type == "start_followup" and context.get("lead_id"):
                from apps.automation.tasks import start_followup_sequence
                seq_id = action.get("sequence_id")
                if seq_id:
                    start_followup_sequence.delay(str(seq_id), str(context["lead_id"]))

        workflow.run_count += 1
        workflow.save(update_fields=["run_count", "updated_at"])


class FollowUpRunner:
    """Execute follow-up sequence steps."""

    @staticmethod
    def process_due_executions():
        from apps.automation.models import FollowUpExecution

        now = timezone.now()
        due = FollowUpExecution.objects.filter(
            status=FollowUpExecution.Status.ACTIVE,
            next_run_at__lte=now,
        ).select_related("sequence", "lead__contact", "organization")

        for execution in due:
            FollowUpRunner._run_step(execution)

    @staticmethod
    def _run_step(execution):
        from apps.automation.models import FollowUpExecution
        from apps.core.whatsapp_service import WhatsAppService
        from apps.inbox.models import Conversation, Message

        steps = execution.sequence.steps or []
        step_idx = execution.current_step

        if step_idx >= len(steps):
            execution.status = FollowUpExecution.Status.COMPLETED
            execution.save(update_fields=["status", "updated_at"])
            return

        step = steps[step_idx]
        contact = execution.lead.contact
        phone = contact.phone

        conv = Conversation.objects.filter(organization=execution.organization, contact=contact).first()
        if conv:
            recent_reply = Message.objects.filter(
                conversation=conv,
                direction=Message.Direction.INBOUND,
                created_at__gte=execution.created_at,
            ).exists()
            if recent_reply and step.get("stop_on_reply", True):
                execution.status = FollowUpExecution.Status.CANCELLED
                execution.save(update_fields=["status", "updated_at"])
                return

        wa = WhatsAppService(execution.organization)
        message_body = step.get("message", "")
        if phone and message_body:
            wa.send_text(phone, message_body)

        execution.current_step += 1
        delay_days = step.get("delay_days", 1)
        if execution.current_step < len(steps):
            execution.next_run_at = timezone.now() + timedelta(days=delay_days)
        else:
            execution.status = FollowUpExecution.Status.COMPLETED
            execution.next_run_at = None
        execution.save(update_fields=["current_step", "next_run_at", "status", "updated_at"])
