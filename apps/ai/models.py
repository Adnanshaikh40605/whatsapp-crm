from django.db import models
from apps.core.models import TenantModel

class AIAgentProfile(TenantModel):
    name = models.CharField(max_length=255)
    industry = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, default="MessageSquare")
    color = models.CharField(max_length=20, default="#3b82f6")
    welcome_message = models.TextField()
    questions = models.JSONField(default=list, blank=True)
    qualify_keywords = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.organization.name})"
