from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.ai.services import AIAgentService, AIBusinessInsights, AIWorkflowGenerator
from apps.automation.models import FollowUpSequence, Workflow
from apps.core.exceptions import APIResponse
from apps.core.models import get_current_organization
from apps.core.permissions import IsOrganizationMember
from apps.ai.models import AIAgentProfile
from apps.ai.serializers import AIAgentProfileSerializer
from apps.crm.models import Lead
from apps.inbox.models import Conversation


class AIAgentProfileListView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        org = get_current_organization()
        agents = AIAgentProfile.objects.filter(organization=org, is_active=True)
        serializer = AIAgentProfileSerializer(agents, many=True)
        
        # Calculate real stats from DB to replace dummy stats
        total_leads = Lead.objects.filter(organization=org, is_archived=False).count()
        appointments = Lead.objects.filter(organization=org, stage__is_won=True).count()
        convs = Conversation.objects.filter(organization=org, is_bot_active=True).count()

        data = serializer.data
        for idx, agent in enumerate(data):
            # Since agents share the org's leads right now, we approximate or just show org totals 
            # for the active agent, or split it if there are multiple. 
            # We'll just distribute them roughly for display or show total.
            agent["leads"] = total_leads
            agent["appointments"] = appointments
            agent["conversion"] = int((appointments / max(total_leads, 1)) * 100)
            agent["avgResponse"] = "1.2s" # This requires complex log parsing not yet available
            
        return APIResponse.success(data)

class AIAgentChatView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def post(self, request):
        org = get_current_organization()
        message = request.data.get("message", "")
        service = AIAgentService(org)
        response = service.chat(message, org.industry or "general")
        return APIResponse.success({
            "reply": response["reply"],
            "intent": response["intent"],
            "lead_score_delta": response.get("lead_score_delta", 0),
            "create_lead": response.get("create_lead", False),
        })


class AIConversationSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def post(self, request):
        messages = request.data.get("messages", [])
        if not messages:
            return APIResponse.error("No messages provided", status_code=400)
        summary = f"Conversation with {len(messages)} messages. "
        summary += f"Last: \"{messages[-1].get('content', '')[:100]}\". Recommend follow-up within 24h."
        return APIResponse.success({
            "summary": summary,
            "key_points": ["Customer inquired about services", "Positive engagement"],
            "recommended_action": "Send follow-up message within 24 hours",
            "priority": "high",
        })


class AIWorkflowGeneratorView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def post(self, request):
        org = get_current_organization()
        prompt = request.data.get("prompt", "")
        if not prompt:
            return APIResponse.error("Prompt is required", status_code=400)

        generated = AIWorkflowGenerator.generate(prompt, org)
        saved = None

        if generated["type"] == "follow_up_sequence":
            seq = FollowUpSequence.objects.create(
                organization=org,
                name=generated["name"],
                steps=generated["steps"],
                is_active=True,
            )
            saved = {"id": str(seq.id), "type": "follow_up_sequence"}
        elif generated["type"] == "workflow":
            wf = Workflow.objects.create(
                organization=org,
                name=generated["name"],
                trigger=generated.get("trigger", Workflow.Trigger.NEW_MESSAGE),
                flow_definition={"actions": generated.get("actions", [])},
                is_active=True,
                created_by=request.user,
            )
            saved = {"id": str(wf.id), "type": "workflow"}

        return APIResponse.success({**generated, "saved": saved}, message="Workflow generated")


class AIBusinessInsightsView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        org = get_current_organization()
        insights = AIBusinessInsights.generate(org)
        return APIResponse.success(insights)
