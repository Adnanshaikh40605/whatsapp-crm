"""Role-based access control helpers for multi-tenant CRM."""

from apps.organizations.models import OrganizationMembership

PLATFORM_SUPER_ADMIN = "super_admin"
PLATFORM_ADMIN = "admin"
PLATFORM_STAFF = "staff"

STAFF_ROLES = frozenset({
    OrganizationMembership.Role.AGENT,
    OrganizationMembership.Role.VIEWER,
})

ADMIN_ROLES = frozenset({
    OrganizationMembership.Role.OWNER,
    OrganizationMembership.Role.ADMIN,
    OrganizationMembership.Role.MANAGER,
    OrganizationMembership.Role.MARKETING,
    OrganizationMembership.Role.ACCOUNTANT,
    OrganizationMembership.Role.FINANCE,
})

STAFF_ALLOWED_API_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/organizations/",
    "/api/v1/inbox/",
    "/api/auth/",
    "/api/inbox/",
    "/api/customers/",
)


def get_membership(user, organization):
    if not user or not user.is_authenticated or organization is None:
        return None
    return OrganizationMembership.objects.filter(
        organization=organization,
        user=user,
        is_active=True,
    ).first()


def resolve_platform_role(user, org_role=None):
    if user.is_superuser:
        return PLATFORM_SUPER_ADMIN
    if org_role in STAFF_ROLES:
        return PLATFORM_STAFF
    return PLATFORM_ADMIN


def is_staff_role(role):
    return role in STAFF_ROLES


def is_admin_role(role):
    return role in ADMIN_ROLES


def user_can_manage_projects(user):
    if user.is_superuser:
        return True
    memberships = OrganizationMembership.objects.filter(user=user, is_active=True)
    if not memberships.exists():
        return True
    return any(m.role not in STAFF_ROLES for m in memberships)


def staff_may_access_path(path):
    return any(path.startswith(prefix) for prefix in STAFF_ALLOWED_API_PREFIXES)
