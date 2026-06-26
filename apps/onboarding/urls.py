from django.urls import path

from apps.onboarding.views import (
    AICampaignBuilderView,
    AISetupView,
    InstallPackView,
    MarketplaceView,
    OnboardingStatusView,
    OnboardingStepView,
    WhatsAppConnectView,
    WhatsAppEmbeddedSignupConfigView,
    WhatsAppWebhookView,
)

urlpatterns = [
    path("status/", OnboardingStatusView.as_view(), name="onboarding-status"),
    path("whatsapp/config/", WhatsAppEmbeddedSignupConfigView.as_view(), name="whatsapp-config"),
    path("whatsapp/connect/", WhatsAppConnectView.as_view(), name="whatsapp-connect"),
    path("step/<int:step>/", OnboardingStepView.as_view(), name="onboarding-step"),
    path("marketplace/", MarketplaceView.as_view(), name="marketplace"),
    path("marketplace/install/", InstallPackView.as_view(), name="install-pack"),
    path("ai/setup/", AISetupView.as_view(), name="ai-setup"),
    path("ai/campaign/", AICampaignBuilderView.as_view(), name="ai-campaign"),
    path("webhooks/whatsapp/", WhatsAppWebhookView.as_view(), name="whatsapp-webhook"),
]
