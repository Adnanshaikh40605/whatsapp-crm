from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.exceptions import APIResponse
from apps.core.models import set_current_organization
from apps.core.rbac import get_membership
from apps.crm.models import Contact
from apps.embed_api.authentication import decode_embed_token, validate_api_key
from apps.embed_api.permissions import embed_permissions, map_external_role, map_org_role
from apps.embed_api.serializers import (
    SSOLoginSerializer,
    SendMediaSerializer,
    SendTemplateSerializer,
    SendTextSerializer,
)
from apps.embed_api.services import (
    get_or_create_conversation,
    normalize_phone,
    queue_outbound_message,
    resolve_conversation,
    serialize_conversation_detail,
    serialize_conversation_list_item,
    serialize_customer,
)
from apps.inbox.models import Conversation, Message
from apps.inbox.realtime import serialize_ws_message
from apps.embed_api.authentication import EmbedAuthentication
from rest_framework.permissions import IsAuthenticated
from apps.campaigns.ecard_tracking import (
    DEFAULT_ECARD_DESTINATION,
    create_tracked_link,
    find_url_button_index,
    serialize_click,
    serialize_link,
    url_button_is_dynamic,
)
from apps.campaigns.models import ECardClick, ECardTrackedLink

User = get_user_model()


def _issue_tokens(user, organization, embed_role: str) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["organization_id"] = str(organization.id)
    refresh["embed_role"] = embed_role
    access = refresh.access_token
    access["organization_id"] = str(organization.id)
    access["embed_role"] = embed_role
    return {
        "access_token": str(access),
        "refresh_token": str(refresh),
    }


def _user_payload(user, embed_role: str) -> dict:
    return {
        "id": str(user.id),
        "name": user.full_name or user.username,
        "email": user.email,
        "role": embed_role,
    }


def _organization_payload(organization) -> dict:
    return {
        "id": str(organization.id),
        "name": organization.name,
        "slug": organization.slug,
        "whatsapp_connected": bool(organization.whatsapp_phone_number_id),
    }


class SSOLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SSOLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        api_key_raw = (data.get("api_key") or "").strip()
        embed_token = (data.get("embed_token") or "").strip()
        org_id = data.get("organization_id")
        external_user = data.get("external_user") or {}

        if not api_key_raw and not embed_token:
            return APIResponse.error("api_key or embed_token is required.", status_code=400)

        api_key = validate_api_key(api_key_raw, request=request) if api_key_raw else None
        if api_key_raw and not api_key:
            return APIResponse.error(
                "Invalid or inactive API key. Use the latest key from WhatsFlow Settings → API Keys "
                "(regenerate replaces the old key).",
                status_code=401,
            )
        if not api_key and not embed_token:
            return APIResponse.error("api_key or embed_token is required.", status_code=400)

        payload: dict = {}
        organization = api_key.organization if api_key else None
        user = api_key.created_by if api_key else None

        if embed_token:
            payload = decode_embed_token(
                embed_token,
                organization_id=str(organization.id) if organization else str(org_id or ""),
            )
            if not organization:
                from apps.organizations.models import Organization
                organization = Organization.objects.filter(
                    id=payload.get("organization_id"),
                    is_active=True,
                ).first()
                if not organization:
                    return APIResponse.error("Organization not found.", status_code=400)

            ext_user_id = payload.get("sub") or payload.get("user_id")
            if ext_user_id:
                user = User.objects.filter(
                    email=f"embed+{ext_user_id}@{organization.slug}.embed",
                    is_active=True,
                ).first()
            if not user:
                user = organization.owner

        if not organization or not user:
            return APIResponse.error("Invalid credentials.", status_code=401)

        set_current_organization(organization)
        membership = get_membership(user, organization)
        embed_role = map_org_role(membership.role) if membership else map_external_role("staff")
        if external_user.get("role"):
            embed_role = map_external_role(external_user["role"])
        elif payload.get("role"):
            embed_role = map_external_role(payload["role"])

        tokens = _issue_tokens(user, organization, embed_role)
        return APIResponse.success({
            **tokens,
            "user": {
                **_user_payload(user, embed_role),
                "external_id": external_user.get("id") or payload.get("sub"),
            },
            "organization": _organization_payload(organization),
            "permissions": embed_permissions(embed_role),
        })


