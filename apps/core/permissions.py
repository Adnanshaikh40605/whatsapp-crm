from rest_framework.permissions import BasePermission

from apps.core.models import get_current_organization
from apps.core.rbac import (
    ADMIN_ROLES,
    STAFF_ROLES,
    get_membership,
    user_can_manage_projects,
)
from apps.organizations.models import OrganizationMembership


class IsOrganizationMember(BasePermission):
    message = "You must be a member of this organization."

    def has_permission(self, request, view):
        org = get_current_organization()
        if org is None:
            return False
        request.organization = org
        if request.user.is_superuser:
            return True
        return OrganizationMembership.objects.filter(
            organization=org,
            user=request.user,
            is_active=True,
        ).exists()


class HasOrganizationRole(BasePermission):
    required_roles = []

    def has_permission(self, request, view):
        org = get_current_organization()
        if org is None:
            return False
        membership = OrganizationMembership.objects.filter(
            organization=org,
            user=request.user,
            is_active=True,
        ).first()
        if not membership:
            return False
        request.membership = membership
        return membership.role in self.required_roles


class IsSuperAdmin(BasePermission):
    message = "Super admin access required."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_superuser


class IsOwnerOrAdmin(HasOrganizationRole):
    required_roles = [
        OrganizationMembership.Role.OWNER,
        OrganizationMembership.Role.ADMIN,
    ]


class IsOrgAdmin(BasePermission):
    """Admin-level access within the current organization (not staff)."""
    message = "Admin access required for this action."

    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        org = get_current_organization()
        membership = get_membership(request.user, org)
        if not membership:
            return False
        request.membership = membership
        return membership.role in ADMIN_ROLES


class IsNotStaffOnly(BasePermission):
    """Block inbox-only staff from admin CRM modules."""
    message = "Staff members can only access the inbox."

    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        org = get_current_organization()
        membership = get_membership(request.user, org)
        if not membership:
            return False
        request.membership = membership
        return membership.role not in STAFF_ROLES


class CanManageProjects(BasePermission):
    message = "You do not have permission to manage or delete projects."

    def has_permission(self, request, view):
        return user_can_manage_projects(request.user)


class IsManagerOrAbove(HasOrganizationRole):
    required_roles = [
        OrganizationMembership.Role.OWNER,
        OrganizationMembership.Role.ADMIN,
        OrganizationMembership.Role.MANAGER,
    ]
