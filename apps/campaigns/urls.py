from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.campaigns.views import CampaignViewSet, MediaAssetViewSet, WhatsAppTemplateViewSet

router = DefaultRouter()
router.register("media", MediaAssetViewSet, basename="media-asset")
router.register("templates", WhatsAppTemplateViewSet, basename="template")
router.register("", CampaignViewSet, basename="campaign")

urlpatterns = [
    path("", include(router.urls)),
]
