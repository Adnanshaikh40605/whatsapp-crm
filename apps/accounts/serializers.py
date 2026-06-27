from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.core.models import get_current_organization
from apps.core.rbac import get_membership, resolve_platform_role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    org_role = serializers.SerializerMethodField()
    platform_role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "avatar",
            "email_verified",
            "is_staff",
            "is_superuser",
            "org_role",
            "platform_role",
            "created_at",
        )
        read_only_fields = ("id", "email_verified", "created_at", "org_role", "platform_role", "is_superuser")

    def get_org_role(self, obj):
        request = self.context.get("request")
        if not request:
            return None
        org = get_current_organization()
        membership = get_membership(obj, org)
        return membership.role if membership else None

    def get_platform_role(self, obj):
        org_role = self.get_org_role(obj)
        return resolve_platform_role(obj, org_role)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    organization_name = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ("username", "password", "first_name", "last_name", "phone", "organization_name")

    def create(self, validated_data):
        organization_name = validated_data.pop("organization_name", None)
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user, organization_name


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8)
