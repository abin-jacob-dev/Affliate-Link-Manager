import json
import logging
import re
from urllib.parse import urlencode

from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError as DjangoValidationError

from links.models import Link
from links.utils import (
    generate_unique_slug,
    validate_url,
    sanitize_url,
    validate_link_count,
)
from links.services import generate_qr_code
from links.validators import sanitize_text_input, sanitize_search_query
from analytics.models import Click
from analytics.services import (
    get_dashboard_stats,
    get_click_stats,
    get_chart_data,
    record_click,
)
from analytics.health_services import (
    get_health_dashboard_data,
    get_smart_alerts,
    scan_all_links,
)

logger = logging.getLogger(__name__)

# Maximum field lengths
MAX_CAMPAIGN_NAME_LENGTH = 255
MAX_DESTINATION_URL_LENGTH = 2048


def home(request):
    """Landing page for the application."""
    return render(request, 'links/landing.html')


def redirect_to_destination(request, slug):
    """
    Redirect a short URL slug to its destination URL.

    Looks up the link by slug, records a click for analytics,
    and issues a 302 redirect to the destination URL.
    Always redirects to the latest destination URL.

    Security: Validates the redirect URL to prevent open redirects.
    Uses 302 (temporary) redirect so crawlers don't cache the redirect target.
    """
    # Validate slug format
    if not slug or not re.match(r'^[a-zA-Z0-9]{4,20}$', slug):
        return render(request, 'links/404.html', status=404)

    try:
        link = get_object_or_404(Link, slug__iexact=slug, is_active=True)

        # Validate destination URL is safe before redirecting
        destination = sanitize_url(link.destination_url)
        if not validate_url(destination):
            logger.error(
                "Blocked redirect to invalid URL for slug '%s': %s",
                slug,
                destination[:100],
            )
            return render(request, 'links/500.html', status=500)

        # Record the click for analytics (best-effort, never break redirect)
        try:
            record_click(link, request)
        except Exception as e:
            logger.warning("Failed to record click for slug '%s': %s", slug, str(e))

        return HttpResponseRedirect(destination)

    except Exception as e:
        logger.error("Redirect error for slug '%s': %s", slug, str(e), exc_info=True)
        return render(request, 'links/404.html', status=404)


def dashboard(request):
    """Main dashboard page with overview statistics and charts."""
    try:
        stats = get_dashboard_stats()
        chart_data = get_chart_data(30)
        smart_alerts = get_smart_alerts()

        context = {
            **stats,
            'chart_labels': json.dumps(chart_data['labels']),
            'chart_data': json.dumps(chart_data['data']),
            'smart_alerts': smart_alerts,
            'active_tab': 'dashboard',
        }
        return render(request, 'links/dashboard.html', context)

    except Exception as e:
        logger.error("Dashboard error: %s", str(e), exc_info=True)
        messages.error(request, 'An error occurred while loading the dashboard.')
        return render(request, 'links/dashboard.html', {
            'total_links': 0,
            'active_links': 0,
            'total_clicks': 0,
            'today_clicks': 0,
            'week_clicks': 0,
            'month_clicks': 0,
            'top_links': [],
            'top_referrers': [],
            'top_countries': [],
            'recent_clicks': [],
            'chart_labels': '[]',
            'chart_data': '[]',
            'smart_alerts': [],
            'active_tab': 'dashboard',
        })


