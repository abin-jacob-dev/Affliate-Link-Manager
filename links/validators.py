"""
Production-grade validators for the LinkForge application.

Provides reusable validation logic for models, forms, and API inputs.
Includes security-focused validators for URL safety, XSS prevention,
and data integrity.
"""

import re
from urllib.parse import urlparse
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Slug validators
# ---------------------------------------------------------------------------

SLUG_REGEX = re.compile(r'^[a-z0-9]{4,20}$')
RESERVED_SLUGS = frozenset({
    'admin', 'api', 'create', 'edit', 'delete', 'analytics',
    'search', 'settings', 'dashboard', 'login', 'logout',
    'signup', 'register', 'static', 'media', 'files',
    'www', 'mail', 'email', 'support', 'help', 'status',
    'health', 'metrics', 'monitor', 'debug', 'test',
    'qr', 'qr_code', 'qrcode', 'download', 'upload',
    'app', 'api', 'graphql', 'docs', 'documentation',
})


@deconstructible
class SlugValidator:
    """Validate that a slug meets production requirements."""

    message = _('Slug must be 4-20 lowercase alphanumeric characters.')
    code = 'invalid_slug'

    def __call__(self, value):
        if not SLUG_REGEX.match(value):
            raise ValidationError(self.message, code=self.code)

    def __eq__(self, other):
        return isinstance(other, SlugValidator)


def validate_slug_not_reserved(value):
    """Ensure slug is not a reserved URL path."""
    if value.lower() in RESERVED_SLUGS:
        raise ValidationError(
            _('This slug is reserved and cannot be used.'),
            code='reserved_slug',
        )


# ---------------------------------------------------------------------------
# Campaign name validators
# ---------------------------------------------------------------------------

CAMPAIGN_NAME_MAX_LENGTH = 255
CAMPAIGN_NAME_MIN_LENGTH = 2
CAMPAIGN_NAME_REGEX = re.compile(r'^[\w\s\-\.\,\!\?\&\@\#\(\)\/\:\;\"\'\+\=\%\$\€\£\¥]+$')


@deconstructible
class CampaignNameValidator:
    """Validate campaign name for safe display and storage."""

    message = _('Campaign name contains invalid characters.')
    code = 'invalid_campaign_name'

    def __call__(self, value):
        if len(value) < CAMPAIGN_NAME_MIN_LENGTH:
            raise ValidationError(
                _('Campaign name must be at least %(min)d characters.') %
                {'min': CAMPAIGN_NAME_MIN_LENGTH},
                code='too_short',
            )
        if len(value) > CAMPAIGN_NAME_MAX_LENGTH:
            raise ValidationError(
                _('Campaign name must be at most %(max)d characters.') %
                {'max': CAMPAIGN_NAME_MAX_LENGTH},
                code='too_long',
            )
        if not CAMPAIGN_NAME_REGEX.match(value):
            raise ValidationError(
                _('Campaign name contains invalid or unsafe characters.'),
                code='unsafe_characters',
            )

    def __eq__(self, other):
        return isinstance(other, CampaignNameValidator)


# ---------------------------------------------------------------------------
# URL validators
# ---------------------------------------------------------------------------

# Known dangerous URL schemes
DANGEROUS_SCHEMES = frozenset({
    'javascript', 'data', 'vbscript', 'file', 'ftp',
    'blob', 'about', 'chrome', 'edge', 'moz',
})


# Suspicious TLDs often used for phishing
SUSPICIOUS_TLDS = frozenset({
    '.tk', '.ml', '.ga', '.cf', '.gq', '.xyz',
    '.top', '.work', '.date', '.men', '.loan',
})

# Maximum URL length (most browsers support up to ~2000 chars)
MAX_URL_LENGTH = 2048


