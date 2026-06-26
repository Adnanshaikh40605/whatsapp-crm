from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.api_platform.views import APIKeyViewSet, WebhookEndpointViewSet

router = DefaultRouter()
router.register("keys", APIKeyViewSet, basename="api-key")
router.register("webhooks", WebhookEndpointViewSet, basename="webhook")

urlpatterns = [path("", include(router.urls))]
