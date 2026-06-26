from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.exceptions import APIResponse
from apps.core.permissions import IsOrganizationMember
from apps.automation.models import BotFlow, BotReply, FollowUpSequence, Workflow
from apps.automation.serializers import (
    BotFlowListSerializer,
    BotFlowSerializer,
    BotReplySerializer,
    FollowUpSequenceSerializer,
    WorkflowSerializer,
)


from rest_framework.views import APIView

class WorkflowTemplatesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        templates = {
            "follow_ups": [
                {
                    "id": "default_5_day",
                    "name": "5-Day Follow-Up",
                    "steps": [
                        {"day": 1, "delay_days": 0, "message": "Thank you for your interest! We are here to help.", "stop_on_reply": True},
                        {"day": 2, "delay_days": 1, "message": "Just checking in — any questions we can answer?", "stop_on_reply": True},
                        {"day": 3, "delay_days": 1, "message": "Special offer running this week! Reply YES to learn more.", "stop_on_reply": True},
                        {"day": 5, "delay_days": 2, "message": "Last chance for this offer. Our team is ready to assist!", "stop_on_reply": True},
                    ]
                }
            ],
            "bot_flows": [
                {
                    "id": "welcome_bot",
                    "name": "Welcome Bot",
                    "description": "Standard welcome flow"
                }
            ]
        }
        return APIResponse.success(templates)

class WorkflowViewSet(viewsets.ModelViewSet):
    serializer_class = WorkflowSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ["trigger", "is_active"]

    def get_queryset(self):
        return Workflow.objects.all()

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.organization,
            created_by=self.request.user,
        )


class FollowUpSequenceViewSet(viewsets.ModelViewSet):
    serializer_class = FollowUpSequenceSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get_queryset(self):
        return FollowUpSequence.objects.all()

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)


class BotFlowViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ["is_active", "trigger_type"]
    search_fields = ["title", "start_trigger"]

    def get_serializer_class(self):
        if self.action == "list":
            return BotFlowListSerializer
        return BotFlowSerializer

    def get_queryset(self):
        return BotFlow.objects.prefetch_related("replies").all()

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.organization,
            created_by=self.request.user,
        )

    @action(detail=True, methods=["post"])
    def toggle_status(self, request, pk=None):
        flow = self.get_object()
        flow.is_active = not flow.is_active
        flow.save(update_fields=["is_active", "updated_at"])
        return APIResponse.success(BotFlowSerializer(flow).data)

    @action(detail=True, methods=["post"])
    def save_flow(self, request, pk=None):
        flow = self.get_object()
        flow.flow_data = request.data.get("flow_data", {})
        flow.save(update_fields=["flow_data", "updated_at"])
        return APIResponse.success(BotFlowSerializer(flow).data, message="Flow saved")


class BotReplyViewSet(viewsets.ModelViewSet):
    serializer_class = BotReplySerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ["bot_flow", "reply_type"]

    def get_queryset(self):
        return BotReply.objects.select_related("bot_flow").all()

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)
