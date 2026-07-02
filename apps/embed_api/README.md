# Embed API for external CRM clients (PestControl CRM, etc.)
#
# Base URL: https://www.driveronhire.ai/api/
#
# 1. SSO Login
#    POST /api/auth/sso-login/
#    { "api_key": "wf_...", "external_user": { "id": "1", "name": "Adnan", "role": "staff" } }
#
# 2. Use returned access_token:
#    Authorization: Bearer <access_token>
#
# 3. WebSocket: wss://www.driveronhire.ai/ws/inbox/?token=<access_token>
#
# Generate API keys in WhatsFlow: Settings → Platform → API Keys (scopes: embed, inbox)
