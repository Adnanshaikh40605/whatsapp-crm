from rest_framework import serializers

from apps.crm.models import Activity, Contact, ContactGroup, Lead, PipelineStage


class ContactSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    group_ids = serializers.PrimaryKeyRelatedField(
        source="groups",
        queryset=ContactGroup.objects.all(),
        many=True,
        required=False,
    )

    class Meta:
        model = Contact
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")


class ContactGroupSerializer(serializers.ModelSerializer):
    contact_count = serializers.ReadOnlyField()
    contact_ids = serializers.PrimaryKeyRelatedField(
        source="contacts",
        queryset=Contact.objects.all(),
        many=True,
        required=False,
    )

    class Meta:
        model = ContactGroup
        fields = "__all__"
        read_only_fields = ("id", "organization", "contact_count", "created_at", "updated_at")


class PipelineStageSerializer(serializers.ModelSerializer):
    lead_count = serializers.SerializerMethodField()

    class Meta:
        model = PipelineStage
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")

    def get_lead_count(self, obj):
        return obj.leads.filter(is_archived=False).count()


class LeadSerializer(serializers.ModelSerializer):
    contact_name = serializers.CharField(source="contact.full_name", read_only=True)
    stage_name = serializers.CharField(source="stage.name", read_only=True)

    class Meta:
        model = Lead
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")
