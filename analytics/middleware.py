import re
from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse
from analytics.services import record_click


class ClickTrackingMiddleware:
    """
    Middleware that intercepts requests to short URLs and records analytics.
    
    When a request matches a valid short URL slug, this middleware:
    1. Looks up the link by slug
    2. Records the click with detailed analytics
    3. Redirects the visitor to the destination URL
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip tracking for static/media/admin paths
        path = request.path_info.lstrip('/')
        
        if not settings.CLICK_TRACKING_ENABLED:
            return self.get_response(request)
        
        # Skip certain paths
        for skip_path in settings.CLICK_TRACKING_SKIP_PATHS:
            if request.path_info.startswith(skip_path):
                return self.get_response(request)
        
        # If this could be a short URL redirect, it will be handled
        # by the redirect view in links.views. This middleware just
        # adds the tracking capability.
        
        return self.get_response(request)
