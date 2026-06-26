from django.contrib import admin

from apps.organizations.models import Organization, OrganizationMembership


class OrganizationMembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "plan", "owner", "is_active", "created_at")
    search_fields = ("name", "slug")
    list_filter = ("plan", "is_active")
    inlines = [OrganizationMembershipInline]


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_active", "is_default")
    list_filter = ("role", "is_active")
