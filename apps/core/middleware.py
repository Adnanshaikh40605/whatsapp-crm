from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from apps.core.models import set_audit_context, set_current_organization
from apps.organizations.models import Organization, OrganizationMembership


from rest_framework_simplejwt.authentication import JWTAuthentication


class TenantMiddleware(MiddlewareMixin):
    """Resolve tenant organization from header or user's default org."""

    def process_request(self, request):
        set_current_organization(None)
        organization = None

        if not request.user.is_authenticated:
            try:
                header = request.headers.get("Authorization")
                if header and header.startswith("Bearer "):
                    authenticator = JWTAuthentication()
                    user_auth_tuple = authenticator.authenticate(request)
                    if user_auth_tuple:
                        request.user, request.auth = user_auth_tuple
            except Exception:
                pass

        if request.user.is_authenticated:
            org_id = request.headers.get(settings.TENANT_HEADER)
            if org_id:
                membership = OrganizationMembership.objects.filter(
                    organization_id=org_id,
                    user=request.user,
                    is_active=True,
                ).select_related("organization").first()
                if membership:
                    organization = membership.organization
            else:
                membership = (
                    OrganizationMembership.objects.filter(
                        user=request.user,
                        is_active=True,
                    )
                    .select_related("organization")
                    .order_by("-is_default", "-created_at")
                    .first()
                )
                if membership:
                    organization = membership.organization

        set_current_organization(organization)
        request.organization = organization


class AuditContextMiddleware(MiddlewareMixin):
    def process_request(self, request):
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        if not ip:
            ip = request.META.get("REMOTE_ADDR")
        user = request.user if request.user.is_authenticated else None
        set_audit_context(
            user=user,
            ip_address=ip or None,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
