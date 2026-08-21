from datetime import datetime, timedelta
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from analytics.models import Click


def record_click(link, request) -> Click:
    """
    Record a click event for analytics.
    
    Extracts detailed information from the HTTP request and saves it
    as a Click record associated with the given link.
    
    Args:
        link: The Link instance that was clicked
        request: The Django HttpRequest object
    
    Returns:
        The created Click instance
    """
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    referrer = request.META.get('HTTP_REFERER', '')
    
    # Get IP address (handling proxies)
    ip_address = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if ip_address:
        ip_address = ip_address.split(',')[0].strip()
    else:
        ip_address = request.META.get('REMOTE_ADDR', '')
    
    # Parse user agent for browser, OS, device info
    browser_info = parse_user_agent(user_agent)
    
    # Extract UTM parameters from query string
    utm_params = extract_utm_params(request)
    
    click = Click.objects.create(
        link=link,
        ip_address=ip_address,
        browser=browser_info.get('browser', ''),
        browser_version=browser_info.get('browser_version', ''),
        os=browser_info.get('os', ''),
        device=browser_info.get('device', ''),
        referrer=referrer,
        user_agent=user_agent,
        utm_source=utm_params.get('utm_source', ''),
        utm_medium=utm_params.get('utm_medium', ''),
        utm_campaign=utm_params.get('utm_campaign', ''),
        utm_content=utm_params.get('utm_content', ''),
        utm_term=utm_params.get('utm_term', ''),
    )
    return click


def parse_user_agent(user_agent: str) -> dict:
    """
    Parse a User-Agent string to extract browser, OS, and device info.
    
    Args:
        user_agent: The raw User-Agent header string
    
    Returns:
        Dictionary with browser, browser_version, os, and device keys
    """
    ua = user_agent.lower()
    result = {
        'browser': 'Unknown',
        'browser_version': '',
        'os': 'Unknown',
        'device': 'desktop',
    }
    
    # Device detection
    if 'mobile' in ua or 'android' in ua and 'mobile' in ua:
        result['device'] = 'mobile'
    elif 'tablet' in ua or 'ipad' in ua:
        result['device'] = 'tablet'
    
    # Browser detection
    if 'firefox/' in ua and not 'seamonkey' in ua:
        result['browser'] = 'Firefox'
    elif 'edge/' in ua or 'edg/' in ua or 'edgios/' in ua:
        result['browser'] = 'Edge'
    elif 'opr/' in ua or 'opera/' in ua:
        result['browser'] = 'Opera'
    elif 'chrome/' in ua and 'chromium' not in ua:
        result['browser'] = 'Chrome'
    elif 'safari/' in ua and 'chrome' not in ua:
        result['browser'] = 'Safari'
    
    # OS detection
    if 'windows' in ua:
        result['os'] = 'Windows'
    elif 'mac os' in ua or 'macintosh' in ua:
        result['os'] = 'macOS'
    elif 'linux' in ua and 'android' not in ua:
        result['os'] = 'Linux'
    elif 'android' in ua:
        result['os'] = 'Android'
    elif 'ios' in ua or 'iphone' in ua or 'ipad' in ua:
        result['os'] = 'iOS'
    
    return result


def extract_utm_params(request) -> dict:
    """
    Extract UTM tracking parameters from the request query string.
    
    Args:
        request: The Django HttpRequest object
    
    Returns:
        Dictionary of UTM parameters
    """
    params = {}
    utm_keys = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']
    
    for key in utm_keys:
        value = request.GET.get(key, '')
        if value:
            params[key] = value[:255]
    
    return params


def get_click_stats(link) -> dict:
    """
    Get comprehensive click statistics for a single link.
    
    Args:
        link: The Link instance
    
    Returns:
        Dictionary with various click statistics
    """
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)
    
    clicks = link.clicks.all()
    
    # Unique clicks are counted by unique IP addresses
    unique_clicks = clicks.values('ip_address').distinct().count()
    repeated_clicks = max(0, clicks.count() - unique_clicks)
    
    return {
        'total_clicks': clicks.count(),
        'today_clicks': clicks.filter(timestamp__gte=today_start).count(),
        'week_clicks': clicks.filter(timestamp__gte=week_start).count(),
        'month_clicks': clicks.filter(timestamp__gte=month_start).count(),
        'unique_clicks': unique_clicks,
        'repeated_clicks': repeated_clicks,
    }


def get_dashboard_stats() -> dict:
    """
    Get global dashboard statistics.
    
    Returns:
        Dictionary with overall statistics for the dashboard
    """
    from links.models import Link
    
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)
    
    total_links = Link.objects.count()
    active_links = Link.objects.filter(is_active=True).count()
    
    total_clicks = Click.objects.count()
    today_clicks = Click.objects.filter(timestamp__gte=today_start).count()
    week_clicks = Click.objects.filter(timestamp__gte=week_start).count()
    month_clicks = Click.objects.filter(timestamp__gte=month_start).count()
    
    # Top links by clicks
    top_links = Link.objects.filter(is_active=True).annotate(
        click_count=Count('clicks')
    ).order_by('-click_count')[:5]
    
    # Top referrers
    top_referrers = Click.objects.exclude(
        referrer=''
    ).values('referrer').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    # Top countries
    top_countries = Click.objects.exclude(
        country=''
    ).values('country').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    # Recent clicks
    recent_clicks = Click.objects.select_related('link').order_by('-timestamp')[:10]
    
    return {
        'total_links': total_links,
        'active_links': active_links,
        'total_clicks': total_clicks,
        'today_clicks': today_clicks,
        'week_clicks': week_clicks,
        'month_clicks': month_clicks,
        'top_links': top_links,
        'top_referrers': top_referrers,
        'top_countries': top_countries,
        'recent_clicks': recent_clicks,
    }


def get_chart_data(days: int = 30) -> dict:
    """
    Get daily click counts for chart rendering.
    
    Args:
        days: Number of days to include
    
    Returns:
        Dictionary with labels (dates) and data (counts)
    """
    now = timezone.now()
    start_date = now - timedelta(days=days)
    
    # Get daily click counts using cross-DB compatible TruncDate
    daily_clicks = (
        Click.objects
        .filter(timestamp__gte=start_date)
        .annotate(date=TruncDate('timestamp'))
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )
    
    # Build complete date range with zeroes
    date_counts = {}
    for entry in daily_clicks:
        date_key = entry['date']
        if date_key:
            date_str = date_key.isoformat() if hasattr(date_key, 'isoformat') else str(date_key)
            date_counts[date_str] = entry['count']
    
    labels = []
    data = []
    for i in range(days):
        day = (start_date + timedelta(days=i)).date()
        labels.append(day.isoformat())
        data.append(date_counts.get(day.isoformat(), 0))
    
    return {
        'labels': labels,
        'data': data,
    }
