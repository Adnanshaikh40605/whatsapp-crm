from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

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
            "created_at",
        )
        read_only_fields = ("id", "email_verified", "created_at")


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
