from rest_framework.permissions import BasePermission

from apps.core.models import get_current_organization
from apps.organizations.models import OrganizationMembership


class IsOrganizationMember(BasePermission):
    message = "You must be a member of this organization."

    def has_permission(self, request, view):
        org = get_current_organization()
        if org is None:
            return False
        request.organization = org
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


class IsOwnerOrAdmin(HasOrganizationRole):
    required_roles = [
        OrganizationMembership.Role.OWNER,
        OrganizationMembership.Role.ADMIN,
    ]


class IsManagerOrAbove(HasOrganizationRole):
    required_roles = [
        OrganizationMembership.Role.OWNER,
        OrganizationMembership.Role.ADMIN,
        OrganizationMembership.Role.MANAGER,
    ]
