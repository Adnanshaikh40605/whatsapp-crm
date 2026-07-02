from .base import *  # noqa: F403
from config.cors import merge_cors_origins

DEBUG = False

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DATABASES = {
    "default": env.db("DATABASE_URL"),  # noqa: F405
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Production CORS — env var from Railway merged with embed CRM defaults (see config/cors.py)
CORS_ALLOWED_ORIGINS = merge_cors_origins(env.list("CORS_ALLOWED_ORIGINS", default=[]))  # noqa: F405

WHATSAPP_WEBHOOK_URL = env(  # noqa: F405
    "WHATSAPP_WEBHOOK_URL",
    default="https://api.driveronhire.ai/api/v1/onboarding/webhooks/whatsapp/",
)

# Run Celery tasks inline until a dedicated worker service is deployed.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=True)  # noqa: F405

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
