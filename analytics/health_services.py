"""
LinkForge - Link Health Intelligence Service

Automatically scans all links to detect:
- Broken destinations (HTTP errors, timeouts)
- Redirect chain issues
- Stale links (not updated in months)
- Traffic drops (click trend analysis)
- SSL certificate problems
- Slow response times

Provides health scores, smart alerts, and fix suggestions.
"""

import json
import logging
import time
from datetime import timedelta
import requests
from django.db.models import Count, Q, Avg
from django.utils import timezone

from analytics.models import LinkHealth, Click
from links.models import Link

logger = logging.getLogger(__name__)

# Timeout for health checks (seconds)
HTTP_CHECK_TIMEOUT = 10

# Maximum redirects to follow
MAX_REDIRECTS = 10

# Thresholds
STALE_DAYS = 180           # Link not updated in 180 days = stale
WARNING_RESPONSE_MS = 3000  # Response over 3s = warning
CRITICAL_RESPONSE_MS = 8000 # Response over 8s = broken
TRAFFIC_DROP_PCT = 35       # Traffic drop over 35% = warning
MAX_HEALTHY_REDIRECTS = 2   # More than 2 redirects = warning
LOW_SCORE_THRESHOLD = 40    # Score below 40 = needs attention


def scan_all_links():
    """
    Scan all active links and update their health records.
    Returns summary of findings.
    """
    links = Link.objects.filter(is_active=True)
    results = {
        'scanned': 0,
        'healthy': 0,
        'warning': 0,
        'broken': 0,
        'stale': 0,
        'errors': 0,
    }

    for link in links:
        try:
            check_link_health(link)
            results['scanned'] += 1
        except Exception as e:
            logger.error("Health scan failed for link '%s': %s", link.slug, str(e))
            results['errors'] += 1

    # Aggregate results
    for status in ('healthy', 'warning', 'broken', 'stale'):
        results[status] = LinkHealth.objects.filter(status=status).count()

    logger.info(
        "Health scan complete: %d scanned, %d healthy, %d warning, %d broken, %d stale",
        results['scanned'], results['healthy'],
        results['warning'], results['broken'], results['stale'],
    )
    return results


