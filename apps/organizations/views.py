from django.contrib.auth import get_user_model
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import APIResponse
from apps.core.models import get_current_organization, set_current_organization
from apps.core.permissions import IsOrganizationMember, IsOwnerOrAdmin
from apps.organizations.models import Organization, OrganizationMembership
from apps.organizations.serializers import (
    CreateOrganizationSerializer,
    OrganizationMembershipSerializer,
    OrganizationSerializer,
)

User = get_user_model()


class OrganizationViewSet(viewsets.ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Organization.objects.filter(
            memberships__user=self.request.user,
            memberships__is_active=True,
        ).distinct()

    def get_permissions(self):
        if self.action in ("create", "list", "retrieve", "switch"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsOwnerOrAdmin()]

    def create(self, request, *args, **kwargs):
        serializer = CreateOrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org = Organization.objects.create(
            owner=request.user,
            slug=Organization.generate_slug(serializer.validated_data["name"]),
            **serializer.validated_data,
        )
        OrganizationMembership.objects.create(
            organization=org,
            user=request.user,
            role=OrganizationMembership.Role.OWNER,
            is_default=not OrganizationMembership.objects.filter(
                user=request.user, is_default=True
            ).exists(),
        )
        return APIResponse.success(
            OrganizationSerializer(org).data,
            message="Organization created",
            status_code=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def switch(self, request, pk=None):
        org = self.get_object()
        if not OrganizationMembership.objects.filter(
            organization=org, user=request.user, is_active=True
        ).exists():
            return APIResponse.error("Not a member", status_code=403)
        OrganizationMembership.objects.filter(user=request.user).update(is_default=False)
        OrganizationMembership.objects.filter(
            organization=org, user=request.user
        ).update(is_default=True)
        set_current_organization(org)
        return APIResponse.success(
            OrganizationSerializer(org).data,
            message="Organization switched",
        )

    @action(detail=True, methods=["get", "post"], permission_classes=[IsAuthenticated, IsOwnerOrAdmin])
    def members(self, request, pk=None):
        org = self.get_object()
        set_current_organization(org)

        if request.method == "GET":
            memberships = org.memberships.select_related("user").filter(is_active=True)
            return APIResponse.success(
                OrganizationMembershipSerializer(memberships, many=True).data
            )

        email = request.data.get("email")
        role = request.data.get("role", OrganizationMembership.Role.AGENT)
        user = User.objects.filter(email=email).first()
        if not user:
            return APIResponse.error("User not found. They must register first.", status_code=404)
        membership, created = OrganizationMembership.objects.get_or_create(
            organization=org,
            user=user,
            defaults={"role": role, "invited_by": request.user},
        )
        if not created:
            return APIResponse.error("User is already a member", status_code=400)
        return APIResponse.success(
            OrganizationMembershipSerializer(membership).data,
            message="Member added",
            status_code=status.HTTP_201_CREATED,
        )


class CurrentOrganizationView(generics.RetrieveAPIView):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get_object(self):
        return get_current_organization()
