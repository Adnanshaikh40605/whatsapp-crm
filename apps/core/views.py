from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from apps.core.exceptions import APIResponse
from apps.organizations.models import OrganizationMembership

class CoreOptionsView(APIView):
    permission_classes = [AllowAny] 

    def get(self, request):
        roles = [{"id": r[0], "label": r[1]} for r in OrganizationMembership.Role.choices]
        industries = [
            {"id": "retail", "label": "Retail & E-commerce"},
            {"id": "real_estate", "label": "Real Estate"},
            {"id": "healthcare", "label": "Healthcare"},
            {"id": "education", "label": "Education"},
            {"id": "driver_service", "label": "Driver Service"},
            {"id": "pest_control", "label": "Pest Control"},
            {"id": "resort", "label": "Resorts & Travel"},
            {"id": "other", "label": "Other"},
        ]
        team_sizes = [
            {"id": "1-10", "label": "1-10"},
            {"id": "11-50", "label": "11-50"},
            {"id": "51-200", "label": "51-200"},
            {"id": "201+", "label": "201+"},
        ]

        return APIResponse.success({
            "roles": roles,
            "industries": industries,
            "team_sizes": team_sizes,
        })