def check_link_health(link):
    """
    Check a single link's health and update its LinkHealth record.
    Performs an HTTP HEAD/GET request and analyzes results.
    """
    health, created = LinkHealth.objects.get_or_create(link=link)

    issues = []
    destination_url = link.destination_url

    # ---- HTTP Check ----
    http_status = None
    redirect_count = 0
    response_time_ms = None
    ssl_valid = True
    final_url = destination_url

    try:
        start_time = time.time()

        # Use a session that follows redirects but caps them
        session = requests.Session()
        session.max_redirects = MAX_REDIRECTS

        response = session.get(
            destination_url,
            timeout=HTTP_CHECK_TIMEOUT,
            allow_redirects=True,
            headers={
                'User-Agent': 'LinkForge-HealthChecker/1.0',
                'Accept': 'text/html,application/xhtml+xml,*/*',
            },
            stream=True,  # Don't download the body
        )

        # Close the connection immediately
        response.close()

        response_time_ms = int((time.time() - start_time) * 1000)
        http_status = response.status_code
        redirect_count = len(response.history)
        final_url = response.url

        # Check SSL
        if response.url.startswith('https://'):
            ssl_valid = True
        elif destination_url.startswith('https://') and not response.url.startswith('https://'):
            ssl_valid = False
            issues.append({
                'type': 'ssl',
                'severity': 'warning',
                'message': 'HTTPS to HTTP downgrade detected',
            })

        # Check HTTP status
        if http_status >= 400:
            issues.append({
                'type': 'http_error',
                'severity': 'critical',
                'message': f'Destination returned HTTP {http_status}',
                'detail': f'The URL responded with status {http_status}',
            })
        elif http_status >= 300:
            issues.append({
                'type': 'redirect_loop',
                'severity': 'warning',
                'message': f'Unexpected redirect to HTTP {http_status}',
            })

        # Check redirect chain
        if redirect_count > MAX_HEALTHY_REDIRECTS:
            issues.append({
                'type': 'excessive_redirects',
                'severity': 'warning',
                'message': f'Redirect chain is {redirect_count} hops long',
                'detail': 'Long redirect chains slow down page load and may lose affiliate tags',
            })

        # Check response time
        if response_time_ms > CRITICAL_RESPONSE_MS:
            issues.append({
                'type': 'slow_response',
                'severity': 'warning',
                'message': f'Response time is {response_time_ms}ms',
                'detail': 'Slow response times can hurt user experience and conversion rates',
            })
        elif response_time_ms > WARNING_RESPONSE_MS:
            issues.append({
                'type': 'slow_response',
                'severity': 'info',
                'message': f'Response time is {response_time_ms}ms',
            })

        # Check if destination changed
        if health.last_destination_snapshot and health.last_destination_snapshot != final_url:
            issues.append({
                'type': 'destination_changed',
                'severity': 'info',
                'message': 'Destination URL has changed since last scan',
                'detail': f'Was: {health.last_destination_snapshot[:80]}...',
            })

    except requests.exceptions.Timeout:
        http_status = 0
        issues.append({
            'type': 'timeout',
            'severity': 'critical',
            'message': 'Destination did not respond within 10 seconds',
            'detail': 'The URL timed out — the page may be down or too slow',
        })
    except requests.exceptions.ConnectionError:
        http_status = 0
        issues.append({
            'type': 'connection_error',
            'severity': 'critical',
            'message': 'Could not connect to destination',
            'detail': 'The domain may be down, blocked, or the URL may be invalid',
        })
    except requests.exceptions.TooManyRedirects:
        http_status = 0
        redirect_count = MAX_REDIRECTS + 1
        issues.append({
            'type': 'too_many_redirects',
            'severity': 'critical',
            'message': f'More than {MAX_REDIRECTS} redirects detected',
            'detail': 'The destination has an excessive redirect chain — possibly a redirect loop',
        })
    except Exception as e:
        http_status = 0
        issues.append({
            'type': 'check_error',
            'severity': 'warning',
            'message': f'Health check failed: {str(e)[:80]}',
        })

    # ---- Stale Detection ----
    days_since_update = (timezone.now() - link.updated_at).days
    if days_since_update >= STALE_DAYS:
        issues.append({
            'type': 'stale',
            'severity': 'warning',
            'message': f'Not reviewed in {days_since_update} days',
            'detail': 'This link has not been updated in over 6 months — the product may have changed',
        })

    # ---- Click Trend Analysis ----
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)

    current_clicks = Click.objects.filter(
        link=link, timestamp__gte=thirty_days_ago
    ).count()

    previous_clicks = Click.objects.filter(
        link=link,
        timestamp__gte=sixty_days_ago,
        timestamp__lt=thirty_days_ago,
    ).count()

    click_trend = 'insufficient'
    if current_clicks > 0 or previous_clicks > 0:
        if previous_clicks == 0 and current_clicks > 0:
            click_trend = 'surging'
        elif current_clicks == 0 and previous_clicks > 0:
            click_trend = 'declining'
            if previous_clicks >= 5:
                issues.append({
                    'type': 'traffic_drop',
                    'severity': 'warning',
                    'message': f'Traffic dropped from {previous_clicks} to 0 clicks',
                    'detail': 'This link stopped getting clicks — the destination may be broken or the product discontinued',
                })
        else:
            change_pct = ((current_clicks - previous_clicks) / previous_clicks) * 100
            if change_pct < -TRAFFIC_DROP_PCT:
                click_trend = 'declining'
                issues.append({
                    'type': 'traffic_drop',
                    'severity': 'warning',
                    'message': f'Traffic down {abs(change_pct):.0f}% compared to previous 30 days',
                    'detail': f'Was {previous_clicks} clicks, now {current_clicks} clicks',
                })
            elif change_pct > 50:
                click_trend = 'surging'
            else:
                click_trend = 'stable'

    # ---- Calculate Health Score ----
    score = 100

    # Deductions for issues
    for issue in issues:
        severity = issue.get('severity', 'info')
        if severity == 'critical':
            score -= 35
        elif severity == 'warning':
            score -= 20
        elif severity == 'info':
            score -= 5

    # Bonus for good behavior
    if http_status and http_status < 300:
        score += 5  # working destination
    if response_time_ms and response_time_ms < 1000:
        score += 5  # fast response
    if days_since_update < 30:
        score += 5  # recently updated
    if click_trend == 'surging':
        score += 5
    if redirect_count == 0:
        score += 3  # direct link

    # Clamp score to 0-100
    score = max(0, min(100, score))

    # ---- Determine Status ----
    has_critical = any(i.get('severity') == 'critical' for i in issues)
    has_warning = any(i.get('severity') == 'warning' for i in issues)
    is_stale = any(i.get('type') == 'stale' for i in issues)

    if has_critical:
        status = 'broken'
    elif is_stale and score < LOW_SCORE_THRESHOLD:
        status = 'stale'
    elif has_warning or score < 70:
        status = 'warning'
    else:
        status = 'healthy'

    # ---- Build suggested fix ----
    suggested_fix = ''
    if status == 'broken':
        suggested_fix = 'Check if the product is still available on the destination site. You may need to find a replacement URL.'
    elif status == 'stale':
        suggested_fix = 'Review this link and update the destination URL if the product or offer has changed.'
    elif status == 'warning':
        critical_issues = [i for i in issues if i['severity'] == 'critical']
        if critical_issues:
            suggested_fix = critical_issues[0]['message']
        elif is_stale:
            suggested_fix = f'Last reviewed {days_since_update} days ago. Check if the campaign is still relevant.'

    # ---- Save Health Record ----
    health.health_score = score
    health.status = status
    health.last_checked = timezone.now()
    health.last_http_status = http_status
    health.redirect_count = redirect_count
    health.response_time_ms = response_time_ms
    health.ssl_valid = ssl_valid
    health.issues_summary = json.dumps(issues)
    health.issues_count = len(issues)
    health.click_trend = click_trend
    health.previous_clicks_30d = previous_clicks
    health.current_clicks_30d = current_clicks
    health.last_destination_snapshot = final_url
    health.suggested_fix = suggested_fix
    health.save()

    return health


