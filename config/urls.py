from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.embed_api.urls")),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/organizations/", include("apps.organizations.urls")),
    path("api/v1/crm/", include("apps.crm.urls")),
    path("api/v1/inbox/", include("apps.inbox.urls")),
    path("api/v1/automation/", include("apps.automation.urls")),
    path("api/v1/campaigns/", include("apps.campaigns.urls")),
    path("api/v1/billing/", include("apps.billing.urls")),
    path("api/v1/onboarding/", include("apps.onboarding.urls")),
    path("api/v1/quotes/", include("apps.quotes.urls")),
    path("api/v1/invoices/", include("apps.invoices.urls")),
    path("api/v1/analytics/", include("apps.analytics.urls")),
    path("api/v1/platform/", include("apps.api_platform.urls")),
    path("api/v1/ai/", include("apps.ai.urls")),
    path("api/v1/core/", include("apps.core.urls")),
    path("api/v1/whatsapp-crm/", include("apps.whatsapp_crm.urls")),
    path("api/v1/sms-crm/", include("apps.sms_crm.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
