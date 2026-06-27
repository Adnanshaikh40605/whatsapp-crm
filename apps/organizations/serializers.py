import json

from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.organizations.models import Organization, OrganizationMembership


class OrganizationSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    plan_limits = serializers.SerializerMethodField()
    timezone = serializers.CharField(source="org_timezone")
    remove_logo = serializers.BooleanField(write_only=True, required=False, default=False)
    whatsapp_phone_number_id = serializers.CharField(read_only=True)
    whatsapp_business_account_id = serializers.CharField(read_only=True)
    whatsapp_api_status = serializers.SerializerMethodField()
    whatsapp_setup_status = serializers.SerializerMethodField()
    has_project_password = serializers.SerializerMethodField()
    membership_role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "description",
            "project_type",
            "slug",
            "plan",
            "industry",
            "team_size",
            "logo",
            "remove_logo",
            "website",
            "timezone",
            "whatsapp_connected",
            "whatsapp_phone_number_id",
            "whatsapp_business_account_id",
            "whatsapp_api_status",
            "whatsapp_setup_status",
            "onboarding_completed",
            "onboarding_step",
            "branding",
            "settings",
            "white_label_domain",
            "is_active",
            "member_count",
            "plan_limits",
            "has_project_password",
            "membership_role",
            "created_at",
        )
        read_only_fields = ("id", "slug", "created_at")

    def validate_branding(self, branding):
        if isinstance(branding, str):
            try:
                return json.loads(branding)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError("Invalid branding JSON.") from exc
        return branding

    def create(self, validated_data):
        validated_data.pop("remove_logo", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        remove_logo = validated_data.pop("remove_logo", False)
        if remove_logo and instance.logo:
            instance.logo.delete(save=False)
            instance.logo = None
        return super().update(instance, validated_data)

    def get_member_count(self, obj):
        return obj.memberships.filter(is_active=True).count()

    def get_plan_limits(self, obj):
        return obj.get_plan_limits()

    def get_whatsapp_api_status(self, obj):
        if obj.whatsapp_phone_number_id and obj.whatsapp_business_account_id and obj.whatsapp_access_token:
            return "live"
        if obj.whatsapp_phone_number_id or obj.whatsapp_business_account_id or obj.whatsapp_connected:
            return "pending"
        return "not_connected"

    def get_whatsapp_setup_status(self, obj):
        missing = []
        if not obj.whatsapp_phone_number_id:
            missing.append("Phone Number ID")
        if not obj.whatsapp_business_account_id:
            missing.append("WhatsApp Business Account ID")
        if not obj.whatsapp_access_token:
            missing.append("Access Token")
        if not missing:
            return "Cloud API credentials are configured."
        return f"Missing: {', '.join(missing)}"

    def get_has_project_password(self, obj):
        return obj.has_access_password

    def get_membership_role(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        membership = obj.memberships.filter(user=request.user, is_active=True).first()
        return membership.role if membership else None


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_email = serializers.EmailField(write_only=True, required=False)

    class Meta:
        model = OrganizationMembership
        fields = (
            "id",
            "user",
            "user_email",
            "role",
            "is_active",
            "is_default",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class CreateOrganizationSerializer(serializers.ModelSerializer):
    timezone = serializers.CharField(source="org_timezone", required=False, default="UTC")
    project_password = serializers.CharField(write_only=True, min_length=4, max_length=128)

    class Meta:
        model = Organization
        fields = ("name", "description", "project_type", "website", "timezone", "project_password")


class VerifyProjectPasswordSerializer(serializers.Serializer):
    project_password = serializers.CharField(required=True, min_length=1, max_length=128)
