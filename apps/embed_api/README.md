# Embed API for external CRM clients (PestControl CRM, etc.)
#
# Base URL (API): https://api.driveronhire.ai/api/
# Do NOT use www.driveronhire.ai for API calls — that is the WhatsFlow frontend (Vercel).
#
# 1. SSO Login
#    POST https://api.driveronhire.ai/api/auth/sso-login/
#    { "api_key": "wf_...", "external_user": { "id": "1", "name": "Adnan", "role": "staff" } }
#
# 2. Use returned access_token:
#    Authorization: Bearer <access_token>
#
# 3. WebSocket: wss://api.driveronhire.ai/ws/inbox/?token=<access_token>
#
# Generate API keys in WhatsFlow: Settings → API Keys (scopes: embed, inbox, read, write)
