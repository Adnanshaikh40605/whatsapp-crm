from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.exceptions import APIResponse
from apps.core.permissions import IsOrganizationMember
from apps.quotes.models import Quotation
from apps.quotes.serializers import QuotationSerializer


class QuotationViewSet(viewsets.ModelViewSet):
    serializer_class = QuotationSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ["status", "lead", "contact"]
    search_fields = ["quote_number", "title"]

    def get_queryset(self):
        return Quotation.objects.select_related("contact", "lead").all()

    def perform_create(self, serializer):
        org = self.request.organization
        count = Quotation.objects.filter(organization=org).count() + 1
        quote_number = f"QT-{timezone.now().strftime('%Y%m')}-{count:04d}"
        instance = serializer.save(
            organization=org,
            quote_number=quote_number,
            created_by=self.request.user,
        )
        instance.calculate_totals()
        instance.save()

    @action(detail=True, methods=["post"])
    def send_whatsapp(self, request, pk=None):
        quote = self.get_object()
        quote.status = Quotation.Status.SENT
        quote.sent_via_whatsapp = True
        quote.save(update_fields=["status", "sent_via_whatsapp", "updated_at"])
        return APIResponse.success(QuotationSerializer(quote).data, message="Quotation sent via WhatsApp")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        quote = self.get_object()
        quote.status = Quotation.Status.APPROVED
        quote.save(update_fields=["status", "updated_at"])
        return APIResponse.success(QuotationSerializer(quote).data)
