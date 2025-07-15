from django.urls import path
from . import views

urlpatterns = [

    path('', views.homepage, name='homepage'),

    # Excursion URLs
    path('excursions/', views.excursion_list, name='excursion_list'),
    path('excursions/add/', views.excursion_create, name='excursion_create'),
    path('excursions/<int:pk>/', views.excursion_detail, name='excursion_detail'),
    path('excursions/<int:pk>/edit/', views.excursion_update, name='excursion_update'),
    path('excursions/<int:pk>/delete/', views.excursion_delete, name='excursion_delete'),
    path('retrive_voucher/', views.retrive_voucher, name='retrive_voucher'),
    path('manage_cookies/', views.manage_cookies, name='manage_cookies'),
    path('sync_pickup_groups/', views.sync_pickup_groups, name='sync_pickup_groups'),
    path('sync_pickup_points/', views.sync_pickup_points, name='sync_pickup_points'),
    path('sync_hotels/', views.sync_hotels, name='sync_hotels'),
    path('sync_excursions/', views.sync_excursions, name='sync_excursions'),
    path('sync_providers/', views.sync_providers, name='sync_providers'),
    path('sync_excursion_availabilities/', views.sync_excursion_availabilities, name='sync_excursion_availabilities'),
    # Booking URLs
    path('availability/<int:availability_pk>/book/', views.booking_create, name='booking_create'),
    path('bookings/<int:pk>/', views.booking_detail, name='booking_detail'),

    # Checkout URL
    path('checkout/<int:booking_pk>/', views.checkout, name='checkout'),

    # User URLs
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup, name='signup'),
    path('profile/<int:pk>/', views.profile, name='profile'),
    path('profile/<int:pk>/edit/', views.profile_edit, name='profile_edit'),
    path('logout/', views.logout_view, name='logout'),

    # Admin Dashboard
    path('profile/admin/<int:pk>/', views.admin_dashboard, name='admin_dashboard'),
    path('profile/admin/excursions/', views.admin_excursions, name='admin_excursions'),
    path('providers_list/', views.providers_list, name='providers_list'),
    path('manage_providers/', views.manage_providers, name='manage_providers'),
    path('reps_list/', views.reps_list, name='reps_list'),
    path('manage_reps/', views.manage_reps, name='manage_reps'),
    path('clients_list/', views.clients_list, name='clients_list'),
    path('manage_clients/', views.manage_clients, name='manage_clients'),
    path('staff_list/', views.staff_list, name='staff_list'),
    path('manage_staff/', views.manage_staff, name='manage_staff'),
    path('guides_list/', views.guides_list, name='guides_list'),
    path('manage_guides/', views.manage_guides, name='manage_guides'),
    # location urls
    path('hotel_list/', views.hotel_list, name='hotel_list'),
    path('manage_hotels/', views.manage_hotels, name='manage_hotels'),
    path('region_list/', views.region_list, name='region_list'),
    path('manage_regions/', views.manage_regions, name='manage_regions'),
    path('pickup_groups_list/', views.pickup_groups_list, name='pickup_groups_list'),
    path('manage_pickup_groups/', views.manage_pickup_groups, name='manage_pickup_groups'),
    path('pickup_points_list/', views.pickup_points_list, name='pickup_points_list'),
    path('manage_pickup_points/', views.manage_pickup_points, name='manage_pickup_points'),

    # Availability URLs
    path('availability/', views.availability_list, name='availability_list'),
    path('availability/add/', views.availability_form, name='availability_create'),
    path('availability/<int:pk>/', views.availability_detail, name='availability_detail'),
    path('availability/<int:pk>/edit/', views.availability_form, name='availability_update'),
    path('availability/<int:pk>/delete/', views.availability_delete, name='availability_delete'),

    # Group URLs
    path('groups/', views.group_list, name='group_list'),
    path('groups/add/', views.group_create, name='group_create'),
    # path('groups/<int:pk>/edit/', views.group_update, name='group_update'),
    path('groups/<int:pk>/delete/', views.group_delete, name='group_delete'),
    
    # Categories and Tags Management
    path('manage-categories-tags/', views.manage_categories_tags, name='manage_categories_tags'),

]

