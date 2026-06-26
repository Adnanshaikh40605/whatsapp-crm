from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.campaigns.models import Campaign
from apps.core.exceptions import APIResponse
from apps.core.models import get_current_organization
from apps.core.permissions import IsOrganizationMember
from apps.crm.models import Lead, PipelineStage
from apps.inbox.models import Conversation, Message
from apps.invoices.models import Invoice
from apps.quotes.models import Quotation


class ExecutiveDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        org = get_current_organization()
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        leads_total = Lead.objects.filter(organization=org, is_archived=False).count()
        leads_this_month = Lead.objects.filter(organization=org, created_at__gte=month_start).count()
        won_leads = Lead.objects.filter(organization=org, stage__is_won=True).count()
        conversion_rate = round(won_leads / leads_total * 100, 1) if leads_total else 0

        conversations_open = Conversation.objects.filter(organization=org, status="open").count()
        unread_conversations = Conversation.objects.filter(
            organization=org,
            unread_count__gt=0,
        ).aggregate(total=Sum("unread_count"))["total"] or 0
        messages_inbound = Message.objects.filter(
            organization=org, direction="inbound", created_at__gte=month_start
        ).count()

        campaigns = Campaign.objects.filter(organization=org)
        campaign_stats = campaigns.aggregate(
            total_sent=Sum("sent_count"),
            total_delivered=Sum("delivered_count"),
            total_read=Sum("read_count"),
            total_replies=Sum("reply_count"),
        )

        revenue = Invoice.objects.filter(
            organization=org, status="paid"
        ).aggregate(total=Sum("amount_paid"))["total"] or 0

        quotes_sent = Quotation.objects.filter(organization=org, status="sent").count()
        quotes_approved = Quotation.objects.filter(organization=org, status="approved").count()

        pipeline = []
        for stage in PipelineStage.objects.filter(organization=org).order_by("order"):
            count = stage.leads.filter(is_archived=False).count()
            pipeline.append({"stage": stage.name, "count": count, "color": stage.color})

        # Weekly lead trend (last 7 days)
        lead_trend = []
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).date()
            count = Lead.objects.filter(organization=org, created_at__date=day).count()
            lead_trend.append({"date": day.isoformat(), "leads": count})

        return APIResponse.success({
            "overview": {
                "total_leads": leads_total,
                "leads_this_month": leads_this_month,
                "conversion_rate": conversion_rate,
                "open_conversations": conversations_open,
                "unread_conversations": unread_conversations,
                "messages_this_month": messages_inbound,
                "revenue": float(revenue),
                "quotes_sent": quotes_sent,
                "quotes_approved": quotes_approved,
            },
            "campaigns": {
                "total": campaigns.count(),
                "sent": campaign_stats["total_sent"] or 0,
                "delivered": campaign_stats["total_delivered"] or 0,
                "read": campaign_stats["total_read"] or 0,
                "replies": campaign_stats["total_replies"] or 0,
            },
            "pipeline": pipeline,
            "lead_trend": lead_trend,
        })


class AgentPerformanceView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationMember]

    def get(self, request):
        org = get_current_organization()
        from apps.organizations.models import OrganizationMembership

        agents = []
        for membership in OrganizationMembership.objects.filter(
            organization=org, is_active=True, role__in=["agent", "manager", "owner", "admin"]
        ).select_related("user"):
            user = membership.user
            assigned_leads = Lead.objects.filter(organization=org, assigned_to=user).count()
            assigned_convs = Conversation.objects.filter(organization=org, assigned_to=user).count()
            agents.append({
                "name": user.full_name,
                "email": user.email,
                "role": membership.role,
                "leads": assigned_leads,
                "conversations": assigned_convs,
            })
        return APIResponse.success(agents)
