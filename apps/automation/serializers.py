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

    def validate(self, attrs):
        request = self.context.get("request")
        organization = getattr(request, "organization", None) if request else None
        bot_flow = attrs.get("bot_flow", getattr(self.instance, "bot_flow", None))
        reply_type = attrs.get(
            "reply_type",
            getattr(self.instance, "reply_type", BotReply.ReplyType.SIMPLE),
        )
        content = attrs.get("content", getattr(self.instance, "content", "")).strip()
        media_url = attrs.get("media_url", getattr(self.instance, "media_url", "")).strip()
        options = attrs.get("options", getattr(self.instance, "options", []))

        if bot_flow and organization and bot_flow.organization_id != organization.id:
            raise serializers.ValidationError({
                "bot_flow": ["The selected bot flow belongs to another project."],
            })
        if not content:
            raise serializers.ValidationError({
                "content": ["Message content is required."],
            })
        if reply_type == BotReply.ReplyType.MEDIA and not media_url:
            raise serializers.ValidationError({
                "media_url": ["Media URL is required for a media reply."],
            })
        if reply_type == BotReply.ReplyType.INTERACTIVE:
            if not isinstance(options, list):
                raise serializers.ValidationError({
                    "options": ["Interactive options must be a list."],
                })
            cleaned_options = [
                str(option).strip() for option in options if str(option).strip()
            ]
            if len(cleaned_options) < 2:
                raise serializers.ValidationError({
                    "options": ["Add at least two interactive options."],
                })
            if len(cleaned_options) > 10:
                raise serializers.ValidationError({
                    "options": ["A reply can have at most 10 options."],
                })
            attrs["options"] = cleaned_options
        return attrs


class BotFlowSerializer(serializers.ModelSerializer):
    replies = BotReplySerializer(many=True, read_only=True)
    reply_count = serializers.SerializerMethodField()

    class Meta:
        model = BotFlow
        fields = "__all__"
        read_only_fields = ("id", "organization", "created_at", "updated_at")

    def get_reply_count(self, obj):
        return obj.replies.count()

    def validate_flow_data(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Flow data must be an object.")
        nodes = value.get("nodes", [])
        edges = value.get("edges", [])
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise serializers.ValidationError("Flow nodes and edges must be lists.")

        node_ids = []
        start_nodes = 0
        for node in nodes:
            if not isinstance(node, dict) or not node.get("id") or not node.get("type"):
                raise serializers.ValidationError(
                    "Every flow node must have an id and type."
                )
            node_ids.append(str(node["id"]))
            if node["type"] == "start":
                start_nodes += 1
        if len(node_ids) != len(set(node_ids)):
            raise serializers.ValidationError("Flow node IDs must be unique.")
        if nodes and start_nodes != 1:
            raise serializers.ValidationError(
                "A flow must contain exactly one start node."
            )

        edge_ids = []
        known_nodes = set(node_ids)
        for edge in edges:
            if not isinstance(edge, dict):
                raise serializers.ValidationError("Every flow edge must be an object.")
            edge_id = str(edge.get("id", ""))
            source = str(edge.get("source", ""))
            target = str(edge.get("target", ""))
            if not edge_id or source not in known_nodes or target not in known_nodes:
                raise serializers.ValidationError(
                    "Every edge must have an id and reference existing source and target nodes."
                )
            edge_ids.append(edge_id)
        if len(edge_ids) != len(set(edge_ids)):
            raise serializers.ValidationError("Flow edge IDs must be unique.")

        return {
            **value,
            "version": value.get("version", 1),
            "nodes": nodes,
            "edges": edges,
        }


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
