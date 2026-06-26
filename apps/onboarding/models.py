from django.db import models

from apps.core.models import TenantModel


class InstalledPack(TenantModel):
    pack_id = models.CharField(max_length=100, db_index=True)
    pack_name = models.CharField(max_length=255)
    industry = models.CharField(max_length=100)
    installed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("organization", "pack_id")]

    def __str__(self):
        return f"{self.pack_name} @ {self.organization.name}"
