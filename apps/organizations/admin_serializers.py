from rest_framework import serializers

from apps.organizations.models import Organization
from apps.organizations.serializers import OrganizationSerializer


class AdminCompanySerializer(OrganizationSerializer):
    whatsapp_phone_number_id = serializers.CharField(read_only=True)
    whatsapp_business_account_id = serializers.CharField(read_only=True)
    owner_email = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()

    class Meta(OrganizationSerializer.Meta):
        fields = OrganizationSerializer.Meta.fields + (
            "whatsapp_phone_number_id",
            "whatsapp_business_account_id",
            "owner_email",
            "stats",
        )

    def get_owner_email(self, obj):
        return obj.owner.email

    def get_stats(self, obj):
        from apps.crm.models import Contact, Lead
        from apps.campaigns.models import Campaign
        from apps.inbox.models import Conversation

        return {
            "contacts": Contact.all_objects.filter(organization=obj).count(),
            "leads": Lead.all_objects.filter(organization=obj, is_archived=False).count(),
            "campaigns": Campaign.all_objects.filter(organization=obj).count(),
            "conversations": Conversation.all_objects.filter(organization=obj).count(),
            "members": obj.memberships.filter(is_active=True).count(),
        }


class CreateCompanySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    industry = serializers.CharField(max_length=100, required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True)
