import hashlib
import logging
from datetime import datetime, timezone as dt_timezone

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.api_platform.models import APIKey
from apps.core.models import set_current_organization
from apps.embed_api.permissions import EMBED_SCOPES
from apps.organizations.models import Organization

logger = logging.getLogger(__name__)
User = get_user_model()


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _client_ip(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def validate_api_key(raw_key: str, request=None) -> APIKey | None:
    if not raw_key or not raw_key.startswith("wf_"):
        return None
    key_hash = hash_api_key(raw_key)
    api_key = (
        APIKey.objects.select_related("organization", "created_by")
        .filter(key_hash=key_hash, is_active=True)
        .first()
    )
    if not api_key:
        return None
    if api_key.expires_at and api_key.expires_at < timezone.now():
        return None
    scopes = set(api_key.scopes or [])
    if scopes and not scopes.intersection(EMBED_SCOPES):
        return None
    client_ip = _client_ip(request)
    update_fields = ["last_used_at"]
    api_key.last_used_at = timezone.now()
    if client_ip:
        api_key.last_used_ip = client_ip
        update_fields.append("last_used_ip")
    api_key.save(update_fields=update_fields)
    return api_key


def decode_embed_token(token: str, organization_id: str | None = None) -> dict:
    secret = getattr(settings, "EMBED_SSO_SECRET", settings.SECRET_KEY)
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AuthenticationFailed("Invalid embed token.") from exc

    exp = payload.get("exp")
    if exp and datetime.fromtimestamp(exp, tz=dt_timezone.utc) < datetime.now(tz=dt_timezone.utc):
        raise AuthenticationFailed("Embed token expired.")

    if organization_id and organization_id not in {"", "None"} and str(payload.get("organization_id", "")) != str(organization_id):
        raise AuthenticationFailed("Embed token organization mismatch.")

    return payload


class EmbedAPIKeyAuthentication(authentication.BaseAuthentication):
    """Authenticate embed requests using Bearer wf_* API keys."""

    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode()
        if not header.startswith(f"{self.keyword} "):
            return None

        raw = header[len(self.keyword) + 1 :].strip()
        if not raw.startswith("wf_"):
            return None

        api_key = validate_api_key(raw, request=request)
        if not api_key:
            raise AuthenticationFailed("Invalid or expired API key.")

        user = api_key.created_by or api_key.organization.owner
        if not user or not user.is_active:
            raise AuthenticationFailed("API key has no active user.")

        request.embed_api_key = api_key
        request.organization = api_key.organization
        set_current_organization(api_key.organization)
        return (user, api_key)


class EmbedJWTAuthentication(JWTAuthentication):
    """JWT from SSO login — attach organization from token claim."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if not result:
            return None
        user, token = result
        org_id = token.get("organization_id")
        if org_id:
            organization = Organization.objects.filter(id=org_id, is_active=True).first()
            if organization:
                request.organization = organization
                set_current_organization(organization)
        return user, token


class EmbedAuthentication(authentication.BaseAuthentication):
    """Try API key first, then SSO JWT."""

    def authenticate(self, request):
        key_auth = EmbedAPIKeyAuthentication()
        try:
            result = key_auth.authenticate(request)
            if result:
                return result
        except AuthenticationFailed:
            raise

        jwt_auth = EmbedJWTAuthentication()
        return jwt_auth.authenticate(request)
