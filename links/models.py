import uuid
import logging
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _

from .validators import (
    SlugValidator,
    validate_slug_not_reserved,
    CampaignNameValidator,
    DestinationURLValidator,
    sanitize_text_input,
)

logger = logging.getLogger(__name__)


class Link(models.Model):
    """
    Represents a shortened URL that redirects to a destination URL.
    The slug is permanent and never changes; only the destination_url can be updated.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the link",
    )
    campaign_name = models.CharField(
        max_length=255,
        validators=[CampaignNameValidator()],
        help_text="Human-readable name for the affiliate campaign",
    )
    destination_url = models.URLField(
        max_length=2048,
        validators=[DestinationURLValidator()],
        help_text="The full affiliate URL to redirect to",
    )
    slug = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        validators=[SlugValidator(), validate_slug_not_reserved],
        help_text="Short unique identifier used in the shortened URL",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive links will not redirect",
    )
    qr_code = models.ImageField(
        upload_to='qr_codes/',
        blank=True,
        null=True,
        help_text="QR code image for the short URL",
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="When the link was created",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the link was last updated",
    )

    class Meta:
        verbose_name = _("Link")
        verbose_name_plural = _("Links")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug', 'is_active']),
            models.Index(fields=['created_at']),
            models.Index(fields=['campaign_name']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(campaign_name=''),
                name='links_campaign_name_not_empty',
            ),
            models.CheckConstraint(
                condition=~models.Q(destination_url=''),
                name='links_destination_url_not_empty',
            ),
        ]

    def __str__(self):
        return f"{self.campaign_name} ({self.slug})"

    def get_short_url(self):
        """Return the full short URL for this link."""
        from django.conf import settings
        return f"{settings.SITE_URL}/{self.slug}"

    def clean(self):
        """
        Model-level validation that runs on every save via ModelForm or .full_clean().
        """
        super().clean()

        # Sanitize campaign name
        if self.campaign_name:
            self.campaign_name = sanitize_text_input(self.campaign_name, max_length=255)

        # Normalize slug to lowercase
        if self.slug:
            self.slug = self.slug.lower()

        # Ensure slug is not empty after normalization
        if self.slug and not self.slug.strip():
            raise DjangoValidationError({'slug': _('Slug cannot be empty.')})

        errors = {}

        # Validate campaign_name length
        if self.campaign_name and len(self.campaign_name) < 2:
            errors['campaign_name'] = _('Campaign name must be at least 2 characters.')

        # Validate destination_url against open redirect patterns
        if self.destination_url:
            from urllib.parse import urlparse
            parsed = urlparse(self.destination_url)
            # Prevent open redirect via //evil.com pattern
            if not parsed.scheme:
                errors['destination_url'] = _('URL must include a scheme (http:// or https://).')
            # Prevent hostname confusion
            if parsed.hostname and '@' in parsed.hostname:
                errors['destination_url'] = _('URL contains an invalid hostname format.')

        if errors:
            raise DjangoValidationError(errors)

    def save(self, *args, **kwargs):
        """
        Override save to ensure validation and slug normalization.

        Note: Validation is skipped when:
        - `raw=True` (e.g., loaddata fixtures)
        - `update_fields` is specified (partial updates, caller must validate)
        """
        # Normalize slug BEFORE validation so SlugValidator doesn't reject uppercase
        if self.slug:
            self.slug = self.slug.lower()

        # Run full validation
        if not kwargs.get('raw') and not kwargs.get('update_fields'):
            try:
                self.full_clean(exclude=None)
            except DjangoValidationError as e:
                logger.warning(
                    "Validation failed while saving link: %s",
                    dict(e),
                    extra={'slug': self.slug},
                )
                raise

        super().save(*args, **kwargs)
