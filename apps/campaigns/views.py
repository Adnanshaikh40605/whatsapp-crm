from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.core.exceptions import APIResponse
from apps.core.permissions import IsOrganizationMember
from apps.campaigns.meta import MetaTemplateService
from apps.campaigns.models import Campaign, MediaAsset, WhatsAppTemplate
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
        if str(submit).lower() in {"1", "true", "yes"}:
            MetaTemplateService(self.request.organization).create_template(template)

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
        return APIResponse.success(
            {
                "name": campaign.name,
                "status": campaign.status,
                "total_recipients": campaign.total_recipients,
                "sent_count": campaign.sent_count,
                "delivered_count": campaign.delivered_count,
                "read_count": campaign.read_count,
                "reply_count": campaign.reply_count,
                "click_count": campaign.click_count,
                "failed_count": campaign.failed_count,
                "delivery_rate": (
                    round(campaign.delivered_count / campaign.sent_count * 100, 1)
                    if campaign.sent_count
                    else 0
                ),
                "read_rate": (
                    round(campaign.read_count / campaign.delivered_count * 100, 1)
                    if campaign.delivered_count
                    else 0
                ),
            }
        )
