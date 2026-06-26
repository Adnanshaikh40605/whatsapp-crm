from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import (
    PasswordField,
    TokenObtainPairSerializer,
    TokenObtainSerializer,
)
from rest_framework_simplejwt.settings import api_settings

User = get_user_model()


def resolve_user_by_name(name: str):
    name = (name or "").strip()
    if not name:
        return None

    user = User.objects.filter(username__iexact=name, is_active=True).first()
    if user:
        return user

    # Fallback to email just in case
    return User.objects.filter(email__iexact=name, is_active=True).first()


class NameTokenObtainPairSerializer(TokenObtainPairSerializer):
    def __init__(self, *args, **kwargs):
        # Skip TokenObtainSerializer.__init__ — it adds the email/username field
        super(TokenObtainSerializer, self).__init__(*args, **kwargs)
        self.fields["name"] = serializers.CharField(write_only=True)
        self.fields["password"] = PasswordField()

    def validate(self, attrs):
        user = resolve_user_by_name(attrs.get("name", ""))
        if user is None or not user.check_password(attrs.get("password", "")):
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            )
        if not api_settings.USER_AUTHENTICATION_RULE(user):
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            )

        self.user = user
        refresh = self.get_token(user)
        return {"refresh": str(refresh), "access": str(refresh.access_token)}

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["name"] = user.full_name
        return token
