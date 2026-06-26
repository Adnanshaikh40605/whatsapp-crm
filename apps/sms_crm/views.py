from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.exceptions import APIResponse
from apps.core.permissions import IsOrganizationMember
from apps.crm.models import Contact
from apps.inbox.models import Conversation, Message
from apps.inbox.serializers import MessageSerializer, SendSMSSerializer
from apps.inbox.tasks import send_sms_message


class SMSCRMBaseView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]


class SMSCRMDashboardView(SMSCRMBaseView):
    def get(self, request):
        settings = request.organization.settings.get("sms_crm", {})
        return APIResponse.success({
            "project": "SMS CRM",
            "connection_status": "configured" if settings.get("api_key") else "setup_required",
            "provider": settings.get("provider", "smartping"),
            "dlt_required": True,
            "steps": [
                "Register entity on DLT and collect Entity ID / PE ID.",
                "Approve sender IDs / headers on DLT.",
                "Register every SMS template and map DLT Template IDs.",
                "Connect Smartping/API credentials in SMS CRM settings.",
                "Send a one-contact test and verify provider delivery logs.",
            ],
        })


class SMSCRMApiSettingsView(SMSCRMBaseView):
    def get(self, request):
        settings = request.organization.settings.get("sms_crm", {})
        safe_settings = {key: value for key, value in settings.items() if key not in {"api_key", "auth_token"}}
        safe_settings["has_api_key"] = bool(settings.get("api_key"))
        safe_settings["has_auth_token"] = bool(settings.get("auth_token"))
        return APIResponse.success(safe_settings)

    def patch(self, request):
        existing = dict(request.organization.settings or {})
        sms_settings = dict(existing.get("sms_crm", {}))
        allowed = {
            "provider",
            "base_url",
            "route",
            "api_key",
            "auth_token",
            "entity_id",
            "default_sender_id",
            "delivery_callback_url",
        }
        for key in allowed:
            if key in request.data:
                sms_settings[key] = request.data.get(key)
        existing["sms_crm"] = sms_settings
        request.organization.settings = existing
        request.organization.save(update_fields=["settings", "updated_at"])
        return APIResponse.success({"saved": True}, message="SMS CRM API settings saved")


class SMSCRMSendMessageView(SMSCRMBaseView):
    def post(self, request):
        serializer = SendSMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        contact = self._get_or_create_contact(request, data)
        conversation, _ = Conversation.objects.get_or_create(
            organization=request.organization,
            contact=contact,
            defaults={"status": Conversation.Status.OPEN, "metadata": {"project": "sms_crm"}},
        )
        message = Message.objects.create(
            organization=request.organization,
            conversation=conversation,
            channel=Message.Channel.SMS,
            direction=Message.Direction.OUTBOUND,
            message_type=Message.MessageType.TEXT,
            content=data["content"],
            sender=request.user,
            metadata={"sms_to": contact.phone, "project": "sms_crm"},
        )
        now = timezone.now()
        conversation.last_message_at = now
        conversation.last_message_preview = message.content[:255]
        conversation.save(update_fields=["last_message_at", "last_message_preview", "updated_at"])
        contact.last_contacted_at = now
        contact.save(update_fields=["last_contacted_at", "updated_at"])
        send_sms_message.delay(str(message.id))
        return APIResponse.success(
            MessageSerializer(message).data,
            message="SMS queued",
            status_code=status.HTTP_201_CREATED,
        )

    def _get_or_create_contact(self, request, data):
        if data.get("contact_id"):
            contact = Contact.objects.filter(id=data["contact_id"], organization=request.organization).first()
            if not contact:
                raise ValidationError({"contact_id": "Contact not found."})
            return contact
        phone = self._normalize_phone(data.get("phone", ""))
        if not phone:
            raise ValidationError({"phone": "Phone number is required."})
        contact, _ = Contact.objects.update_or_create(
            organization=request.organization,
            phone=phone,
            defaults={
                "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "source": Contact.Source.MANUAL,
                "is_active": True,
            },
        )
        return contact

    def _normalize_phone(self, value):
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        if len(digits) == 10:
            return f"91{digits}"
        if digits.startswith("00"):
            return digits[2:]
        return digits


class SMSCRMMessageLogView(SMSCRMBaseView):
    def get(self, request):
        messages = Message.objects.filter(channel=Message.Channel.SMS).select_related("conversation", "sender")
        return APIResponse.success(MessageSerializer(messages, many=True).data)
