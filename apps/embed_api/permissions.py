"""Permissions and role mapping for external CRM embed API."""

from apps.organizations.models import OrganizationMembership

EMBED_ROLE_ADMIN = "Admin"
EMBED_ROLE_MANAGER = "Manager"
EMBED_ROLE_STAFF = "Staff"

ORG_ROLE_TO_EMBED = {
    OrganizationMembership.Role.OWNER: EMBED_ROLE_ADMIN,
    OrganizationMembership.Role.ADMIN: EMBED_ROLE_ADMIN,
    OrganizationMembership.Role.MANAGER: EMBED_ROLE_MANAGER,
    OrganizationMembership.Role.AGENT: EMBED_ROLE_STAFF,
    OrganizationMembership.Role.VIEWER: EMBED_ROLE_STAFF,
    OrganizationMembership.Role.MARKETING: EMBED_ROLE_MANAGER,
    OrganizationMembership.Role.ACCOUNTANT: EMBED_ROLE_STAFF,
    OrganizationMembership.Role.FINANCE: EMBED_ROLE_STAFF,
}

EXTERNAL_ROLE_MAP = {
    "admin": EMBED_ROLE_ADMIN,
    "owner": EMBED_ROLE_ADMIN,
    "manager": EMBED_ROLE_MANAGER,
    "staff": EMBED_ROLE_STAFF,
    "agent": EMBED_ROLE_STAFF,
    "viewer": EMBED_ROLE_STAFF,
}

EMBED_SCOPES = ("embed", "inbox", "read", "write", "customers")


def map_org_role(role: str) -> str:
    return ORG_ROLE_TO_EMBED.get(role, EMBED_ROLE_STAFF)


def map_external_role(role: str) -> str:
    return EXTERNAL_ROLE_MAP.get(str(role or "").lower(), EMBED_ROLE_STAFF)


def embed_permissions(embed_role: str) -> dict:
    """Embed API only exposes inbox + customers. Admin modules stay off-platform."""
    can_manage = embed_role in {EMBED_ROLE_ADMIN, EMBED_ROLE_MANAGER}
    return {
        "inbox": True,
        "customers": True,
        "send_messages": True,
        "templates": False,
        "campaigns": False,
        "media": False,
        "reports": False,
        "automation": False,
        "api_settings": False,
        "role": embed_role,
        "can_assign_conversations": can_manage,
        "can_manage_team": embed_role == EMBED_ROLE_ADMIN,
    }
