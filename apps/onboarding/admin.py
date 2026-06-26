from django.contrib import admin

from apps.onboarding.models import InstalledPack


@admin.register(InstalledPack)
class InstalledPackAdmin(admin.ModelAdmin):
    list_display = ("pack_name", "industry", "organization", "installed_at")
