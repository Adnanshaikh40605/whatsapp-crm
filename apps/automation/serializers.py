from rest_framework import serializers

from apps.automation.models import BotFlow, BotReply, FollowUpSequence, Workflow


class WorkflowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workflow
        fields = "__all__"
        read_only_fields = ("id", "organization", "run_count", "created_at", "updated_at")


class FollowUpSequenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = FollowUpSequence
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")


class BotReplySerializer(serializers.ModelSerializer):
    class Meta:
        model = BotReply
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")


class BotFlowSerializer(serializers.ModelSerializer):
    replies = BotReplySerializer(many=True, read_only=True)
    reply_count = serializers.SerializerMethodField()

    class Meta:
        model = BotFlow
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")

    def get_reply_count(self, obj):
        return obj.replies.count()


class BotFlowListSerializer(serializers.ModelSerializer):
    reply_count = serializers.SerializerMethodField()

    class Meta:
        model = BotFlow
        fields = (
            "id",
            "title",
            "start_trigger",
            "trigger_type",
            "is_active",
            "reply_count",
            "created_at",
            "updated_at",
        )

    def get_reply_count(self, obj):
        return obj.replies.count()
