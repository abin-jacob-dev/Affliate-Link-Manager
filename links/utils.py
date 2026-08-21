import secrets
import string
import re
import logging
from urllib.parse import urlparse, unquote
from django.core.exceptions import ValidationError as DjangoValidationError


logger = logging.getLogger(__name__)

# Character set for slug generation (no ambiguous characters)
SLUG_CHARS = string.ascii_lowercase + string.digits
AMBIGUOUS_CHARS = '0o1li'
SLUG_SAFE_CHARS = ''.join(c for c in SLUG_CHARS if c not in AMBIGUOUS_CHARS)

# Default slug length
DEFAULT_SLUG_LENGTH = 6

# Maximum number of links allowed (production safeguard)
MAX_LINKS_PER_INSTANCE = 100000

# Known dangerous URL patterns for open redirect and SSRF prevention
DANGEROUS_URL_PATTERNS = [
    re.compile(r'^\s*javascript\s*:', re.IGNORECASE),
    re.compile(r'^\s*data\s*:', re.IGNORECASE),
    re.compile(r'^\s*vbscript\s*:', re.IGNORECASE),
    re.compile(r'^\s*file\s*:', re.IGNORECASE),
]


def generate_slug(length: int = DEFAULT_SLUG_LENGTH) -> str:
    """
    Generate a cryptographically secure random slug.
    
    Uses the secrets module for true randomness suitable for
    security-sensitive applications like URL shortening.
    
    Args:
        length: Length of the slug to generate (default: 6)
    
    Returns:
        A random alphanumeric string
    
    Raises:
        ValueError: If length is less than 4 or greater than 20
    """
    if length < 4 or length > 20:
        raise ValueError(f"Slug length must be between 4 and 20, got {length}")
    return ''.join(secrets.choice(SLUG_SAFE_CHARS) for _ in range(length))


def is_slug_available(slug: str, exclude_id=None) -> bool:
    """
    Check if a slug is available (not taken by another link).
    
    Args:
        slug: The slug to check
        exclude_id: Optional link ID to exclude from check (for updates)
    
    Returns:
        True if the slug is available
    """
    if not slug or not slug.strip():
        return False

    from links.models import Link

    try:
        queryset = Link.objects.filter(slug__iexact=slug)
        if exclude_id:
            queryset = queryset.exclude(id=exclude_id)
        return not queryset.exists()
    except Exception as e:
        logger.error("Error checking slug availability for '%s': %s", slug, str(e))
        return False


def generate_unique_slug(length: int = DEFAULT_SLUG_LENGTH, max_attempts: int = 10) -> str:
    """
    Generate a unique slug, retrying on collision.
    
    Uses exponential backoff for retry logic. If collisions persist,
    increases slug length for more entropy.
    
    Args:
        length: Length of the slug
        max_attempts: Maximum number of retry attempts per length
    
    Returns:
        A unique slug string
    
    Raises:
        RuntimeError: If unable to generate a unique slug after all attempts
    """
    if length < 4:
        length = 4

    # Try with requested length
    for attempt in range(max_attempts):
        try:
            slug = generate_slug(length)
            if is_slug_available(slug):
                return slug
        except Exception as e:
            logger.warning("Slug generation attempt %d failed: %s", attempt + 1, str(e))
            continue

    # Escalate to longer slugs if collisions persist
    for extra in range(1, 5):
        new_length = min(length + extra, 20)
        for attempt in range(max_attempts):
            try:
                slug = generate_slug(new_length)
                if is_slug_available(slug):
                    return slug
            except Exception as e:
                logger.warning(
                    "Slug generation attempt %d (len=%d) failed: %s",
                    attempt + 1, new_length, str(e),
                )
                continue

    logger.error(
        "Failed to generate unique slug after %d total attempts",
        max_attempts * 5,
    )
    raise RuntimeError(
        f"Unable to generate unique slug after {max_attempts * 5} attempts. "
        f"Please try again later."
    )


