from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.core.exceptions import APIResponse
from apps.core.permissions import IsOrganizationMember
from apps.campaigns.meta import MetaTemplateService
from apps.campaigns.models import Campaign, CampaignRecipient, MediaAsset, WhatsAppTemplate
from apps.campaigns.campaign_analytics import (
    export_report,
    get_overview,
    get_recipients,
    get_tab_stats,
    _parse_failure_code,
    _can_retry,
)
from apps.campaigns.serializers import CampaignSerializer, MediaAssetSerializer, WhatsAppTemplateSerializer


class MediaAssetViewSet(viewsets.ModelViewSet):
    serializer_class = MediaAssetSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    parser_classes = [MultiPartParser, FormParser]
    filterset_fields = ["asset_type"]
    search_fields = ["name"]

    def get_queryset(self):
        return MediaAsset.objects.all()

    def perform_create(self, serializer):
        file_obj = self.request.FILES.get("file")
        serializer.save(
            organization=self.request.organization,
            uploaded_by=self.request.user,
            file_size=getattr(file_obj, "size", 0) or 0,
            mime_type=getattr(file_obj, "content_type", "") or "",
        )


class WhatsAppTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = WhatsAppTemplateSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ["category", "status"]
    search_fields = ["name", "body"]

    def get_queryset(self):
        return WhatsAppTemplate.objects.select_related("media_asset").all()

    def perform_create(self, serializer):
        template = serializer.save(organization=self.request.organization)
        submit = self.request.data.get("submit_to_meta")
        if str(submit).lower() not in {"1", "true", "yes"}:
            return

        result = MetaTemplateService(self.request.organization).create_template(template)
        if result.get("error"):
            # Keep the draft saved, but surface Meta's rejection so it does not silently
            # look like a failed/disabled template with no Meta ID.
            raw = result["error"]
            if isinstance(raw, dict):
                message = (
                    (raw.get("error") or {}).get("message")
                    or raw.get("message")
                    or str(raw)
                )
            else:
                message = str(raw)
            raise ValidationError({"submit_to_meta": [message]})

    @action(detail=False, methods=["post"])
    def sync_meta(self, request):
        """Sync templates from Meta WhatsApp Business API."""
        result = MetaTemplateService(request.organization).sync_templates()
        if result.get("error"):
            return APIResponse.error(result["error"], status_code=400)
        return APIResponse.success(
            {"synced_count": result["synced_count"]},
            message=f"Synced {result['synced_count']} templates from Meta",
        )

    @action(detail=True, methods=["post"])
    def submit_meta(self, request, pk=None):
        template = self.get_object()
        result = MetaTemplateService(request.organization).create_template(template)
        if result.get("error"):
            return APIResponse.error(result["error"], status_code=400)
        return APIResponse.success(WhatsAppTemplateSerializer(template).data, message="Template submitted to Meta")

    @action(detail=True, methods=["post"])
    def refresh_meta(self, request, pk=None):
        template = self.get_object()
        result = MetaTemplateService(request.organization).refresh_template(template)
        if result.get("error"):
            return APIResponse.error(result["error"], status_code=400)
        return APIResponse.success(WhatsAppTemplateSerializer(template).data, message="Template status refreshed")

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        template = self.get_object()
        return APIResponse.success(
            {
                "name": template.name,
                "body": template.body,
                "header": template.header,
                "footer": template.footer,
                "buttons": template.buttons,
                "variables": template.variables,
            }
        )

    @action(detail=True, methods=["post"], url_path="send_test")
    def send_test(self, request, pk=None):
        template = self.get_object()
        if template.status != WhatsAppTemplate.Status.APPROVED:
            return APIResponse.error("Template must be approved before sending a test message.", status_code=400)

        phone = str(request.data.get("phone", "")).strip()
        if not phone:
            return APIResponse.error("Phone number is required.", status_code=400)

        from apps.campaigns.meta import build_template_send_components
        from apps.core.whatsapp_service import WhatsAppService

        wa = WhatsAppService(request.organization)
        body_params = request.data.get("body_params")
        if body_params is None:
            examples = template.examples if isinstance(template.examples, dict) else {}
            body_text = examples.get("body_text")
            if isinstance(body_text, list) and body_text and isinstance(body_text[0], list):
                body_params = [str(v) for v in body_text[0]]
            elif isinstance(body_text, list):
                body_params = [str(v) for v in body_text if not isinstance(v, (list, dict))]
            elif template.variables:
                body_params = [str(v) for v in template.variables]
            else:
                body_params = []
        components = build_template_send_components(template, body_params, wa=wa)
        result = wa.send_template(phone, template.name, template.language, components)
        if result.get("error"):
            return APIResponse.error(str(result["error"]), status_code=400)
        return APIResponse.success(result, message="Test template sent")


