from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.exceptions import APIResponse
from apps.core.permissions import IsOrganizationMember
from apps.inbox.models import Message
from apps.inbox.serializers import MessageSerializer


class WhatsAppCRMBaseView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]


class WhatsAppCRMDashboardView(WhatsAppCRMBaseView):
    def get(self, request):
        organization = request.organization
        status = organization.whatsapp_api_status if hasattr(organization, "whatsapp_api_status") else None
        if not status:
            if organization.whatsapp_phone_number_id and organization.whatsapp_business_account_id and organization.whatsapp_access_token:
                status = "live"
            elif organization.whatsapp_phone_number_id or organization.whatsapp_business_account_id or organization.whatsapp_connected:
                status = "pending"
            else:
                status = "not_connected"

        return APIResponse.success({
            "project": "WhatsApp CRM",
            "connection_status": status,
            "phone_number_id": organization.whatsapp_phone_number_id,
            "business_account_id": organization.whatsapp_business_account_id,
            "modules": [
                "Dashboard",
                "Templates",
                "Campaigns",
                "Contacts",
                "Contact Groups",
                "Message Logs",
                "Automation",
                "API Settings",
                "Reports",
            ],
        })


class WhatsAppCRMApiSettingsView(WhatsAppCRMBaseView):
    def get(self, request):
        organization = request.organization
        return APIResponse.success({
            "phone_number_id": organization.whatsapp_phone_number_id,
            "business_account_id": organization.whatsapp_business_account_id,
            "connected": organization.whatsapp_connected,
            "has_access_token": bool(organization.whatsapp_access_token),
        })


class WhatsAppCRMMessageLogView(WhatsAppCRMBaseView):
    def get(self, request):
        messages = Message.objects.filter(channel=Message.Channel.WHATSAPP).select_related("conversation", "sender")
        return APIResponse.success(MessageSerializer(messages, many=True).data)
