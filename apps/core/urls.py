from django.urls import path
from apps.core.views import CoreOptionsView

urlpatterns = [
    path("options/", CoreOptionsView.as_view(), name="core-options"),
]
