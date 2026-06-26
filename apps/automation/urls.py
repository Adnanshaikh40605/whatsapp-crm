from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.automation.views import (
    BotFlowViewSet,
    BotReplyViewSet,
    FollowUpSequenceViewSet,
    WorkflowViewSet,
    WorkflowTemplatesView,
)

router = DefaultRouter()
router.register("workflows", WorkflowViewSet, basename="workflow")
router.register("follow-ups", FollowUpSequenceViewSet, basename="follow-up")
router.register("bot-flows", BotFlowViewSet, basename="bot-flow")
router.register("bot-replies", BotReplyViewSet, basename="bot-reply")

urlpatterns = [
    path("templates/", WorkflowTemplatesView.as_view(), name="workflow-templates"),
    path("", include(router.urls)),
]