def get_health_dashboard_data():
    """
    Aggregate health data for the health center dashboard.
    """
    total = Link.objects.filter(is_active=True).count()
    healthy = LinkHealth.objects.filter(status='healthy').count()
    warning = LinkHealth.objects.filter(status='warning').count()
    broken = LinkHealth.objects.filter(status='broken').count()
    stale = LinkHealth.objects.filter(status='stale').count()
    unscanned = total - LinkHealth.objects.count()

    # Get links needing attention (worst health first)
    needs_attention_qs = Link.objects.filter(
        is_active=True,
        health__status__in=['broken', 'warning', 'stale'],
    ).select_related('health').order_by('health__health_score')[:20]

    # Parse issues_summary JSON for each link
    needs_attention = []
    for link in needs_attention_qs:
        try:
            issues = json.loads(link.health.issues_summary) if link.health.issues_summary else []
        except (json.JSONDecodeError, TypeError):
            issues = []
        link.health.parsed_issues = issues
        needs_attention.append(link)

    # Average health score
    avg_score = LinkHealth.objects.aggregate(avg=Avg('health_score'))
    avg_score = round(avg_score['avg'] or 0)

    return {
        'total_links': total,
        'healthy_count': healthy,
        'warning_count': warning,
        'broken_count': broken,
        'stale_count': stale,
        'unscanned_count': unscanned,
        'needs_attention': needs_attention,
        'avg_health_score': avg_score,
    }


def get_smart_alerts():
    """
    Generate smart alert summaries for the main dashboard.
    Returns a list of alert groups.
    """
    alerts = []

    broken_count = LinkHealth.objects.filter(status='broken').count()
    if broken_count:
        alerts.append({
            'icon': 'iconoir-warning-triangle',
            'color': 'text-[#EF4444]',
            'bg': 'bg-[rgba(239,68,68,0.08)]',
            'border': 'border-[rgba(239,68,68,0.15)]',
            'count': broken_count,
            'label': 'broken links need immediate attention',
            'url': 'links:link_health',
        })

    stale_count = LinkHealth.objects.filter(status='stale').count()
    if stale_count:
        alerts.append({
            'icon': 'iconoir-clock',
            'color': 'text-[#F59E0B]',
            'bg': 'bg-[rgba(245,158,11,0.08)]',
            'border': 'border-[rgba(245,158,11,0.15)]',
            'count': stale_count,
            'label': 'links not reviewed in 6+ months',
            'url': 'links:link_health',
        })

    warning_count = LinkHealth.objects.filter(
        status='warning',
        issues_summary__contains='traffic_drop',
    ).count()
    if warning_count:
        alerts.append({
            'icon': 'iconoir-graph-down',
            'color': 'text-[#F59E0B]',
            'bg': 'bg-[rgba(245,158,11,0.08)]',
            'border': 'border-[rgba(245,158,11,0.15)]',
            'count': warning_count,
            'label': 'links lost significant traffic',
            'url': 'links:link_health',
        })

    return alerts
