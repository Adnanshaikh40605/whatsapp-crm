"""Public redirect for e-card / brochure click tracking."""

from django.http import HttpResponseNotFound, HttpResponseRedirect
from django.views import View

from apps.campaigns.ecard_tracking import record_click
from apps.campaigns.models import ECardTrackedLink


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class ECardRedirectView(View):
    """
    GET /r/<token>/
    Logs the click (phone + time) then redirects to the real e-card URL.
    """

    def get(self, request, token: str):
        link = (
            ECardTrackedLink.objects.select_related("organization")
            .filter(token=token)
            .first()
        )
        if not link:
            return HttpResponseNotFound("Tracking link not found.")

        record_click(
            link,
            ip=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return HttpResponseRedirect(link.destination_url)
