from django.contrib import admin
from .models import Click


@admin.register(Click)
class ClickAdmin(admin.ModelAdmin):
    list_display = ['link', 'timestamp', 'country', 'browser', 'os', 'device']
    list_filter = ['timestamp', 'country', 'browser', 'os', 'device']
    search_fields = ['link__slug', 'link__campaign_name', 'country', 'referrer']
    readonly_fields = ['link', 'timestamp', 'ip_address', 'country', 'browser', 'os', 'device', 'referrer', 'user_agent']
    ordering = ['-timestamp']
    list_per_page = 50
