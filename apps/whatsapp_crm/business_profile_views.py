import os

from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.core.exceptions import APIResponse
from apps.core.permissions import IsOrganizationMember, IsOwnerOrAdmin
from apps.core.rbac import get_membership
from apps.organizations.models import OrganizationMembership
from apps.whatsapp_crm.profile_service import (
    LABEL_TO_VERTICAL,
    META_VERTICALS,
    MetaBusinessProfileService,
)
from apps.whatsapp_crm.views import WhatsAppCRMBaseView


class WhatsAppBusinessProfileView(WhatsAppCRMBaseView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        if self.request.method in {"PATCH", "POST"}:
            return [IsAuthenticated(), IsOrganizationMember(), IsOwnerOrAdmin()]
        return [IsAuthenticated(), IsOrganizationMember()]

    def get(self, request):
        service = MetaBusinessProfileService(request.organization)
        if not service.is_configured:
            return APIResponse.error(
                "Connect WhatsApp API before managing the business profile.",
                status_code=400,
            )

        cached = (request.organization.settings or {}).get("whatsapp_profile")
        if cached:
            profile = cached
        else:
            profile = service.sync_and_cache()
            if profile.get("error"):
                return APIResponse.error(str(profile["error"]), status_code=400)

        return APIResponse.success({
            "profile": profile,
            "health": service.get_health(),
            "audit_log": service.get_audit_log(),
            "categories": [{"code": code, "label": label} for code, label in META_VERTICALS],
            "can_edit": self._user_can_edit(request),
        })

    def _user_can_edit(self, request):
        if request.user.is_superuser:
            return True
        membership = get_membership(request.user, request.organization)
        return bool(
            membership
            and membership.role in {
                OrganizationMembership.Role.OWNER,
                OrganizationMembership.Role.ADMIN,
            }
        )

    def patch(self, request):
        service = MetaBusinessProfileService(request.organization)
        if not service.is_configured:
            return APIResponse.error("WhatsApp is not connected.", status_code=400)

        data = request.data.copy()
        if "category" in data and "vertical" not in data:
            label = str(data.get("category", "")).strip().lower()
            data["vertical"] = LABEL_TO_VERTICAL.get(label, data.get("vertical"))

        websites = data.get("websites")
        if isinstance(websites, str):
            import json
            try:
                websites = json.loads(websites)
            except json.JSONDecodeError:
                websites = [websites]
        if websites is not None:
            data["websites"] = websites

        errors = service.validate_payload(data)
        if errors:
            return APIResponse.error(errors[0], status_code=400)

        logo_path = None
        upload = request.FILES.get("logo")
        remove_logo = str(data.get("remove_logo", "")).lower() in {"1", "true", "yes"}
        try:
            if upload:
                logo_path = service.save_uploaded_logo(upload)
            elif remove_logo:
                pass
        except ValueError as exc:
            return APIResponse.error(str(exc), status_code=400)

        update_payload = {
            "description": data.get("description"),
            "address": data.get("address"),
            "email": data.get("email"),
            "websites": data.get("websites"),
            "vertical": data.get("vertical"),
        }
        result = service.update_profile(update_payload, logo_path=logo_path)
        if logo_path:
            try:
                os.unlink(logo_path)
            except OSError:
                pass

        if result.get("error"):
            return APIResponse.error(str(result["error"]), status_code=400)

        business_hours = data.get("business_hours")
        if isinstance(business_hours, str):
            import json
            try:
                business_hours = json.loads(business_hours)
            except json.JSONDecodeError:
                business_hours = None
        if business_hours is not None:
            settings_data = dict(request.organization.settings or {})
            wp = dict(settings_data.get("whatsapp_profile", {}))
            wp["business_hours"] = business_hours
            settings_data["whatsapp_profile"] = wp
            request.organization.settings = settings_data
            request.organization.save(update_fields=["settings", "updated_at"])

        profile = service.sync_and_cache()
        service.append_audit(
            request.user,
            "Profile updated",
            {k: v for k, v in update_payload.items() if v is not None},
        )

        return APIResponse.success(
            {
                "profile": profile,
                "health": service.get_health(),
                "audit_log": service.get_audit_log(),
            },
            message="Profile updated successfully",
        )


class WhatsAppBusinessProfileSyncView(WhatsAppCRMBaseView):
    permission_classes = [IsAuthenticated, IsOrganizationMember, IsOwnerOrAdmin]

    def post(self, request):
        service = MetaBusinessProfileService(request.organization)
        if not service.is_configured:
            return APIResponse.error("WhatsApp is not connected.", status_code=400)

        profile = service.sync_and_cache()
        if profile.get("error"):
            return APIResponse.error(str(profile["error"]), status_code=400)

        service.append_audit(request.user, "Synced from Meta")
        return APIResponse.success(
            {
                "profile": profile,
                "health": service.get_health(),
                "audit_log": service.get_audit_log(),
            },
            message="Profile synced from Meta",
        )
