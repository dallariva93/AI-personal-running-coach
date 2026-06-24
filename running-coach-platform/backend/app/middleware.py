"""HTTP middleware: security headers, request logging and optional auth.

The auth layer is intentionally simple: a single shared bearer token, enabled
only when ``API_TOKEN`` is configured. This is enough to safely expose the
personal dashboard on a free host without pulling in a full user/identity stack.
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("app.http")

# Paths reachable without authentication (platform probes, static assets).
_PUBLIC_PREFIXES = ("/api/health", "/api/ready", "/static", "/favicon.ico")

_LOGIN_HTML = """<!doctype html><html lang="it"><head><meta charset="utf-8">
<title>AI Running Coach — accesso</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet"
 href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
</head><body class="bg-body-tertiary">
<div class="container" style="max-width:380px;margin-top:12vh">
  <h1 class="h4 mb-3">🏃 AI Running Coach</h1>
  {error}
  <form method="get" action="/">
    <label class="form-label">Token di accesso</label>
    <input class="form-control mb-3" type="password" name="token" autofocus required>
    <button class="btn btn-primary w-100" type="submit">Entra</button>
  </form>
</div></body></html>"""


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add a conservative set of security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        if get_settings().is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Attach a request id and log method, path, status and duration."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            logger.exception(
                "request error %s %s (%.1fms)", request.method, request.url.path, elapsed,
                extra={"ctx_request_id": request_id},
            )
            raise
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %d (%.1fms)", request.method, request.url.path, response.status_code, elapsed,
            extra={"ctx_request_id": request_id},
        )
        response.headers["X-Request-ID"] = request_id
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    """Gate the whole app behind a single bearer token when one is configured."""

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.auth_enabled or _is_public(request.url.path):
            return await call_next(request)

        token = _extract_token(request)
        if token and _constant_time_eq(token, settings.api_token):
            response = await call_next(request)
            # Persist the token as a cookie when supplied via query string.
            if request.query_params.get("token"):
                response.set_cookie(
                    "coach_token", token, httponly=True, samesite="lax",
                    secure=settings.is_production, max_age=60 * 60 * 24 * 30,
                )
            return response

        if request.url.path.startswith("/api") or request.url.path.startswith("/ui"):
            return JSONResponse({"detail": "Non autorizzato"}, status_code=401)
        error = ""
        if request.query_params.get("token"):
            error = '<div class="alert alert-danger py-2">Token non valido.</div>'
        return HTMLResponse(_LOGIN_HTML.format(error=error), status_code=401)


def _is_public(path: str) -> bool:
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("token") or request.cookies.get("coach_token")


def _constant_time_eq(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a, b)
