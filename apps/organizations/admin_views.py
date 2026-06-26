from django.conf import settings
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.views import APIView

from apps.core.exceptions import APIResponse
from apps.core.models import set_current_organization
from apps.onboarding.services import WorkspaceBootstrap
from apps.organizations.admin_serializers import AdminCompanySerializer, CreateCompanySerializer
from apps.organizations.models import Organization, OrganizationMembership


class SuperAdminCompaniesView(APIView):
    """List and create companies — internal multi-company management."""

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        if getattr(settings, "INTERNAL_MODE", True):
            companies = Organization.objects.filter(is_active=True).select_related("owner")
        else:
            companies = Organization.objects.filter(
                memberships__user=request.user,
                memberships__role=OrganizationMembership.Role.OWNER,
                is_active=True,
            ).distinct()
        return APIResponse.success(AdminCompanySerializer(companies, many=True).data)

    def post(self, request):
        ser = CreateCompanySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        org = Organization.objects.create(
            name=data["name"],
            slug=Organization.generate_slug(data["name"]),
            owner=request.user,
            industry=data.get("industry", ""),
            website=data.get("website", ""),
            plan=Organization.Plan.INTERNAL,
            onboarding_completed=True,
        )
        OrganizationMembership.objects.create(
            organization=org,
            user=request.user,
            role=OrganizationMembership.Role.OWNER,
            is_default=False,
        )

        set_current_organization(org)
        bootstrap = WorkspaceBootstrap(org)
        bootstrap.setup_default_pipeline()
        bootstrap.setup_default_automations()

        return APIResponse.success(
            AdminCompanySerializer(org).data,
            message=f"Company '{org.name}' created",
        )


class SuperAdminCompanyDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, company_id):
        org = Organization.objects.filter(id=company_id, is_active=True).first()
        if not org:
            return APIResponse.error("Company not found", status_code=404)
        return APIResponse.success(AdminCompanySerializer(org).data)

    def patch(self, request, company_id):
        org = Organization.objects.filter(id=company_id).first()
        if not org:
            return APIResponse.error("Company not found", status_code=404)
        for field in ("name", "industry", "website", "is_active"):
            if field in request.data:
                setattr(org, field, request.data[field])
        org.save()
        return APIResponse.success(AdminCompanySerializer(org).data)