class EmbedAPIView(APIView):
    authentication_classes = [EmbedAuthentication]
    permission_classes = [IsAuthenticated]

    def get_organization(self, request):
        org = getattr(request, "organization", None)
        if org:
            return org
        from apps.core.models import get_current_organization
        return get_current_organization()


class ConversationListView(EmbedAPIView):
    def get(self, request):
        org = self.get_organization(request)
        qs = (
            Conversation.objects.filter(organization=org)
            .select_related("contact")
            .order_by("-last_message_at", "-created_at")
        )
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(contact__phone__icontains=search) | Q(contact__first_name__icontains=search)
            )
        return APIResponse.success({
            "results": [serialize_conversation_list_item(c) for c in qs[:200]],
        })


class ConversationDetailView(EmbedAPIView):
    def get(self, request, conversation_id):
        org = self.get_organization(request)
        try:
            conversation = Conversation.objects.select_related("contact").get(
                id=conversation_id,
                organization=org,
            )
        except Conversation.DoesNotExist:
            return APIResponse.error("Conversation not found.", status_code=404)
        return APIResponse.success(serialize_conversation_detail(conversation))


class SendMessageView(EmbedAPIView):
    def post(self, request):
        serializer = SendTextSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        org = self.get_organization(request)
        conversation = resolve_conversation(org, data)
        message = queue_outbound_message(
            organization=org,
            user=request.user,
            conversation=conversation,
            content=data["message"],
            message_type=Message.MessageType.TEXT,
        )
        return APIResponse.success(
            serialize_ws_message(message),
            message="Message queued",
            status_code=201,
        )


class SendTemplateView(EmbedAPIView):
    def post(self, request):
        serializer = SendTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        org = self.get_organization(request)
        conversation = resolve_conversation(org, data)
        from apps.campaigns.models import WhatsAppTemplate
        from apps.campaigns.meta import build_template_send_components
        from apps.core.whatsapp_service import WhatsAppService

        language = data.get("language") or "en"
        template = WhatsAppTemplate.objects.filter(
            organization=org,
            name=data["template_name"],
            language=language,
            status=WhatsAppTemplate.Status.APPROVED,
        ).first()
        # Fall back to en_US when caller sends "en"
        if not template and language == "en":
            template = WhatsAppTemplate.objects.filter(
                organization=org,
                name=data["template_name"],
                language="en_US",
                status=WhatsAppTemplate.Status.APPROVED,
            ).first()
        if not template:
            return APIResponse.error("Approved template not found.", status_code=400)

        url_button_params: dict[int, str] = {}
        tracked = None
        raw_button_params = data.get("button_url_params") or {}
        for key, value in raw_button_params.items():
            try:
                url_button_params[int(key)] = str(value)
            except (TypeError, ValueError):
                continue

        if data.get("track_ecard"):
            phone = data.get("phone") or getattr(conversation.contact, "phone", "")
            if not phone:
                return APIResponse.error("phone is required when track_ecard=true.", status_code=400)
            tracked = create_tracked_link(
                organization=org,
                phone=phone,
                destination_url=data.get("ecard_destination_url") or DEFAULT_ECARD_DESTINATION,
                customer_name=data.get("customer_name") or "",
                external_id=data.get("external_id") or "",
                template_name=template.name,
                created_by=request.user,
            )
            btn_index = find_url_button_index(template)
            if btn_index is None:
                return APIResponse.error(
                    "Template has no URL button to track. Use a template with a dynamic E-Brochure URL.",
                    status_code=400,
                )
            if not url_button_is_dynamic(template, btn_index):
                return APIResponse.error(
                    "Template E-Brochure URL is static. Create/approve a template whose URL ends with {{1}} "
                    "(e.g. https://api.driveronhire.ai/r/{{1}}) — see pest_ecard_utility.",
                    status_code=400,
                )
            url_button_params[btn_index] = tracked.token

        wa = WhatsAppService(org)
        components = build_template_send_components(
            template,
            data.get("body_params") or [],
            wa=wa,
            url_button_params=url_button_params or None,
        )
        message = queue_outbound_message(
            organization=org,
            user=request.user,
            conversation=conversation,
            content=f"Template: {template.name}",
            message_type=Message.MessageType.TEMPLATE,
            template_name=template.name,
            template_language=template.language,
            template_components=components,
        )
        payload = serialize_ws_message(message)
        if tracked:
            payload["ecard_tracking"] = serialize_link(tracked)
        return APIResponse.success(
            payload,
            message="Template queued",
            status_code=201,
        )


