from .base import *  # noqa: F403
from config.cors import merge_cors_origins

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

DATABASES = {
    "default": env.db(  # noqa: F405
        "DATABASE_URL",
        default="postgres://postgres:postgres@localhost:5432/whatsapp_saas",
    )
}

CORS_ALLOWED_ORIGINS = merge_cors_origins(env.list("CORS_ALLOWED_ORIGINS", default=[]))  # noqa: F405

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Local dev without Redis/Docker
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

CELERY_TASK_ALWAYS_EAGER = True

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    "anon": "1000/hour",
    "user": "10000/hour",
}