class CampaignViewSet(viewsets.ModelViewSet):
    serializer_class = CampaignSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ["status", "is_archived"]
    search_fields = ["name"]

    def get_queryset(self):
        archived = self.request.query_params.get("archived")
        qs = Campaign.objects.select_related("template", "contact_group").all()
        if archived == "true":
            return qs.filter(is_archived=True)
        if archived == "false":
            return qs.filter(is_archived=False)
        return qs

    def perform_create(self, serializer):
        template = serializer.validated_data.get("template")
        if template and template.status != WhatsAppTemplate.Status.APPROVED:
            raise ValidationError("Only approved templates can be used for campaigns.")
        serializer.save(
            organization=self.request.organization,
            created_by=self.request.user,
        )

    @action(detail=True, methods=["post"])
    def launch(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status not in (Campaign.Status.DRAFT, Campaign.Status.SCHEDULED):
            return APIResponse.error("Campaign cannot be launched", status_code=400)
        if campaign.template and campaign.template.status != WhatsAppTemplate.Status.APPROVED:
            return APIResponse.error("Only approved templates can be launched", status_code=400)
        campaign.status = Campaign.Status.RUNNING
        campaign.save(update_fields=["status", "updated_at"])
        from apps.campaigns.tasks import process_campaign

        process_campaign.delay(str(campaign.id))
        return APIResponse.success(CampaignSerializer(campaign).data, message="Campaign launched")

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        campaign = self.get_object()
        campaign.is_archived = True
        campaign.save(update_fields=["is_archived", "updated_at"])
        return APIResponse.success(CampaignSerializer(campaign).data, message="Campaign archived")

    @action(detail=True, methods=["get"])
    def dashboard(self, request, pk=None):
        campaign = self.get_object()
        overview = get_overview(campaign)
        return APIResponse.success({**overview["summary"], **overview["campaign"], **overview})

    @action(detail=True, methods=["get"], url_path="analytics/overview")
    def analytics_overview(self, request, pk=None):
        campaign = self.get_object()
        return APIResponse.success(get_overview(campaign))

    @action(detail=True, methods=["get"], url_path="analytics/recipients")
    def analytics_recipients(self, request, pk=None):
        campaign = self.get_object()
        tab = request.query_params.get("tab", "sent")
        page = int(request.query_params.get("page", 1))
        page_size = min(int(request.query_params.get("page_size", 25)), 100)
        data = get_recipients(
            campaign,
            tab,
            search=request.query_params.get("search", ""),
            preset=request.query_params.get("preset", ""),
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
            read_filter=request.query_params.get("read_filter", ""),
            page=page,
            page_size=page_size,
        )
        return APIResponse.success({
            "stats": get_tab_stats(campaign, tab),
            **data,
        })

    @action(detail=True, methods=["get"], url_path="analytics/export")
    def analytics_export(self, request, pk=None):
        campaign = self.get_object()
        tab = request.query_params.get("tab", "overview")
        fmt = request.query_params.get("format", "csv")
        content, filename, content_type = export_report(campaign, tab, fmt)
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @action(detail=True, methods=["post"], url_path="analytics/email-report")
    def analytics_email_report(self, request, pk=None):
        campaign = self.get_object()
        tab = request.data.get("tab", "overview")
        email = str(request.data.get("email", "")).strip()
        if not email:
            return APIResponse.error("Email address is required.", status_code=400)
        content, filename, _ = export_report(campaign, tab, request.data.get("format", "xlsx"))
        # SMTP not configured — return downloadable payload for now
        return APIResponse.success(
            {
                "email": email,
                "tab": tab,
                "filename": filename,
                "message": f"Report prepared for {email}. Configure SMTP to enable automatic email delivery.",
            },
            message="Report queued",
        )

    @action(detail=True, methods=["post"], url_path="retry-recipient")
    def retry_recipient(self, request, pk=None):
        campaign = self.get_object()
        recipient_id = request.data.get("recipient_id")
        try:
            recipient = campaign.recipients.select_related("contact").get(id=recipient_id)
        except CampaignRecipient.DoesNotExist:
            return APIResponse.error("Recipient not found.", status_code=404)

        code = recipient.failure_code or _parse_failure_code(recipient.error_message)
        if not _can_retry(code):
            return APIResponse.error("This failure cannot be retried.", status_code=400)

        from apps.core.whatsapp_service import WhatsAppService

        wa = WhatsAppService(request.organization)
        if campaign.template:
            result = wa.send_template(
                recipient.contact.phone,
                campaign.template.name,
                campaign.template.language,
            )
        else:
            result = wa.send_text(recipient.contact.phone, campaign.message_content or "Hello from WhatsFlow!")

        if result.get("error"):
            recipient.status = CampaignRecipient.Status.FAILED
            recipient.error_message = str(result["error"])
            recipient.failure_code = _parse_failure_code(recipient.error_message)
            recipient.save()
            return APIResponse.error(str(result["error"]), status_code=400)

        wa_id = ""
        if result.get("messages"):
            wa_id = result["messages"][0].get("id", "")

        recipient.status = CampaignRecipient.Status.SENT
        recipient.sent_at = timezone.now()
        recipient.whatsapp_message_id = wa_id
        recipient.error_message = ""
        recipient.failure_code = ""
        recipient.save()
        return APIResponse.success({"recipient_id": str(recipient.id)}, message="Message resent")
