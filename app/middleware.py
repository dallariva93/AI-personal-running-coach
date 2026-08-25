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

# Paths reachable without authentication (platform probes, static assets,
# and the Strava webhook/callback — called by Strava's servers, which can't carry our
# bearer token; the webhook is protected instead by the webhook verify-token handshake).
_PUBLIC_PREFIXES = (
    "/api/health",
    "/api/ready",
    "/api/strava/webhook",
    "/api/strava/callback",
    "/static",
    "/favicon.ico",
    # Discovery probes, which must be allowed through in order to 404.
    #
    # A client adding the MCP connector asks for
    # /.well-known/oauth-protected-resource to find out whether this server
    # needs OAuth. Behind the auth gate that request got a 401 with the login
    # page — which reads as "yes, there is an authorization server here", so the
    # client tries to register itself as an OAuth client, finds no registration
    # endpoint, and fails with "impossibile registrarsi con il servizio di
    # accesso". Nothing is served under this prefix, so letting it past the gate
    # produces the honest answer: 404, no OAuth, connect with the secret path.
    "/.well-known/",
)

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
        if not settings.auth_enabled or _is_public(request.url.path, settings):
            return await call_next(request)

        token = _extract_token(request)
        if token and _token_valid(token, settings):
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


def _is_public(path: str, settings=None) -> bool:  # noqa: ANN001 - Settings
    """Paths that bypass the bearer-token gate.

    The MCP mount is one of them **by design**: a Claude custom connector
    cannot attach an Authorization header, so the unguessable mount path is
    itself the credential (docs/MCP_CONNECTOR_ROADMAP.md, Fase 3). It is only
    ever mounted when explicitly configured, exposes read-only tools, and gets
    its own rate-limit bucket below.
    """
    if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return True
    settings = settings or get_settings()
    mcp_path = settings.mcp_mount_path
    return bool(mcp_path) and path.startswith(mcp_path)


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("token") or request.cookies.get("coach_token")


def _token_valid(presented: str, settings) -> bool:
    """Delegate to the auth service: a rotated token (hash in sync_state)
    overrides the env token (A10). Constant-time in both paths."""
    from app.services.auth_service import verify_api_token

    return verify_api_token(presented, settings)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-process token-bucket rate limiting on ``/api/*`` (A10).

    One bucket per (client IP, scope): the default scope allows
    ``rate_limit_per_minute`` requests/min; the Strava webhook gets its own,
    stricter bucket (``rate_limit_strava_per_minute``) because it is the only
    unauthenticated write endpoint. Platform probes (health/ready) and
    non-API paths are exempt. In-process state is enough for the current
    single-worker deploy — with multiple workers each keeps its own buckets,
    so the effective limit becomes N× the configured one (documented, like
    the Q5 cache; a shared store lands with G4).
    """

    _MAX_BUCKETS = 1024  # hard cap: prune oldest entries to bound memory

    def __init__(self, app) -> None:  # noqa: ANN001 - ASGI app
        super().__init__(app)
        # key -> [tokens, last_refill_monotonic]
        self._buckets: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        path = request.url.path
        mcp_path = settings.mcp_mount_path
        is_mcp = bool(mcp_path) and path.startswith(mcp_path)
        if not settings.rate_limit_enabled or _is_public_probe(path):
            return await call_next(request)
        if not path.startswith("/api") and not is_mcp:
            return await call_next(request)

        if is_mcp:
            # The MCP mount skips the auth middleware, so this bucket is the
            # only thing standing between a guessed URL and the tool layer.
            scope, per_minute = "mcp", settings.rate_limit_mcp_per_minute
        elif path.startswith("/api/strava/webhook"):
            scope, per_minute = "strava", settings.rate_limit_strava_per_minute
        else:
            scope, per_minute = "api", settings.rate_limit_per_minute

        client_ip = request.client.host if request.client else "unknown"
        if self._acquire(f"{scope}:{client_ip}", per_minute):
            return await call_next(request)

        logger.warning("Rate limit hit: %s %s (%s)", request.method, path, client_ip)
        return JSONResponse(
            {"detail": "Troppe richieste, riprova tra poco."},
            status_code=429,
            headers={"Retry-After": "60"},
        )

    def _acquire(self, key: str, per_minute: int) -> bool:
        """Classic token bucket: capacity == per_minute, refill per_minute/60 per s."""
        import time as _time

        now = _time.monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            if len(self._buckets) >= self._MAX_BUCKETS:
                oldest = min(self._buckets, key=lambda k: self._buckets[k][1])
                del self._buckets[oldest]
            bucket = [float(per_minute), now]
            self._buckets[key] = bucket
        tokens, last = bucket
        tokens = min(float(per_minute), tokens + (now - last) * per_minute / 60.0)
        if tokens < 1.0:
            bucket[0], bucket[1] = tokens, now
            return False
        bucket[0], bucket[1] = tokens - 1.0, now
        return True


def _is_public_probe(path: str) -> bool:
    """Health/readiness must never 429: Fly polls them to keep the app alive."""
    return path.startswith("/api/health") or path.startswith("/api/ready")
