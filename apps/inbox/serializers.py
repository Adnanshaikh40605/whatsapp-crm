from rest_framework import serializers

from apps.crm.serializers import ContactSerializer
from apps.inbox.models import CannedReply, Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = "__all__"
        read_only_fields = (
            "id",
            "organization",
            "direction",
            "sender",
            "status",
            "channel",
            "provider_message_id",
            "whatsapp_message_id",
            "metadata",
            "created_at",
            "updated_at",
        )


class ConversationSerializer(serializers.ModelSerializer):
    contact = ContactSerializer(read_only=True)
    contact_id = serializers.UUIDField(write_only=True)
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")

    def get_message_count(self, obj):
        return obj.messages.count()


class CannedReplySerializer(serializers.ModelSerializer):
    class Meta:
        model = CannedReply
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")


class SendSMSSerializer(serializers.Serializer):
    phone = serializers.CharField(required=False, allow_blank=True, max_length=32)
    contact_id = serializers.UUIDField(required=False)
    content = serializers.CharField(max_length=1600, trim_whitespace=True)
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)

    def validate(self, attrs):
        if not attrs.get("phone") and not attrs.get("contact_id"):
            raise serializers.ValidationError("Provide either phone or contact_id.")
        return attrs
