from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.organizations.admin_views import SuperAdminCompaniesView, SuperAdminCompanyDetailView
from apps.organizations.views import CurrentOrganizationView, OrganizationViewSet

router = DefaultRouter()
router.register("", OrganizationViewSet, basename="organization")

urlpatterns = [
    path("current/", CurrentOrganizationView.as_view(), name="current-organization"),
    path("admin/companies/", SuperAdminCompaniesView.as_view(), name="admin-companies"),
    path("admin/companies/<uuid:company_id>/", SuperAdminCompanyDetailView.as_view(), name="admin-company-detail"),
    path("", include(router.urls)),
]
