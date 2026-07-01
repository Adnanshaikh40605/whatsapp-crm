"""Bundled pest promo image — available on production after deploy."""

from pathlib import Path

from django.conf import settings


def get_promo_image_path() -> str:
    candidates = [
        Path(settings.BASE_DIR) / "static" / "promo" / "pest_mosquito.png",
        Path(settings.BASE_DIR).parent / "ChatGPT Image Jun 24, 2026, 02_05_05 AM.png",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return ""
