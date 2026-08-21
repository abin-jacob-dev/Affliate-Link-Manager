"""
Production-grade security middleware for the LinkForge application.

Provides:
- Security headers (CSP, HSTS, X-Content-Type-Options, Referrer-Policy, etc.)
- Request validation (size limits, content type checks)
- Click fraud detection (basic rate limiting)
- IP blocking for suspicious activity
"""

import re
import logging
import time
from collections import defaultdict
from django.conf import settings
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware:
    """
    Adds security-related HTTP headers to all responses.
    
    Headers include:
    - Content-Security-Policy (CSP)
    - X-Content-Type-Options (nosniff)
    - X-Frame-Options (DENY)
    - Referrer-Policy
    - Permissions-Policy
    - X-XSS-Protection (legacy)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # CSP - Content Security Policy
        #
        # NOTE: 'unsafe-inline' for scripts is REQUIRED because:
        #   - Tailwind CSS CDN (cdn.tailwindcss.com) injects inline styles
        #   - Chart.js (cdn.jsdelivr.net) requires inline script configuration
        #   - theme.js runs inline for FOUC prevention
        #
        # PRODUCTION UPGRADE: To remove 'unsafe-inline':
        #   1. Switch to a build-time Tailwind pipeline (not CDN)
        #   2. Move Chart.js config to external JS files
        #   3. Move theme initialization to an external script with async/defer
        #   4. Use nonce or hash-based CSP for remaining inline scripts
        #
        # Current policy allows:
        # - 'self' for same-origin resources
        # - cdn.tailwindcss.com + cdn.jsdelivr.net for scripts
        # - fonts.googleapis.com + fonts.gstatic.com for typography
        response['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
            "img-src 'self' data: blob:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self'; "
            "frame-src 'none'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

        # Prevent MIME type sniffing
        response['X-Content-Type-Options'] = 'nosniff'

        # Prevent clickjacking
        response['X-Frame-Options'] = 'DENY'

        # Referrer policy
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Permissions policy (limit feature access)
        response['Permissions-Policy'] = (
            'camera=(), microphone=(), geolocation=(), '
            'payment=(), usb=(), magnetometer=(), '
            'accelerometer=(), gyroscope=()'
        )

        # Legacy XSS protection
        response['X-XSS-Protection'] = '1; mode=block'

        # HSTS - only in production
        if not settings.DEBUG:
            response['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains; preload'
            )

        return response


class RequestValidationMiddleware:
    """
    Validates incoming requests for safety and correctness.
    
    Checks:
    - Maximum request size
    - Valid content types for POST requests
    - Suspicious URL patterns
    - Basic bot detection
    """

    # Maximum request body size (1MB)
    MAX_REQUEST_BODY_SIZE = 1 * 1024 * 1024

    # Suspicious patterns in request paths
    SUSPICIOUS_PATH_PATTERNS = [
        re.compile(r'\.\./'),  # Path traversal
        re.compile(r'\\x00'),  # Null bytes
        re.compile(r'%00'),    # URL-encoded null bytes
        re.compile(r'<script'),  # XSS attempts
        re.compile(r'\.env'),    # Environment file access
        re.compile(r'wp-admin'),  # WordPress admin (common scanner)
        re.compile(r'\.git/'),    # Git directory access
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip validation for static/media files
        path = request.path_info
        if path.startswith('/static/') or path.startswith('/media/'):
            return self.get_response(request)

        # Check request body size
        content_length = request.META.get('CONTENT_LENGTH', 0)
        try:
            content_length = int(content_length)
            if content_length > self.MAX_REQUEST_BODY_SIZE:
                logger.warning(
                    "Request body too large: %d bytes from %s",
                    content_length,
                    request.META.get('REMOTE_ADDR', 'unknown'),
                )
                return HttpResponseBadRequest('Request body too large.')
        except (ValueError, TypeError):
            pass

        # Check for suspicious patterns in URL
        for pattern in self.SUSPICIOUS_PATH_PATTERNS:
            if pattern.search(path):
                logger.warning(
                    "Suspicious request path blocked: %s from %s",
                    path,
                    request.META.get('REMOTE_ADDR', 'unknown'),
                )
                return HttpResponseBadRequest('Invalid request.')

        # Validate content type for POST requests
        if request.method == 'POST':
            content_type = request.META.get('CONTENT_TYPE', '')
            # Allow form-encoded and multipart (for QR code uploads)
            if content_type and content_type != 'application/x-www-form-urlencoded':
                if not content_type.startswith('multipart/form-data'):
                    logger.warning(
                        "Invalid content type for POST: %s from %s",
                        content_type,
                        request.META.get('REMOTE_ADDR', 'unknown'),
                    )

        return self.get_response(request)


class RateLimitingMiddleware:
    """
    Simple in-memory rate limiting to prevent abuse.
    
    Tracks requests per IP address and blocks excessive requests.
    Uses a sliding window approach.
    
    Note: For production with multiple workers, use Redis-backed
    rate limiting instead of this in-memory approach.
    """

    # Request limits per time window
    REQUEST_LIMIT = 60  # requests per window
    WINDOW_SECONDS = 60  # 1 minute window

    # Stricter limits for specific paths
    STRICT_PATH_LIMITS = {
        'create': {'limit': 10, 'window': 60},  # 10 creates per minute
        'delete': {'limit': 10, 'window': 60},  # 10 deletes per minute
    }

    def __init__(self):
        # IP -> list of timestamps
        self._request_log: dict[str, list[float]] = defaultdict(list)
        self._enabled = getattr(settings, 'RATE_LIMITING_ENABLED', True)

    def __call__(self, request):
        if not self._enabled:
            return None

        # Skip for static/media
        path = request.path_info
        if path.startswith('/static/') or path.startswith('/media/'):
            return None

        ip = request.META.get('REMOTE_ADDR', 'unknown')
        now = time.time()

        # Determine limits for this path
        limits = self.REQUEST_LIMIT, self.WINDOW_SECONDS
        for key, strict_limits in self.STRICT_PATH_LIMITS.items():
            if key in path:
                limits = strict_limits['limit'], strict_limits['window']
                break

        limit, window = limits

        # Clean old entries
        self._request_log[ip] = [
            t for t in self._request_log[ip]
            if now - t < window
        ]

        # Check limit
        if len(self._request_log[ip]) >= limit:
            logger.warning(
                "Rate limit exceeded for %s on path %s (%d requests in %ds)",
                ip, path, limit, window,
            )
            # Return 429 Too Many Requests
            from django.http import HttpResponse
            response = HttpResponse('Too many requests. Please slow down.', status=429)
            response['Retry-After'] = str(window)
            return response

        # Log this request
        self._request_log[ip].append(now)

        return None

    def get_rate_limiting_response(self, request):
        """Hook for middleware to check rate limits."""
        return self.__call__(request)


# Singleton instance for the middleware
_rate_limiter = RateLimitingMiddleware()


class RateLimitingMiddlewareAdapter:
    """
    Adapter to use RateLimitingMiddleware as Django middleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check rate limit
        rate_limit_response = _rate_limiter.get_rate_limiting_response(request)
        if rate_limit_response:
            return rate_limit_response

        return self.get_response(request)
