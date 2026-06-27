from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from apps.core.models import get_current_organization, set_audit_context, set_current_organization
from apps.core.rbac import get_membership, is_staff_role, staff_may_access_path
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
                if request.user.is_superuser:
                    organization = Organization.objects.filter(
                        id=org_id, is_active=True
                    ).first()
                else:
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


class StaffAccessMiddleware(MiddlewareMixin):
    """Restrict staff (agent/viewer) to inbox and auth endpoints."""

    def process_request(self, request):
        if not request.user.is_authenticated or request.user.is_superuser:
            return None
        if not request.path.startswith("/api/v1/"):
            return None
        if staff_may_access_path(request.path):
            return None

        org = get_current_organization()
        membership = get_membership(request.user, org)
        if membership and is_staff_role(membership.role):
            return JsonResponse(
                {"success": False, "message": "Staff members can only access the inbox."},
                status=403,
            )
        return None