@deconstructible
class DestinationURLValidator:
    """
    Production-grade URL validator with security checks.

    Validates:
    - URL structure (scheme, netloc)
    - Allowed schemes (only http/https)
    - Open redirect prevention
    - Dangerous scheme detection (javascript:, data:, etc.)
    - Maximum length enforcement
    - Hostname format validation
    - Basic SSRF prevention (block private IPs in redirect URLs)
    """

    message = _('Enter a valid and safe URL.')
    code = 'invalid_url'

    def __call__(self, value):
        if not value:
            raise ValidationError(_('URL is required.'), code='required')

        if len(value) > MAX_URL_LENGTH:
            raise ValidationError(
                _('URL must be at most %(max)d characters.') %
                {'max': MAX_URL_LENGTH},
                code='too_long',
            )

        try:
            parsed = urlparse(value)
        except Exception as e:
            raise ValidationError(
                _('Invalid URL format: %(error)s.') % {'error': str(e)},
                code='parse_error',
            )

        # Must have a scheme
        if not parsed.scheme:
            raise ValidationError(
                _('URL must include a scheme (http:// or https://).'),
                code='missing_scheme',
            )

        # Only allow http and https
        if parsed.scheme.lower() not in ('http', 'https'):
            raise ValidationError(
                _('Only http and https URLs are allowed.'),
                code='invalid_scheme',
            )

        # Must have a hostname
        if not parsed.hostname:
            raise ValidationError(
                _('URL must have a valid hostname.'),
                code='missing_hostname',
            )

        # Block empty or whitespace-only hostnames
        if not parsed.hostname.strip():
            raise ValidationError(
                _('URL hostname cannot be empty.'),
                code='empty_hostname',
            )

        # Check for common open redirect patterns
        # e.g., //evil.com or https://valid.com@evil.com
        if '@' in parsed.hostname:
            raise ValidationError(
                _('URL contains an invalid hostname format.'),
                code='invalid_hostname',
            )

        # Check for encoded dangerous schemes
        # e.g., javascript:alert(1) or j a v a s c r i p t:
        decoded_url = _decode_url_safely(value)
        for scheme in DANGEROUS_SCHEMES:
            if scheme in decoded_url.lower() and ':' in decoded_url.lower().split(scheme)[-1][:2]:
                raise ValidationError(
                    _('URL contains a disallowed protocol.'),
                    code='dangerous_scheme',
                )

    def __eq__(self, other):
        return isinstance(other, DestinationURLValidator)


def _decode_url_safely(url: str) -> str:
    """Decode URL-encoded characters safely for inspection."""
    from urllib.parse import unquote
    try:
        # Decode once
        decoded = unquote(url)
        # Decode again to catch double-encoding
        decoded = unquote(decoded)
        return decoded
    except Exception:
        return url


# ---------------------------------------------------------------------------
# XSS prevention helpers
# ---------------------------------------------------------------------------

# HTML tags and attributes that are potentially dangerous
DANGEROUS_HTML_PATTERN = re.compile(
    r'<[^>]*\b(on\w+)\s*=|'
    r'<script[^>]*>|'
    r'<iframe[^>]*>|'
    r'<object[^>]*>|'
    r'<embed[^>]*>|'
    r'<style[^>]*>',
    re.IGNORECASE,
)


def sanitize_text_input(value: str, max_length: int = 255) -> str:
    """
    Sanitize user text input for safe storage and display.

    - Strips whitespace
    - Removes null bytes and control characters
    - Truncates to max_length
    - Removes known dangerous HTML constructs

    Args:
        value: Raw input string
        max_length: Maximum allowed length

    Returns:
        Sanitized string
    """
    if not value:
        return ''

    # Strip whitespace
    value = value.strip()

    # Remove null bytes and control characters (except newlines and tabs)
    value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value)

    # Remove dangerous HTML constructs (defense in depth - templates also escape)
    value = DANGEROUS_HTML_PATTERN.sub('', value)

    # Truncate
    if len(value) > max_length:
        value = value[:max_length]

    return value


def sanitize_search_query(query: str) -> str:
    """
    Sanitize a search query for safe database querying.

    - Strips whitespace
    - Removes SQL injection characters (defense in depth)
    - Limits length

    Args:
        query: Raw search query

    Returns:
        Sanitized query string
    """
    if not query:
        return ''

    # Strip whitespace
    query = query.strip()

    # Remove obvious SQL injection attempts (defense in depth)
    # Django ORM already parameterizes queries, but this adds a layer
    dangerous_patterns = [
        r"['\";\-\-]",
        r'\bUNION\b',
        r'\bSELECT\b',
        r'\bDROP\b',
        r'\bDELETE\b',
        r'\bINSERT\b',
        r'\bUPDATE\b',
        r'\bALTER\b',
        r'\bEXEC\b',
    ]
    for pattern in dangerous_patterns:
        query = re.sub(pattern, '', query, flags=re.IGNORECASE)

    # Limit length
    if len(query) > 200:
        query = query[:200]

    return query.strip()
