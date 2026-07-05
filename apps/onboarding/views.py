from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.core.exceptions import APIResponse
from apps.core.models import get_current_organization
from apps.core.permissions import IsOrgAdmin, IsOrganizationMember, IsOwnerOrAdmin
from apps.onboarding.data.industry_packs import INDUSTRY_PACKS
from apps.onboarding.serializers import (
    AICampaignSerializer,
    AISetupSerializer,
    BusinessDetailsSerializer,
    OnboardingStatusSerializer,
    PackInstallSerializer,
    QualificationQuestionsSerializer,
    TeamInviteSerializer,
    WhatsAppConnectSerializer,
)
from apps.onboarding.services import AICampaignBuilder, AISetupAssistant, PackInstaller, WorkspaceBootstrap
from apps.onboarding.whatsapp import WhatsAppConnectService
from apps.organizations.models import OrganizationMembership


class OnboardingStatusView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        org = get_current_organization()
        return APIResponse.success({
            "onboarding_completed": org.onboarding_completed,
            "onboarding_step": org.onboarding_step,
            "whatsapp_connected": org.whatsapp_connected,
            "industry": org.industry,
            "onboarding_data": org.onboarding_data,
            "ai_config": org.ai_config,
        })


class WhatsAppEmbeddedSignupConfigView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        org = get_current_organization()
        service = WhatsAppConnectService(org)
        return APIResponse.success(service.get_embedded_signup_config())


class WhatsAppConnectView(APIView):
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def post(self, request):
        org = get_current_organization()
        if org is None:
            return APIResponse.error("No organization selected", status_code=400)
        serializer = WhatsAppConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = WhatsAppConnectService(org)
        result = service.process_embedded_signup(
            code=serializer.validated_data.get("code", ""),
            waba_id=serializer.validated_data.get("waba_id", ""),
            phone_number_id=serializer.validated_data.get("phone_number_id", ""),
            access_token=serializer.validated_data.get("access_token", ""),
        )

        org.onboarding_data = {**org.onboarding_data, "whatsapp_connect": result}
        org.save(update_fields=["onboarding_data"])

        return APIResponse.success(result, message="WhatsApp connected successfully!")


class OnboardingStepView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def post(self, request, step):
        org = get_current_organization()
        step = int(step)

        if step == 2:
            ser = BusinessDetailsSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            for field, value in ser.validated_data.items():
                if value:
                    setattr(org, field if field != "name" else "name", value)
            org.onboarding_data = {**org.onboarding_data, "business_details": ser.validated_data}

        elif step == 3:
            invites = request.data.get("invites", [])
            org.onboarding_data = {**org.onboarding_data, "team_invites": invites}

        elif step == 4:
            ser = QualificationQuestionsSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            org.ai_config = {**org.ai_config, "qualification_questions": ser.validated_data["questions"]}
            org.onboarding_data = {**org.onboarding_data, "qualification_questions": ser.validated_data["questions"]}

        elif step == 5:
            ser = AISetupSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            assistant = AISetupAssistant()
            result = assistant.generate_setup(
                org,
                ser.validated_data["business_description"],
                ser.validated_data.get("qualification_questions"),
            )
            org.onboarding_data = {**org.onboarding_data, "ai_setup_result": result}

        elif step == 6:
            bootstrap = WorkspaceBootstrap(org)
            bootstrap.setup_default_pipeline()
            bootstrap.setup_default_automations()
            org.onboarding_completed = True

        org.onboarding_step = max(org.onboarding_step, step + 1)
        org.save()

        return APIResponse.success({
            "step": org.onboarding_step,
            "completed": org.onboarding_completed,
        })


class MarketplaceView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        org = get_current_organization()
        from apps.onboarding.models import InstalledPack
        installed = set(
            InstalledPack.objects.filter(organization=org).values_list("pack_id", flat=True)
        )
        packs = [{**p, "installed": p["id"] in installed} for p in INDUSTRY_PACKS]
        return APIResponse.success(packs)


class InstallPackView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def post(self, request):
        org = get_current_organization()
        ser = PackInstallSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        installer = PackInstaller(org)
        try:
            result = installer.install(ser.validated_data["pack_id"])
        except ValueError as e:
            return APIResponse.error(str(e), status_code=404)
        return APIResponse.success(result, message=f"{result['pack']} installed!")


class AISetupView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def post(self, request):
        org = get_current_organization()
        ser = AISetupSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        assistant = AISetupAssistant()
        result = assistant.generate_setup(
            org,
            ser.validated_data["business_description"],
            ser.validated_data.get("qualification_questions"),
        )
        return APIResponse.success(result, message="AI workspace configured!")


class AICampaignBuilderView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def post(self, request):
        org = get_current_organization()
        ser = AICampaignSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        builder = AICampaignBuilder()
        result = builder.generate(org, ser.validated_data["prompt"])
        return APIResponse.success(result, message="Campaign generated!")


class WhatsAppWebhookView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        from django.conf import settings as django_settings
        from django.http import HttpResponse

        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge", "")
        verify_token = getattr(django_settings, "WHATSAPP_VERIFY_TOKEN", "whatsflow_verify")
        if mode == "subscribe" and token == verify_token:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("Forbidden", status=403)

    def post(self, request):
        import logging

        from django.conf import settings as django_settings
        from django.http import HttpResponse
        from apps.inbox.tasks import process_inbound_webhook

        webhook_logger = logging.getLogger("apps.inbox.webhook")
        raw_body = request.body.decode("utf-8", errors="replace")
        webhook_logger.info("WhatsApp webhook received")
        webhook_logger.info("Raw WhatsApp webhook payload: %s", raw_body[:8000])

        app_secret = getattr(django_settings, "META_APP_SECRET", "")
        signature = request.headers.get("X-Hub-Signature-256", "")
        if app_secret:
            from apps.onboarding.whatsapp import WhatsAppConnectService

            if not WhatsAppConnectService.verify_webhook_signature(request.body, signature):
                webhook_logger.warning(
                    "WhatsApp webhook rejected: invalid signature (header=%s)",
                    signature[:32] + "..." if signature else "missing",
                )
                return HttpResponse("Invalid signature", status=403)
            webhook_logger.info("WhatsApp webhook signature verified")

        from apps.inbox.services import WebhookProcessor

        # Process synchronously so save + WebSocket broadcast happen immediately.
        # Heavy side effects (automation workflows) are still queued inside WebhookProcessor.
        try:
            result = WebhookProcessor(request.data).process()
            webhook_logger.info("WhatsApp webhook processed: %s", result)
        except Exception as exc:
            webhook_logger.exception("WhatsApp webhook sync processing failed: %s", exc)
            try:
                process_inbound_webhook.delay(request.data)
                webhook_logger.info("WhatsApp webhook queued for Celery retry")
            except Exception as queue_exc:
                webhook_logger.error("WhatsApp webhook Celery fallback failed: %s", queue_exc)
                return APIResponse.error("Webhook processing failed", status_code=500)
        return APIResponse.success({"status": "received"})
