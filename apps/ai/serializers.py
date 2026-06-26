from rest_framework import serializers
from apps.ai.models import AIAgentProfile

class AIAgentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIAgentProfile
        fields = [
            "id", "name", "industry", "icon", "color", 
            "welcome_message", "questions", "qualify_keywords", "is_active"
        ]
