"""Shared CORS defaults for WhatsFlow + external embed CRMs (PestControl CRM, etc.)."""

# Always allowed — merged with CORS_ALLOWED_ORIGINS from Railway / .env
DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "https://pestcontrol-crm-frontend.vercel.app",
    "https://dohadminpanel.vercel.app",
    "https://www.driveronhire.ai",
    "https://driveronhire.ai",
)


def merge_cors_origins(env_list: list[str] | tuple[str, ...] | None = None) -> list[str]:
    """Combine hardcoded embed origins with values from the CORS_ALLOWED_ORIGINS env var."""
    extra = [origin.strip() for origin in (env_list or []) if origin and origin.strip()]
    return sorted({*DEFAULT_CORS_ORIGINS, *extra})
