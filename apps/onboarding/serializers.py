from rest_framework import serializers

from apps.onboarding.models import InstalledPack


class OnboardingStatusSerializer(serializers.Serializer):
    onboarding_completed = serializers.BooleanField()
    onboarding_step = serializers.IntegerField()
    whatsapp_connected = serializers.BooleanField()
    industry = serializers.CharField()
    onboarding_data = serializers.JSONField()
    ai_config = serializers.JSONField()


class WhatsAppConnectSerializer(serializers.Serializer):
    code = serializers.CharField(required=False, allow_blank=True)
    waba_id = serializers.CharField(required=False, allow_blank=True)
    phone_number_id = serializers.CharField(required=False, allow_blank=True)
    access_token = serializers.CharField(required=False, allow_blank=True)


class BusinessDetailsSerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    industry = serializers.CharField(required=False, allow_blank=True)
    team_size = serializers.CharField(required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True)


class TeamInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.CharField(default="agent")


class QualificationQuestionsSerializer(serializers.Serializer):
    questions = serializers.ListField(child=serializers.CharField(), min_length=1)


class AISetupSerializer(serializers.Serializer):
    business_description = serializers.CharField(min_length=3)
    qualification_questions = serializers.ListField(
        child=serializers.CharField(), required=False
    )


class AICampaignSerializer(serializers.Serializer):
    prompt = serializers.CharField(min_length=5)


class PackInstallSerializer(serializers.Serializer):
    pack_id = serializers.CharField()


class InstalledPackSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstalledPack
        fields = "__all__"
