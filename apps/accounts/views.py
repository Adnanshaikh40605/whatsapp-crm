from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.tokens import NameTokenObtainPairSerializer, resolve_user_by_name
from apps.accounts.serializers import (
    ChangePasswordSerializer,
    RegisterSerializer,
    UserSerializer,
)
from apps.core.exceptions import APIResponse
from apps.core.models import AuditLog, get_audit_context
from apps.organizations.models import Organization, OrganizationMembership

User = get_user_model()


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        org_name = serializer.validated_data.pop("organization_name", None)
        password = serializer.validated_data.pop("password")
        user = User.objects.create_user(password=password, **serializer.validated_data)

        if org_name:
            org = Organization.objects.create(
                name=org_name,
                slug=Organization.generate_slug(org_name),
                owner=user,
            )
            OrganizationMembership.objects.create(
                organization=org,
                user=user,
                role=OrganizationMembership.Role.OWNER,
                is_default=True,
            )

        refresh = RefreshToken.for_user(user)
        return APIResponse.success(
            {
                "user": UserSerializer(user).data,
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
            },
            message="Registration successful",
            status_code=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = NameTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            user = resolve_user_by_name(request.data.get("name", ""))
            if user:
                user.last_login_at = timezone.now()
                user.save(update_fields=["last_login_at"])
                ctx = get_audit_context()
                AuditLog.objects.create(
                    user=user,
                    action=AuditLog.Action.LOGIN,
                    resource_type="user",
                    resource_id=str(user.id),
                    ip_address=ctx.get("ip_address"),
                    user_agent=ctx.get("user_agent", ""),
                )
            return APIResponse.success(
                {"tokens": response.data},
                message="Login successful",
            )
        return response


class RefreshTokenView(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            return APIResponse.success({"tokens": response.data})
        return response


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["old_password"]):
            return APIResponse.error("Current password is incorrect", status_code=400)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        return APIResponse.success(message="Password updated successfully")


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        user = User.objects.filter(email=email, is_active=True).first()
        if user:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            # In production: send email with reset link
            return APIResponse.success(
                {"uid": uid, "token": token},
                message="If the email exists, a reset link has been sent.",
            )
        return APIResponse.success(message="If the email exists, a reset link has been sent.")


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")
        password = request.data.get("password")
        if not all([uid, token, password]):
            return APIResponse.error("Missing required fields", status_code=400)
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return APIResponse.error("Invalid reset link", status_code=400)
        if not default_token_generator.check_token(user, token):
            return APIResponse.error("Invalid or expired token", status_code=400)
        user.set_password(password)
        user.save()
        return APIResponse.success(message="Password reset successful")
