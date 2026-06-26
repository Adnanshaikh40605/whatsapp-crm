from django.urls import path

from apps.whatsapp_crm.views import (
    WhatsAppCRMApiSettingsView,
    WhatsAppCRMDashboardView,
    WhatsAppCRMMessageLogView,
)

urlpatterns = [
    path("dashboard/", WhatsAppCRMDashboardView.as_view(), name="whatsapp-crm-dashboard"),
    path("api-settings/", WhatsAppCRMApiSettingsView.as_view(), name="whatsapp-crm-api-settings"),
    path("messages/logs/", WhatsAppCRMMessageLogView.as_view(), name="whatsapp-crm-message-logs"),
]