class ECardTrackingListView(EmbedAPIView):
    """List e-card / brochure clicks for the Pest Control CRM tracking page."""

    def get(self, request):
        org = self.get_organization(request)
        qs = (
            ECardClick.objects.filter(organization=org)
            .select_related("link")
            .order_by("-clicked_at")
        )
        phone = (request.query_params.get("phone") or "").strip()
        if phone:
            qs = qs.filter(phone__icontains=normalize_phone(phone).replace("+", ""))
        external_id = (request.query_params.get("external_id") or "").strip()
        if external_id:
            qs = qs.filter(external_id=external_id)

        try:
            limit = min(int(request.query_params.get("limit") or 100), 500)
        except ValueError:
            limit = 100

        items = [serialize_click(c) for c in qs[:limit]]
        return APIResponse.success({
            "results": items,
            "count": len(items),
            "total_clicks": ECardClick.objects.filter(organization=org).count(),
            "unique_phones": (
                ECardClick.objects.filter(organization=org)
                .values("phone")
                .distinct()
                .count()
            ),
        })


class ECardTrackedLinkListView(EmbedAPIView):
    """List tracked links, or POST to create a test tracking link without sending WhatsApp."""

    def get(self, request):
        org = self.get_organization(request)
        qs = ECardTrackedLink.objects.filter(organization=org).order_by("-created_at")
        try:
            limit = min(int(request.query_params.get("limit") or 100), 500)
        except ValueError:
            limit = 100
        items = [serialize_link(link) for link in qs[:limit]]
        return APIResponse.success({"results": items, "count": len(items)})

    def post(self, request):
        """Create a tracking link for testing clicks (no WhatsApp send)."""
        org = self.get_organization(request)
        phone = (request.data.get("phone") or "").strip()
        if not phone:
            return APIResponse.error("phone is required.", status_code=400)
        link = create_tracked_link(
            organization=org,
            phone=phone,
            destination_url=request.data.get("ecard_destination_url") or DEFAULT_ECARD_DESTINATION,
            customer_name=request.data.get("customer_name") or "",
            external_id=request.data.get("external_id") or "",
            template_name=request.data.get("template_name") or "test",
            created_by=request.user,
        )
        return APIResponse.success(serialize_link(link), message="Tracking link created", status_code=201)


class SendMediaView(EmbedAPIView):
    def post(self, request):
        serializer = SendMediaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        org = self.get_organization(request)
        conversation = resolve_conversation(org, data)
        type_map = {
            "image": Message.MessageType.IMAGE,
            "video": Message.MessageType.VIDEO,
            "document": Message.MessageType.DOCUMENT,
            "audio": Message.MessageType.AUDIO,
        }
        message = queue_outbound_message(
            organization=org,
            user=request.user,
            conversation=conversation,
            content=data.get("caption", ""),
            message_type=type_map[data["type"]],
            media_url=data["media_url"],
        )
        return APIResponse.success(
            serialize_ws_message(message),
            message="Media queued",
            status_code=201,
        )


class CustomerDetailView(EmbedAPIView):
    def get(self, request, phone):
        org = self.get_organization(request)
        normalized = normalize_phone(phone)
        contact = Contact.objects.filter(organization=org, phone=normalized).first()
        if not contact:
            return APIResponse.error("Customer not found.", status_code=404)
        return APIResponse.success(serialize_customer(contact))
