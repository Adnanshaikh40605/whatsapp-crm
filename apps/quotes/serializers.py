from rest_framework import serializers

from apps.quotes.models import Quotation


class QuotationSerializer(serializers.ModelSerializer):
    contact_name = serializers.CharField(source="contact.full_name", read_only=True)

    class Meta:
        model = Quotation
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")

    def create(self, validated_data):
        instance = Quotation(**validated_data)
        instance.calculate_totals()
        instance.save()
        return instance
