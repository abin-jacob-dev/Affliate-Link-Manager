from django import template
from django.utils import timezone
from datetime import timedelta

register = template.Library()


@register.filter
def time_ago(value):
    """Convert a datetime to a human-readable 'time ago' string."""
    if not value:
        return ''
    
    if not timezone.is_aware(value):
        value = timezone.make_aware(value)
    
    now = timezone.now()
    diff = now - value
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return 'just now'
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f'{minutes}m ago'
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f'{hours}h ago'
    elif seconds < 604800:
        days = int(seconds // 86400)
        return f'{days}d ago'
    elif seconds < 2592000:
        weeks = int(seconds // 604800)
        return f'{weeks}w ago'
    elif seconds < 31536000:
        months = int(seconds // 2592000)
        return f'{months}mo ago'
    else:
        years = int(seconds // 31536000)
        return f'{years}y ago'


@register.filter
def truncate_url(value, length=50):
    """Truncate a URL to a maximum length for display."""
    if not value:
        return ''
    if len(value) > length:
        return value[:length] + '...'
    return value


@register.filter
def pluralize(value, singular='', plural='s'):
    """Simple pluralize filter."""
    try:
        count = int(value)
        if count == 1:
            return singular
        return plural
    except (ValueError, TypeError):
        return plural


@register.filter
def percentage(value, total):
    """Calculate percentage."""
    try:
        if total and int(total) > 0:
            return round((int(value) / int(total)) * 100)
        return 0
    except (ValueError, TypeError):
        return 0


@register.simple_tag
def active_class(current_tab, tab_name):
    """Return active class if the current tab matches tab_name."""
    return 'active' if current_tab == tab_name else ''


@register.filter
def format_number(value):
    """Format large numbers with K/M suffixes."""
    try:
        num = int(value)
        if num >= 1000000:
            return f'{num / 1000000:.1f}M'
        elif num >= 1000:
            return f'{num / 1000:.1f}K'
        return str(num)
    except (ValueError, TypeError):
        return '0'
