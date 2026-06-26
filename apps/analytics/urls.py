from django.urls import path

from apps.analytics.views import AgentPerformanceView, ExecutiveDashboardView

urlpatterns = [
    path("dashboard/", ExecutiveDashboardView.as_view(), name="analytics-dashboard"),
    path("agents/", AgentPerformanceView.as_view(), name="agent-performance"),
]