def link_create(request):
    """Create a new shortened link with comprehensive validation."""
    if request.method == 'POST':
        # Sanitize inputs upfront (defense-in-depth — model's clean() also sanitizes)
        campaign_name = sanitize_text_input(
            request.POST.get('campaign_name', ''),
            max_length=MAX_CAMPAIGN_NAME_LENGTH,
        )
        destination_url = request.POST.get('destination_url', '').strip()

        errors = []

        # Validate campaign name
        if not campaign_name:
            errors.append('Campaign name is required.')
        elif len(campaign_name) < 2:
            errors.append('Campaign name must be at least 2 characters.')
        elif len(campaign_name) > MAX_CAMPAIGN_NAME_LENGTH:
            errors.append(f'Campaign name must be at most {MAX_CAMPAIGN_NAME_LENGTH} characters.')

        # Validate destination URL
        if not destination_url:
            errors.append('Destination URL is required.')
        elif len(destination_url) > MAX_DESTINATION_URL_LENGTH:
            errors.append(f'URL must be at most {MAX_DESTINATION_URL_LENGTH} characters.')
        else:
            destination_url = sanitize_url(destination_url)
            if not validate_url(destination_url):
                errors.append(
                    'Please enter a valid URL (must start with http:// or https:// '
                    'and point to a public website).'
                )

        # Check link limit
        if not errors and not validate_link_count():
            errors.append(
                'Maximum number of links reached. Please delete some links before creating new ones.'
            )

        if errors:
            return render(request, 'links/link_create.html', {
                'errors': errors,
                'campaign_name': campaign_name,
                'destination_url': destination_url,
                'active_tab': 'create',
            })

        try:
            slug = generate_unique_slug()

            link = Link(
                campaign_name=campaign_name,
                destination_url=destination_url,
                slug=slug,
            )
            # full_clean runs model validators including custom ones
            link.full_clean()
            link.save()

            # Generate QR code (best-effort, non-blocking)
            try:
                generate_qr_code(link)
            except Exception as qr_err:
                logger.warning(
                    "QR generation failed for link '%s': %s",
                    slug, str(qr_err),
                )

            messages.success(
                request,
                f'Link created successfully! Short URL: {link.get_short_url()}',
            )
            logger.info("Link created: slug=%s campaign=%s", slug, campaign_name)
            return redirect('links:dashboard')

        except DjangoValidationError as e:
            # Model-level validation errors
            for field, field_errors in e.message_dict.items():
                for err in field_errors:
                    errors.append(f'{field}: {err}')
            return render(request, 'links/link_create.html', {
                'errors': errors,
                'campaign_name': campaign_name,
                'destination_url': destination_url,
                'active_tab': 'create',
            })

        except Exception as e:
            logger.error("Link creation failed: %s", str(e), exc_info=True)
            return render(request, 'links/link_create.html', {
                'errors': [f'An unexpected error occurred. Please try again. If the problem persists, contact support.'],
                'campaign_name': campaign_name,
                'destination_url': destination_url,
                'active_tab': 'create',
            })

    return render(request, 'links/link_create.html', {
        'active_tab': 'create',
    })


