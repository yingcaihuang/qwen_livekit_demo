"""OIDC service: handles Authentik SSO discovery, authorization, token exchange, and verification."""

import base64
import hashlib
import logging
import secrets
from typing import Any

import aiohttp
from jose import JWTError, jwt

logger = logging.getLogger(__name__)


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256).

    Returns (code_verifier, code_challenge).
    """
    code_verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def generate_state() -> str:
    """Generate a random state parameter."""
    return secrets.token_urlsafe(24)


def generate_nonce() -> str:
    """Generate a random nonce."""
    return secrets.token_urlsafe(24)


async def discover(discovery_url: str) -> dict[str, Any]:
    """Fetch OIDC discovery document and return endpoint URLs."""
    async with aiohttp.ClientSession() as session:
        async with session.get(discovery_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            return await resp.json()


def build_authorization_url(
    *,
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    scopes: str,
    state: str,
    nonce: str,
    code_challenge: str,
) -> str:
    """Build the OIDC authorization URL with PKCE."""
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{authorization_endpoint}?{urlencode(params)}"


async def exchange_code(
    *,
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """Exchange authorization code for tokens."""
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            token_endpoint,
            data=data,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()


async def fetch_jwks(jwks_uri: str) -> dict[str, Any]:
    """Fetch the JWKS (JSON Web Key Set) from the IdP."""
    async with aiohttp.ClientSession() as session:
        async with session.get(jwks_uri, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            return await resp.json()


def verify_id_token(
    id_token: str,
    *,
    jwks: dict[str, Any],
    issuer: str,
    audience: str,
    nonce: str,
) -> dict[str, Any]:
    """Verify and decode an ID token using JWKS.

    Validates signature, issuer, audience, expiration, and nonce.
    Raises JWTError on any validation failure.
    """
    try:
        payload = jwt.decode(
            id_token,
            jwks,
            algorithms=["RS256", "ES256"],
            audience=audience,
            issuer=issuer,
        )
    except JWTError:
        raise

    # Verify nonce
    if payload.get("nonce") != nonce:
        raise JWTError("Nonce mismatch")

    return payload


async def fetch_userinfo(userinfo_endpoint: str, access_token: str) -> dict[str, Any]:
    """Fetch user info from the IdP's userinfo endpoint."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
