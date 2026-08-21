from django.db import models
from django.utils import timezone


class LinkHealth(models.Model):
    """
    Stores health status and intelligence data for each link.
    Updated periodically by the health scanning service.
    """
    HEALTH_STATUS_CHOICES = [
        ('healthy', 'Healthy'),
        ('warning', 'Warning'),
        ('broken', 'Broken'),
        ('stale', 'Stale'),
    ]
    CLICK_TREND_CHOICES = [
        ('stable', 'Stable'),
        ('declining', 'Declining'),
        ('surging', 'Surging'),
        ('insufficient', 'Insufficient Data'),
    ]

    link = models.OneToOneField(
        'links.Link',
        on_delete=models.CASCADE,
        related_name='health',
        primary_key=True,
        help_text="The link being monitored",
    )
    health_score = models.PositiveSmallIntegerField(
        default=100,
        help_text="Overall health score (0-100)",
    )
    status = models.CharField(
        max_length=20,
        choices=HEALTH_STATUS_CHOICES,
        default='healthy',
        db_index=True,
        help_text="Current health status",
    )
    last_checked = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the link was last scanned",
    )
    last_http_status = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Last HTTP status code from destination",
    )
    redirect_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of redirects the destination URL goes through",
    )
    response_time_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Response time in milliseconds",
    )
    ssl_valid = models.BooleanField(
        default=True,
        help_text="Whether the destination has a valid SSL certificate",
    )
    issues_summary = models.TextField(
        blank=True,
        default='',
        help_text="JSON-encoded list of issues found",
    )
    issues_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of active issues",
    )
    click_trend = models.CharField(
        max_length=20,
        choices=CLICK_TREND_CHOICES,
        default='insufficient',
        help_text="Click traffic trend",
    )
    previous_clicks_30d = models.IntegerField(
        default=0,
        help_text="Click count 30-60 days ago",
    )
    current_clicks_30d = models.IntegerField(
        default=0,
        help_text="Click count in last 30 days",
    )
    last_destination_snapshot = models.URLField(
        max_length=2048,
        blank=True,
        default='',
        help_text="The destination URL at last check (for detecting changes)",
    )
    suggested_fix = models.TextField(
        blank=True,
        default='',
        help_text="Suggested fix or replacement suggestion",
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the health record was created",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the health record was last updated",
    )

    class Meta:
        verbose_name = "Link Health"
        verbose_name_plural = "Link Health"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['health_score']),
            models.Index(fields=['issues_count']),
        ]

    def __str__(self):
        return f"{self.link.slug}: {self.status} ({self.health_score}/100)"


class Click(models.Model):
    """
    Tracks every click/redirect event for analytics purposes.
    Stores detailed information about the visitor and their request.
    """
    link = models.ForeignKey(
        'links.Link',
        on_delete=models.CASCADE,
        related_name='clicks',
        db_index=True,
        help_text="The shortened link that was clicked",
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the click occurred",
    )
    ip_address = models.GenericIPAddressField(
        blank=True,
        null=True,
        help_text="Visitor's IP address",
    )
    country = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Detected country of the visitor",
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Detected city of the visitor",
    )
    browser = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Visitor's browser name",
    )
    browser_version = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Visitor's browser version",
    )
    os = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Visitor's operating system",
    )
    device = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Device type (desktop, tablet, mobile)",
    )
    referrer = models.URLField(
        max_length=2048,
        blank=True,
        default='',
        help_text="HTTP referrer header",
    )
    user_agent = models.TextField(
        blank=True,
        default='',
        help_text="Raw User-Agent header",
    )
    utm_source = models.CharField(
        max_length=255,
        blank=True,
        default='',
        db_index=True,
        help_text="UTM source parameter",
    )
    utm_medium = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="UTM medium parameter",
    )
    utm_campaign = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="UTM campaign parameter",
    )
    utm_content = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="UTM content parameter",
    )
    utm_term = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="UTM term parameter",
    )

    class Meta:
        verbose_name = "Click"
        verbose_name_plural = "Clicks"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['link', 'timestamp']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['country']),
            models.Index(fields=['referrer']),
            models.Index(fields=['utm_source']),
        ]

    def __str__(self):
        return f"Click on {self.link.slug} at {self.timestamp}"