def link_edit(request, pk):
    """Edit an existing link with comprehensive validation."""
    try:
        link = get_object_or_404(Link, pk=pk)
    except Exception as e:
        logger.error("Link edit - invalid PK '%s': %s", pk, str(e))
        return render(request, 'links/404.html', status=404)

    if request.method == 'POST':
        # Sanitize inputs
        campaign_name = sanitize_text_input(
            request.POST.get('campaign_name', ''),
            max_length=MAX_CAMPAIGN_NAME_LENGTH,
        )
        destination_url = request.POST.get('destination_url', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        errors = []

        # Validate campaign name
        if not campaign_name:
            errors.append('Campaign name is required.')
        elif len(campaign_name) < 2:
            errors.append('Campaign name must be at least 2 characters.')
        elif len(campaign_name) > MAX_CAMPAIGN_NAME_LENGTH:
            errors.append(f'Campaign name must be at most {MAX_CAMPAIGN_NAME_LENGTH} characters.')

        # Validate destination URL
        if not destination_url:
            errors.append('Destination URL is required.')
        elif len(destination_url) > MAX_DESTINATION_URL_LENGTH:
            errors.append(f'URL must be at most {MAX_DESTINATION_URL_LENGTH} characters.')
        else:
            destination_url = sanitize_url(destination_url)
            if not validate_url(destination_url):
                errors.append(
                    'Please enter a valid URL (must start with http:// or https:// '
                    'and point to a public website).'
                )

        if errors:
            return render(request, 'links/link_edit.html', {
                'errors': errors,
                'link': link,
                'active_tab': None,
            })

        try:
            link.campaign_name = campaign_name
            link.destination_url = destination_url
            link.is_active = is_active

            # Run model validation
            link.full_clean()
            link.save()

            messages.success(request, 'Link updated successfully!')
            logger.info("Link updated: slug=%s new_url=%s", link.slug, destination_url[:100])
            return redirect('links:dashboard')

        except DjangoValidationError as e:
            for field, field_errors in e.message_dict.items():
                for err in field_errors:
                    errors.append(f'{field}: {err}')
            return render(request, 'links/link_edit.html', {
                'errors': errors,
                'link': link,
                'active_tab': None,
            })

        except Exception as e:
            logger.error("Link update failed for '%s': %s", link.slug, str(e), exc_info=True)
            return render(request, 'links/link_edit.html', {
                'errors': ['An unexpected error occurred while updating the link.'],
                'link': link,
                'active_tab': None,
            })

    return render(request, 'links/link_edit.html', {
        'link': link,
        'active_tab': None,
    })


@require_http_methods(['POST'])
def link_delete(request, pk):
    """Delete a link and its associated data with proper cleanup."""
    try:
        link = get_object_or_404(Link, pk=pk)
        slug = link.slug
        campaign = link.campaign_name

        # Delete associated clicks (will cascade but explicit is clearer)
        deleted_clicks_count = link.clicks.all().delete()[0]

        # Delete QR code file from storage
        if link.qr_code:
            try:
                link.qr_code.delete(save=False)
            except Exception as qr_err:
                logger.warning(
                    "Failed to delete QR code for '%s': %s",
                    slug, str(qr_err),
                )

        link.delete()

        messages.success(request, f'Link "{campaign}" deleted successfully.')
        logger.info(
            "Link deleted: slug=%s campaign=%s clicks_removed=%d",
            slug, campaign, deleted_clicks_count,
        )

    except Exception as e:
        logger.error("Link deletion failed for PK '%s': %s", pk, str(e), exc_info=True)
        messages.error(request, 'An error occurred while deleting the link.')

    return redirect('links:dashboard')


def link_analytics(request, pk):
    """View detailed analytics for a single link."""
    try:
        link = get_object_or_404(Link, pk=pk)
    except Exception as e:
        logger.error("Analytics - invalid PK '%s': %s", pk, str(e))
        return render(request, 'links/404.html', status=404)

    try:
        stats = get_click_stats(link)
        chart_data = get_chart_data(30)

        # Get recent clicks with efficient query
        recent_clicks = link.clicks.order_by('-timestamp')[:50]

        # Get top referrers
        top_referrers = link.clicks.exclude(
            referrer=''
        ).values('referrer').annotate(
            count=Count('id')
        ).order_by('-count')[:5]

        # Get top countries
        top_countries = link.clicks.exclude(
            country=''
        ).values('country').annotate(
            count=Count('id')
        ).order_by('-count')[:5]

        # Get browser breakdown
        browser_stats = link.clicks.exclude(
            browser=''
        ).values('browser').annotate(
            count=Count('id')
        ).order_by('-count')

        # Get OS breakdown
        os_stats = link.clicks.exclude(
            os=''
        ).values('os').annotate(
            count=Count('id')
        ).order_by('-count')

        # Get device breakdown
        device_stats = link.clicks.exclude(
            device=''
        ).values('device').annotate(
            count=Count('id')
        ).order_by('-count')

        context = {
            'link': link,
            **stats,
            'chart_labels': json.dumps(chart_data['labels']),
            'chart_data': json.dumps(chart_data['data']),
            'recent_clicks': recent_clicks,
            'top_referrers': top_referrers,
            'top_countries': top_countries,
            'browser_stats': json.dumps(list(browser_stats)),
            'os_stats': json.dumps(list(os_stats)),
            'device_stats': json.dumps(list(device_stats)),
            'active_tab': None,
        }
        return render(request, 'links/link_analytics.html', context)

    except Exception as e:
        logger.error(
            "Analytics error for link '%s': %s",
            getattr(link, 'slug', 'unknown'),
            str(e),
            exc_info=True,
        )
        messages.error(request, 'An error occurred while loading analytics.')
        return redirect('links:dashboard')


def search_links(request):
    """
    Search links by campaign name, slug, or destination URL.
    Redirects to the links list page with the search query.
    Input is sanitized to prevent XSS and injection attacks.
    """
    raw_query = request.GET.get('q', '').strip()

    if not raw_query:
        return redirect('links:links_list')

    # Sanitize search query
    query = sanitize_search_query(raw_query)

    if not query:
        messages.warning(request, 'Please enter a valid search term.')
        return redirect('links:links_list')

    # Redirect to the links list page with search query
    return redirect(f"{reverse('links:links_list')}?q={query}")


def links_list(request):
    """View all links with filtering, sorting, search, and pagination."""
    try:
        # --- Filtering ---
        status_filter = request.GET.get('status', 'all')
        search_query = sanitize_search_query(request.GET.get('q', '').strip())

        links_qs = Link.objects.annotate(click_count=Count('clicks'))

        # Status filter
        if status_filter == 'active':
            links_qs = links_qs.filter(is_active=True)
        elif status_filter == 'inactive':
            links_qs = links_qs.filter(is_active=False)

        # Search filter
        if search_query:
            links_qs = links_qs.filter(
                Q(campaign_name__icontains=search_query) |
                Q(slug__icontains=search_query) |
                Q(destination_url__icontains=search_query)
            )

        # --- Sorting ---
        allowed_sort_fields = {
            'name': 'campaign_name',
            'slug': 'slug',
            'clicks': 'click_count',
            'created': 'created_at',
            'updated': 'updated_at',
        }
        sort_by = request.GET.get('sort', 'created')
        sort_field = allowed_sort_fields.get(sort_by, 'created_at')

        order = request.GET.get('order', 'desc')
        if order == 'asc':
            sort_field = sort_field
        else:
            sort_field = f'-{sort_field}'

        links_qs = links_qs.order_by(sort_field)

        # --- Pagination ---
        try:
            page_size = int(request.GET.get('per_page', 15))
            if page_size not in (10, 15, 25, 50):
                page_size = 15
        except (ValueError, TypeError):
            page_size = 15

        try:
            page_number = int(request.GET.get('page', 1))
            if page_number < 1:
                page_number = 1
        except (ValueError, TypeError):
            page_number = 1

        paginator = Paginator(links_qs, page_size)
        page_obj = paginator.get_page(page_number)

        # Preserve query params for pagination links
        query_params = {
            'status': status_filter if status_filter != 'all' else '',
            'sort': sort_by,
            'order': order,
            'q': search_query,
            'per_page': page_size,
        }
        # Remove empty values
        query_params = {k: v for k, v in query_params.items() if v}

        context = {
            'page_obj': page_obj,
            'links': page_obj,
            'active_tab': 'links',
            'current_sort': sort_by,
            'current_order': order,
            'current_status': status_filter,
            'search_query': search_query,
            'current_per_page': page_size,
            'query_params': urlencode(query_params),
        }
        return render(request, 'links/links_list.html', context)

    except Exception as e:
        logger.error("Links list error: %s", str(e), exc_info=True)
        messages.error(request, 'An error occurred while loading the links.')
        return render(request, 'links/links_list.html', {
            'page_obj': None,
            'links': [],
            'active_tab': 'links',
            'current_sort': 'created',
            'current_order': 'desc',
            'current_status': 'all',
            'search_query': '',
            'current_per_page': 15,
            'query_params': '',
        })


def link_health(request):
    """Link Health Center dashboard with health scores, issues, and smart alerts."""
    # Run scan if requested
    if request.GET.get('scan') == '1':
        scan_all_links()
        messages.success(request, 'Link health scan completed.')
        return redirect('links:link_health')

    try:
        health_data = get_health_dashboard_data()
        context = {
            **health_data,
            'active_tab': 'health',
        }
        return render(request, 'links/link_health.html', context)
    except Exception as e:
        logger.error("Health dashboard error: %s", str(e), exc_info=True)
        messages.error(request, 'An error occurred while loading the health dashboard.')
        return render(request, 'links/link_health.html', {
            'total_links': 0,
            'healthy_count': 0,
            'warning_count': 0,
            'broken_count': 0,
            'stale_count': 0,
            'unscanned_count': 0,
            'needs_attention': [],
            'avg_health_score': 0,
            'active_tab': 'health',
        })


def settings_view(request):
    """Application settings page."""
    return render(request, 'links/settings.html', {
        'active_tab': 'settings',
    })


def custom_404(request, exception):
    """Custom 404 error page with logging."""
    logger.info(
        "404 Not Found: %s (referrer: %s)",
        request.path,
        request.META.get('HTTP_REFERER', 'None'),
    )
    return render(request, 'links/404.html', status=404)


def custom_500(request):
    """Custom 500 error page with logging."""
    logger.error(
        "500 Server Error: %s (user: %s)",
        request.path,
        request.META.get('REMOTE_ADDR', 'unknown'),
    )
    return render(request, 'links/500.html', status=500)
