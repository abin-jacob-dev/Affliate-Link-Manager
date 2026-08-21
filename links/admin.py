from django.contrib import admin
from .models import Link


@admin.register(Link)
class LinkAdmin(admin.ModelAdmin):
    list_display = ['campaign_name', 'slug', 'destination_url', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['campaign_name', 'slug', 'destination_url']
    readonly_fields = ['slug', 'created_at', 'updated_at', 'qr_code']
    ordering = ['-created_at']
    list_per_page = 25
