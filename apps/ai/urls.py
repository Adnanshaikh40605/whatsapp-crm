from django.urls import path

from apps.ai.views import (
    AIAgentChatView,
    AIBusinessInsightsView,
    AIConversationSummaryView,
    AIWorkflowGeneratorView,
    AIAgentProfileListView,
)

urlpatterns = [
    path("agents/", AIAgentProfileListView.as_view(), name="ai-agents"),
    path("chat/", AIAgentChatView.as_view(), name="ai-chat"),
    path("summarize/", AIConversationSummaryView.as_view(), name="ai-summarize"),
    path("workflow/generate/", AIWorkflowGeneratorView.as_view(), name="ai-workflow-generate"),
    path("insights/", AIBusinessInsightsView.as_view(), name="ai-insights"),
]
