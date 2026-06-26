from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.crm.views import ActivityViewSet, ContactGroupViewSet, ContactViewSet, LeadViewSet, PipelineStageViewSet

router = DefaultRouter()
router.register("contacts", ContactViewSet, basename="contact")
router.register("groups", ContactGroupViewSet, basename="contact-group")
router.register("stages", PipelineStageViewSet, basename="pipeline-stage")
router.register("leads", LeadViewSet, basename="lead")
router.register("activities", ActivityViewSet, basename="activity")

urlpatterns = [
    path("", include(router.urls)),
]
