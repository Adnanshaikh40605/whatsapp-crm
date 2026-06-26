from rest_framework import serializers

from apps.invoices.models import Invoice


class InvoiceSerializer(serializers.ModelSerializer):
    contact_name = serializers.CharField(source="contact.full_name", read_only=True)
    balance_due = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")

    def get_balance_due(self, obj):
        return obj.balance_due