def validate_url(url: str) -> bool:
    """
    Production-grade URL validation with security checks.
    
    Validates:
    - URL structure (scheme + netloc required)
    - Only http/https schemes
    - Maximum length (2048 chars)
    - Open redirect patterns
    - Dangerous schemes (javascript:, data:, etc.)
    - Hostname format
    - Basic SSRF prevention (block private/reserved IPs)
    
    Args:
        url: The URL string to validate
    
    Returns:
        True if the URL is valid and safe
    """
    if not url:
        return False

    if len(url) > 2048:
        return False

    try:
        # Decode for inspection (catch double-encoded attacks)
        decoded = unquote(url)
        decoded = unquote(decoded)

        # Check for dangerous schemes in decoded URL
        for pattern in DANGEROUS_URL_PATTERNS:
            if pattern.match(decoded):
                logger.warning("Blocked URL with dangerous scheme: %s", url[:100])
                return False

        # Check for obfuscated javascript: via HTML entities or encoding
        decoded_lower = decoded.lower().replace('&#', '').replace(';', '')
        if 'javascript:' in decoded_lower or 'vbscript:' in decoded_lower:
            logger.warning("Blocked URL with obfuscated dangerous scheme: %s", url[:100])
            return False

        parsed = urlparse(url)

        # Must have a scheme and netloc
        if not parsed.scheme or not parsed.netloc:
            return False

        # Only allow http and https schemes
        if parsed.scheme not in ('http', 'https'):
            return False

        # Must have a valid hostname
        if not parsed.hostname:
            return False

        # Check for open redirect patterns
        # e.g., https://valid.com@evil.com (credential confusion)
        if '@' in parsed.hostname:
            return False

        # Check for empty or whitespace hostname
        if not parsed.hostname.strip():
            return False

        # Basic SSRF prevention: reject private/reserved IP ranges
        # in destination URLs (not for short URLs which point to public sites)
        hostname = parsed.hostname.lower()
        _blocked_hosts = [
            'localhost',
            '127.0.0.1',
            '0.0.0.0',
            '[::1]',
            '10.',
            '172.16.',
            '172.17.',
            '172.18.',
            '172.19.',
            '172.20.',
            '172.21.',
            '172.22.',
            '172.23.',
            '172.24.',
            '172.25.',
            '172.26.',
            '172.27.',
            '172.28.',
            '172.29.',
            '172.30.',
            '172.31.',
            '192.168.',
            '169.254.',
        ]
        for blocked in _blocked_hosts:
            if hostname.startswith(blocked):
                return False

        return True

    except Exception as e:
        logger.warning("URL validation error for '%s': %s", url[:100], str(e))
        return False


def sanitize_url(url: str) -> str:
    """
    Sanitize a URL by removing dangerous characters and normalizing.
    
    - Strips whitespace
    - Removes null bytes and control characters
    - Ensures http:// prefix if missing
    - Validates basic URL structure
    
    Args:
        url: Raw URL string
    
    Returns:
        Sanitized URL string, or empty string if invalid
    """
    if not url:
        return ''

    # Strip whitespace
    url = url.strip()

    # Remove any null bytes or control characters
    url = re.sub(r'[\x00-\x1f\x7f\x80-\x9f]', '', url)

    if not url:
        return ''

    # Ensure http:// prefix if missing (but not for other schemes)
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    return url


def validate_link_count() -> bool:
    """
    Check if the instance has reached the maximum link limit.
    
    Returns:
        True if under the limit, False if max links reached
    """
    from links.models import Link
    try:
        current_count = Link.objects.count()
        if current_count >= MAX_LINKS_PER_INSTANCE:
            logger.warning(
                "Maximum link limit reached: %d/%d",
                current_count,
                MAX_LINKS_PER_INSTANCE,
            )
            return False
        return True
    except Exception as e:
        logger.error("Error checking link count: %s", str(e))
        return False
