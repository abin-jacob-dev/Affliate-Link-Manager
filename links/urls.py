from django.urls import path, re_path
from links import views

app_name = 'links'

urlpatterns = [
    # Landing page
    path('', views.home, name='home'),
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Link CRUD
    path('create/', views.link_create, name='link_create'),
    path('edit/<uuid:pk>/', views.link_edit, name='link_edit'),
    path('delete/<uuid:pk>/', views.link_delete, name='link_delete'),
    
    # Analytics
    path('analytics/<uuid:pk>/', views.link_analytics, name='link_analytics'),
    
    # All Links (table view)
    path('links/', views.links_list, name='links_list'),
    
    # Search
    path('search/', views.search_links, name='search'),
    
    # Link Health
    path('health/', views.link_health, name='link_health'),
    
    # Settings
    path('settings/', views.settings_view, name='settings'),
    
    # Redirect engine - catch all short URL slugs
    # This must be the last pattern to avoid catching other paths
    re_path(r'^(?P<slug>[a-zA-Z0-9]{4,10})/?$', views.redirect_to_destination, name='redirect'),
]
