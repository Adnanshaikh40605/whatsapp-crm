from django.db.models import DurationField, ExpressionWrapper, F
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.core.exceptions import APIResponse
from apps.core.permissions import IsOrganizationMember
from apps.crm.models import Contact
from apps.inbox.models import CannedReply, Conversation, Message
from apps.inbox.realtime import broadcast_conversation_updated, broadcast_outbound_queued
from apps.inbox.serializers import (
    CannedReplySerializer,
    ConversationSerializer,
    MessageSerializer,
    SendSMSSerializer,
)
from apps.inbox.tasks import send_sms_message, send_whatsapp_message


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ["status", "assigned_to", "is_bot_active"]
    search_fields = ["contact__first_name", "contact__phone"]
    ordering_fields = ["last_message_at", "created_at"]

    def get_queryset(self):
        qs = Conversation.objects.select_related("contact", "assigned_to").all()
        delivery_status = self.request.query_params.get("delivery_status")
        if delivery_status:
            qs = qs.filter(last_outbound_status=delivery_status)
        return qs

    def perform_create(self, serializer):
        contact_id = serializer.validated_data.pop("contact_id")
        contact = Contact.objects.get(id=contact_id)
        serializer.save(organization=self.request.organization, contact=contact)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        conversation = self.get_object()
        user_id = request.data.get("user_id")
        conversation.assigned_to_id = user_id
        conversation.save(update_fields=["assigned_to", "updated_at"])
        return APIResponse.success(ConversationSerializer(conversation).data)

    @action(detail=True, methods=["post"])
    def takeover(self, request, pk=None):
        conversation = self.get_object()
        conversation.is_bot_active = False
        conversation.assigned_to = request.user
        conversation.save(update_fields=["is_bot_active", "assigned_to", "updated_at"])
        return APIResponse.success(
            ConversationSerializer(conversation).data,
            message="Human takeover activated",
        )

    @action(detail=True, methods=["post"])
    def add_tag(self, request, pk=None):
        conversation = self.get_object()
        tag = request.data.get("tag", "").strip()
        if tag:
            tags = list(conversation.tags or [])
            if tag not in tags:
                tags.append(tag)
                conversation.tags = tags
                conversation.save(update_fields=["tags", "updated_at"])
        return APIResponse.success(ConversationSerializer(conversation).data)

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        conversation = self.get_object()
        conversation.unread_count = 0
        conversation.save(update_fields=["unread_count", "updated_at"])
        broadcast_conversation_updated(str(request.organization.id), conversation)
        return APIResponse.success(ConversationSerializer(conversation).data)

    @action(detail=True, methods=["get"], url_path="message-analytics")
    def message_analytics(self, request, pk=None):
        conversation = self.get_object()
        outbound = Message.objects.filter(
            conversation=conversation,
            direction=Message.Direction.OUTBOUND,
            is_internal_note=False,
        )
        total_sent = outbound.exclude(status=Message.Status.PENDING).count()
        total_delivered = outbound.filter(
            status__in=[Message.Status.DELIVERED, Message.Status.READ]
        ).count()
        total_read = outbound.filter(status=Message.Status.READ).count()
        total_failed = outbound.filter(status=Message.Status.FAILED).count()

        last_delivered = outbound.filter(delivered_at__isnull=False).order_by("-delivered_at").first()
        last_read = outbound.filter(read_at__isnull=False).order_by("-read_at").first()

        read_pairs = outbound.filter(
            sent_at__isnull=False,
            read_at__isnull=False,
        ).annotate(
            read_delay=ExpressionWrapper(F("read_at") - F("sent_at"), output_field=DurationField())
        )
        avg_read_seconds = None
        delays = [row.read_delay.total_seconds() for row in read_pairs if row.read_delay]
        if delays:
            avg_read_seconds = sum(delays) / len(delays)

        read_rate = round((total_read / total_sent) * 100, 1) if total_sent else 0

        return APIResponse.success({
            "total_sent": total_sent,
            "total_delivered": total_delivered,
            "total_read": total_read,
            "total_failed": total_failed,
            "read_rate": read_rate,
            "last_delivered_at": last_delivered.delivered_at.isoformat() if last_delivered else None,
            "last_read_at": last_read.read_at.isoformat() if last_read else None,
            "average_read_seconds": avg_read_seconds,
        })


class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ["conversation", "direction", "status", "channel"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return Message.objects.select_related("conversation", "sender").all()

    def perform_create(self, serializer):
        message = serializer.save(
            organization=self.request.organization,
            sender=self.request.user,
            direction=Message.Direction.OUTBOUND,
        )
        conversation = message.conversation
        conversation.last_message_at = timezone.now()
        conversation.last_message_preview = message.content[:255]
        conversation.metadata = {
            **(conversation.metadata or {}),
            "last_message_direction": Message.Direction.OUTBOUND,
        }
        conversation.save(update_fields=["last_message_at", "last_message_preview", "metadata", "updated_at"])

        if not message.is_internal_note:
            from apps.inbox.message_status import apply_message_status_update

            apply_message_status_update(message, Message.Status.PENDING, broadcast=False)
            broadcast_outbound_queued(str(self.request.organization.id), message, conversation)
            send_whatsapp_message.delay(str(message.id))

    @action(detail=False, methods=["post"], url_path="send-sms")
    def send_sms(self, request):
        serializer = SendSMSSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            contact = self._get_or_create_sms_contact(request, data)
            conversation, _ = Conversation.objects.get_or_create(
                organization=request.organization,
                contact=contact,
                defaults={"status": Conversation.Status.OPEN},
            )
            message = Message.objects.create(
                organization=request.organization,
                conversation=conversation,
                channel=Message.Channel.SMS,
                direction=Message.Direction.OUTBOUND,
                message_type=Message.MessageType.TEXT,
                content=data["content"],
                sender=request.user,
                metadata={"sms_to": contact.phone},
            )
            now = timezone.now()
            conversation.last_message_at = now
            conversation.last_message_preview = message.content[:255]
            conversation.save(update_fields=["last_message_at", "last_message_preview", "updated_at"])
            contact.last_contacted_at = now
            contact.save(update_fields=["last_contacted_at", "updated_at"])

        send_sms_message.delay(str(message.id))
        return APIResponse.success(
            MessageSerializer(message, context=self.get_serializer_context()).data,
            message="SMS queued",
            status_code=201,
        )

    def _get_or_create_sms_contact(self, request, data):
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


class CannedReplyViewSet(viewsets.ModelViewSet):
    serializer_class = CannedReplySerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    search_fields = ["title", "content", "shortcut"]

    def get_queryset(self):
        return CannedReply.objects.all()

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.organization,
            created_by=self.request.user,
        )
