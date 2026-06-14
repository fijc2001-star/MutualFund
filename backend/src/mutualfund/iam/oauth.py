"""OAuth/OIDC providers behind a small interface (REQUIREMENTS §5.1).

Social-first; Google is the first provider, designed for more. The interface keeps
the protocol details in Authlib and lets tests inject a fake provider — we never
hand-roll the OAuth handshake.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import get_settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


@dataclass(frozen=True, slots=True)
class OAuthUserInfo:
    provider: str
    subject: str
    email: str
    email_verified: bool
    display_name: str | None


class OAuthProvider(Protocol):
    name: str

    def authorization_url(self, redirect_uri: str, state: str) -> str: ...

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthUserInfo: ...


class GoogleOAuthProvider:
    name = "google"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def authorization_url(self, redirect_uri: str, state: str) -> str:
        from authlib.integrations.httpx_client import AsyncOAuth2Client

        client = AsyncOAuth2Client(
            client_id=self._client_id,
            redirect_uri=redirect_uri,
            scope="openid email profile",
        )
        url, _ = client.create_authorization_url(
            GOOGLE_AUTH_URL, state=state, access_type="offline", prompt="consent"
        )
        return str(url)

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthUserInfo:
        from authlib.integrations.httpx_client import AsyncOAuth2Client

        client = AsyncOAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
            redirect_uri=redirect_uri,
        )
        await client.fetch_token(GOOGLE_TOKEN_URL, code=code, grant_type="authorization_code")
        resp = await client.get(GOOGLE_USERINFO_URL)
        resp.raise_for_status()
        data = resp.json()
        return OAuthUserInfo(
            provider=self.name,
            subject=str(data["sub"]),
            email=data["email"],
            email_verified=bool(data.get("email_verified", False)),
            display_name=data.get("name"),
        )


_registry: dict[str, OAuthProvider] = {}


def register_provider(provider: OAuthProvider) -> None:
    _registry[provider.name] = provider


def get_provider(name: str) -> OAuthProvider:
    if name not in _registry:
        raise KeyError(f"OAuth provider '{name}' is not registered")
    return _registry[name]


def init_providers() -> None:
    """Register configured providers at startup. Missing creds → provider skipped."""
    settings = get_settings()
    if settings.google_client_id and settings.google_client_secret:
        register_provider(
            GoogleOAuthProvider(settings.google_client_id, settings.google_client_secret)
        )
