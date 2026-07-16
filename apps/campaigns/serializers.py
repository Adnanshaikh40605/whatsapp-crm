from rest_framework import serializers

from apps.campaigns.models import Campaign, MediaAsset, WhatsAppTemplate


class MediaAssetSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = "__all__"
        read_only_fields = (
            "id",
            "organization",
            "file_size",
            "mime_type",
            "meta_media_id",
            "uploaded_by",
            "created_at",
            "updated_at",
        )

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not obj.file:
            return ""
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class WhatsAppTemplateSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    media_asset_display = serializers.CharField(source="media_asset.name", read_only=True)

    class Meta:
        model = WhatsAppTemplate
        fields = "__all__"
        read_only_fields = (
            "id",
            "organization",
            "whatsapp_template_id",
            "meta_status",
            "quality_rating",
            "rejected_reason",
            "last_synced_at",
            "created_at",
            "updated_at",
        )

    def get_display_name(self, obj):
        return f"{obj.name} ({obj.language})"

    def validate(self, attrs):
        request = self.context.get("request")
        organization = getattr(request, "organization", None) if request else None
        if not organization:
            return attrs

        name = attrs.get("name", getattr(self.instance, "name", ""))
        language = attrs.get("language", getattr(self.instance, "language", "en"))
        qs = WhatsAppTemplate.objects.filter(
            organization=organization,
            name=name,
            language=language,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({
                "name": ["This template name already exists for the selected language."],
            })
        return attrs


class CampaignSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)
    group_name = serializers.CharField(source="contact_group.name", read_only=True)
    template_display = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")

    def get_template_display(self, obj):
        if obj.template:
            return f"{obj.template.name} ({obj.template.language})"
        return ""
