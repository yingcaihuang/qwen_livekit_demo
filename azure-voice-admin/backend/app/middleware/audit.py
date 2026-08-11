"""Audit logging middleware — records every API request to audit_logs table."""

import json
import logging
import time
from collections.abc import Callable

import aiosqlite
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.database import DB_PATH

logger = logging.getLogger("audit")

# Paths to skip (health checks, static files, websockets)
SKIP_PATHS = ("/api/health", "/api/auth/me")
SKIP_PREFIXES = ("/ws/", "/_next/", "/assets/")

# Sensitive fields to redact from request body
SENSITIVE_FIELDS = {"password", "api_key", "client_secret", "secret", "token", "new_password"}


def _redact_body(body_str: str, max_length: int = 2000) -> str:
    """Redact sensitive fields and truncate body for storage."""
    if not body_str:
        return ""
    try:
        data = json.loads(body_str)
        if isinstance(data, dict):
            for key in list(data.keys()):
                if any(s in key.lower() for s in SENSITIVE_FIELDS):
                    data[key] = "***REDACTED***"
        result = json.dumps(data, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        result = body_str

    if len(result) > max_length:
        result = result[:max_length] + "...[truncated]"
    return result


class AuditMiddleware(BaseHTTPMiddleware):
    """Records every API request (excluding health/static) to audit_logs."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip non-API paths and high-frequency endpoints
        if (
            not path.startswith("/api/")
            and not path.startswith("/scim/")
            and not path.startswith("/internal/")
        ):
            return await call_next(request)
        if path in SKIP_PATHS:
            return await call_next(request)
        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return await call_next(request)

        start_time = time.time()

        # Read request body (for POST/PUT/PATCH)
        body_str = ""
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                body_str = body_bytes.decode("utf-8", errors="replace")
            except Exception:
                body_str = ""

        response = await call_next(request)

        duration_ms = int((time.time() - start_time) * 1000)

        # Extract user info from request state (set by auth dependency)
        user_id = None
        username = None
        try:
            if hasattr(request.state, "user") and request.state.user:
                user_id = request.state.user.id
                username = request.state.user.username
        except Exception:
            pass

        # Extract client IP
        ip_address = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not ip_address:
            ip_address = request.client.host if request.client else None

        # Write audit log asynchronously (best-effort, don't block response)
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO audit_logs (user_id, username, method, path, status_code, ip_address, user_agent, request_body, duration_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        username,
                        request.method,
                        path,
                        response.status_code,
                        ip_address,
                        request.headers.get("user-agent", "")[:500],
                        _redact_body(body_str) if body_str else None,
                        duration_ms,
                    ),
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

        return response
