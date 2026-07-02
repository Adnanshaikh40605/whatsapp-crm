from rest_framework import serializers


class SSOLoginSerializer(serializers.Serializer):
    api_key = serializers.CharField(required=False, allow_blank=True)
    embed_token = serializers.CharField(required=False, allow_blank=True)
    organization_id = serializers.UUIDField(required=False)
    external_user = serializers.DictField(required=False)


class SendTextSerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField(required=False)
    phone = serializers.CharField(required=False, allow_blank=True)
    type = serializers.ChoiceField(choices=["text"], default="text")
    message = serializers.CharField(max_length=4096)

    def validate(self, attrs):
        if not attrs.get("conversation_id") and not attrs.get("phone"):
            raise serializers.ValidationError("Provide conversation_id or phone.")
        return attrs


class SendTemplateSerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField(required=False)
    phone = serializers.CharField(required=False, allow_blank=True)
    template_name = serializers.CharField(max_length=255)
    language = serializers.CharField(max_length=10, default="en")
    body_params = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    def validate(self, attrs):
        if not attrs.get("conversation_id") and not attrs.get("phone"):
            raise serializers.ValidationError("Provide conversation_id or phone.")
        return attrs


class SendMediaSerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField(required=False)
    phone = serializers.CharField(required=False, allow_blank=True)
    type = serializers.ChoiceField(choices=["image", "video", "document", "audio"])
    media_url = serializers.URLField()
    caption = serializers.CharField(required=False, allow_blank=True, max_length=1024)

    def validate(self, attrs):
        if not attrs.get("conversation_id") and not attrs.get("phone"):
            raise serializers.ValidationError("Provide conversation_id or phone.")
        return attrs
