from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


def _client_ip(request):
    # Only trust REMOTE_ADDR by default. Configure your reverse proxy to set it correctly.
    return request.META.get("REMOTE_ADDR", "unknown")


class RateLimitMiddleware:
    """Small distributed rate limiter using Django's configured cache/Redis backend."""

    SAFE_PREFIXES = ("/static/", "/healthz/", "/service-worker.js", "/manifest.webmanifest")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(self.SAFE_PREFIXES):
            return self.get_response(request)
        limit = int(getattr(settings, "RATE_LIMIT_PER_MINUTE", 180))
        if request.method == "POST":
            limit = int(getattr(settings, "POST_RATE_LIMIT_PER_MINUTE", 40))
        bucket = int(time.time() // 60)
        key = f"rl:{_client_ip(request)}:{request.method}:{bucket}"
        try:
            added = cache.add(key, 1, timeout=75)
            if added:
                count = 1
            else:
                try:
                    count = cache.incr(key)
                except ValueError:
                    cache.set(key, 1, timeout=75)
                    count = 1
            if count > limit:
                return HttpResponse("Too many requests. Please try again shortly.", status=429, content_type="text/plain")
        except Exception:
            # Availability is more important than rate-limiter failure; the reverse proxy should also rate limit.
            pass
        return self.get_response(request)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault("X-Robots-Tag", "noindex" if request.path.startswith(("/admin/", "/ops/", "/analytics/", "/account/")) else "index, follow")
        if not request.path.startswith("/admin/"):
            response.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-src https:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            )
        return response


def _totp_code(secret: str, at_time: int | None = None, period: int = 30, digits: int = 6) -> str:
    at_time = int(at_time or time.time())
    key = base64.b32decode(secret.upper().replace(" ", "") + "=" * ((8 - len(secret) % 8) % 8), casefold=True)
    counter = int(at_time // period)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def validate_totp(secret: str, code: str) -> bool:
    code = (code or "").strip()
    if not secret or not code.isdigit():
        return False
    now = int(time.time())
    return any(hmac.compare_digest(_totp_code(secret, now + delta), code) for delta in (-30, 0, 30))


class StaffTOTP2FAMiddleware:
    """Optional staff-wide TOTP challenge. Enabled only when ADMIN_TOTP_SECRET is set."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        secret = getattr(settings, "ADMIN_TOTP_SECRET", "")
        user = getattr(request, "user", None)
        if not secret or not user or not user.is_authenticated or not user.is_staff:
            return self.get_response(request)
        allowed = (
            "/staff-2fa/",
            "/accounts/logout/",
            "/static/",
            "/healthz/",
        )
        if request.path.startswith(allowed) or request.session.get("staff_2fa_ok"):
            return self.get_response(request)
        target = reverse("staff-2fa") + "?" + urlencode({"next": request.get_full_path()})
        return redirect(target)
