from django.urls import path

from apps.sms_crm.views import (
    SMSCRMApiSettingsView,
    SMSCRMDashboardView,
    SMSCRMMessageLogView,
    SMSCRMSendMessageView,
)

urlpatterns = [
    path("dashboard/", SMSCRMDashboardView.as_view(), name="sms-crm-dashboard"),
    path("api-settings/", SMSCRMApiSettingsView.as_view(), name="sms-crm-api-settings"),
    path("messages/send/", SMSCRMSendMessageView.as_view(), name="sms-crm-send"),
    path("messages/logs/", SMSCRMMessageLogView.as_view(), name="sms-crm-message-logs"),
]
