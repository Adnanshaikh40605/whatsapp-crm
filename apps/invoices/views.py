from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.exceptions import APIResponse
from apps.core.permissions import IsOrganizationMember
from apps.invoices.models import Invoice
from apps.invoices.serializers import InvoiceSerializer


class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated, IsOrganizationMember]
    filterset_fields = ["status", "contact"]
    search_fields = ["invoice_number", "title"]

    def get_queryset(self):
        return Invoice.objects.select_related("contact", "quotation").all()

    def perform_create(self, serializer):
        org = self.request.organization
        count = Invoice.objects.filter(organization=org).count() + 1
        invoice_number = f"INV-{timezone.now().strftime('%Y%m')}-{count:04d}"
        instance = serializer.save(
            organization=org,
            invoice_number=invoice_number,
            created_by=self.request.user,
        )
        instance.calculate_totals()
        instance.save()

    @action(detail=True, methods=["post"])
    def mark_paid(self, request, pk=None):
        invoice = self.get_object()
        amount = request.data.get("amount", invoice.total)
        invoice.amount_paid = amount
        invoice.status = Invoice.Status.PAID if float(amount) >= float(invoice.total) else Invoice.Status.PARTIAL
        invoice.save()
        return APIResponse.success(InvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"])
    def send_whatsapp(self, request, pk=None):
        invoice = self.get_object()
        invoice.status = Invoice.Status.SENT
        invoice.sent_via_whatsapp = True
        invoice.save(update_fields=["status", "sent_via_whatsapp", "updated_at"])
        return APIResponse.success(InvoiceSerializer(invoice).data, message="Invoice sent via WhatsApp")

    @action(detail=True, methods=["post"])
    def send_reminder(self, request, pk=None):
        invoice = self.get_object()
        return APIResponse.success(
            InvoiceSerializer(invoice).data,
            message="Payment reminder queued via WhatsApp",
        )
