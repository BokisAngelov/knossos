from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from datetime import date, datetime, time, timedelta
from django.contrib.auth.models import User
from django.http import JsonResponse, Http404, HttpResponse
from django.utils.text import slugify
from .models import (
    Excursion, ExcursionImage, ExcursionAvailability,
    Booking, Feedback, UserProfile, Region, 
        Group, Category, Tag, PickupPoint, AvailabilityDays, DayOfWeek, Hotel, PickupGroup, PickupGroupAvailability, Reservation, Bus
    )
from .forms import (
    ExcursionForm, ExcursionImageFormSet,
    ExcursionAvailabilityForm, BookingForm, FeedbackForm, UserProfileForm,
    GroupForm, SignupForm
)
from django.core.validators import validate_email, RegexValidator
from django.core.exceptions import ValidationError
import re
import json
import logging
from django.db.models import Q, Sum, Count

logger = logging.getLogger(__name__)
from django.apps import apps
from .cyber_api import get_groups, get_hotels, get_pickup_points, get_excursions, get_excursion_description, get_providers, get_excursion_availabilities, get_reservation
from .utils import FeedbackService, BookingService, ExcursionService, VoucherService, create_reservation, ExcursionAnalyticsService, RevenueAnalyticsService, JCCPaymentService, EmailService, EmailBuilder

def is_staff(user):
    return user.is_staff

def testmodels(request):
    bookings = Booking.objects.all()
    reservations = Reservation.objects.all()
    availabilities = ExcursionAvailability.objects.all()
    availability_days = AvailabilityDays.objects.all()
    # bookings.delete()
    return render(request, 'main/admin/testmodels.html', {
        'bookings': bookings,
        'reservations': reservations,
        'availabilities': availabilities,
        'availability_days': availability_days,
    })

@ensure_csrf_cookie
def homepage(request):
    excursions = Excursion.objects.all().filter(availabilities__isnull=False).filter(status='active').distinct()
    return render(request, 'main/home.html', {
        'excursions': excursions,
    })

def manage_cookies(request, cookie_name, cookie_value, cookie_action):

    if cookie_action == 'set':
        response = JsonResponse({
            'success': True,
            'message': 'Cookie set successfully'
        })
        response.set_cookie(
            cookie_name, 
            cookie_value, 
            max_age=604800, # 7 days
            secure=False,  # Set to True only if using HTTPS exclusively
            httponly=False,
            samesite='Lax'
        )
        return response
    elif cookie_action == 'get':
        return request.COOKIES.get(cookie_name)
    elif cookie_action == 'delete':
        response = JsonResponse({
            'success': True,
            'message': 'Cookie deleted successfully'
        })
        response.delete_cookie(cookie_name)
        return response
    return None
    
def retrive_voucher(request):
    """
    Authenticate and retrieve voucher/reservation.
    Auto-login the user and redirect to their profile.
    """
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': 'Invalid request method.'
        })
    
    try:
        data = json.loads(request.body)
        action = data.get('action')
        
        # Handle clear action
        if action == 'clear':
            # Logout user if authenticated
            if request.user.is_authenticated:
                logout(request)
            return VoucherService.clear_voucher_cookies()
        
        # Get and validate voucher code
        voucher_code = data.get('voucher_code')
        
        if not voucher_code:
            return JsonResponse({
                'success': False,
                'message': 'Voucher code is required.'
            })
        
        logger.info(f"Processing voucher: {voucher_code}")
        
        # Authenticate voucher using VoucherService
        try:
            reservation, created = VoucherService.authenticate_voucher(voucher_code)
            logger.info(f"Voucher authenticated. Created: {created}, Has profile: {hasattr(reservation, 'client_profile')}")
        except Exception as e:
            logger.error(f"Error authenticating voucher: {str(e)}\n{traceback.format_exc()}")
            raise
        
        # Get voucher data
        try:
            voucher_data = VoucherService.get_voucher_data(reservation)
        except Exception as e:
            logger.error(f"Error getting voucher data: {str(e)}\n{traceback.format_exc()}")
            raise
        
        # Check if client_profile exists (might not if migrations haven't been run)
        client_profile = getattr(reservation, 'client_profile', None)
        
        if client_profile and client_profile.user:
            user = client_profile.user
            
            # Login user without password (voucher-based auth)
            user.backend = 'django.contrib.auth.backends.ModelBackend'
            login(request, user)
            
            logger.info(f"User {user.username} logged in successfully")
            
            # Get profile URL using User ID
            profile_url = reverse('profile', kwargs={'pk': user.id})
            
            # Create response with cookies and redirect URL
            response = JsonResponse({
                'success': True,
                'message': f'Welcome, {reservation.client_name}! Redirecting to your profile...',
                'return_data': voucher_data,
                'redirect_url': profile_url,
                'is_new': created
            })
        else:
            # Profile not created - might need migrations
            logger.warning(f"No client profile for reservation {voucher_code}. Migrations may not be applied.")
            
            # Return success but without auto-login
            response = JsonResponse({
                'success': True,
                'message': 'Voucher is valid.',
                'return_data': voucher_data,
                'redirect_url': None,
                'is_new': created,
                'warning': 'Profile creation pending. Please run migrations.'
            })
        
        # Set cookies for voucher data
        response.set_cookie(
            'voucher_code',
            voucher_code,
            max_age=86400,
            secure=False,  # Set to True only if using HTTPS exclusively
            httponly=False,
            samesite='Lax'
        )
        
        if reservation.pickup_group:
            response.set_cookie(
                'pickup_group',
                reservation.pickup_group.id,
                max_age=86400,
                secure=False,  # Set to True only if using HTTPS exclusively
                httponly=False,
                samesite='Lax'
            )
        
        if reservation.pickup_point:
            response.set_cookie(
                'pickup_point',
                reservation.pickup_point.id,
                max_age=86400,
                secure=False,  # Set to True only if using HTTPS exclusively
                httponly=False,
                samesite='Lax'
            )
        
        return response
        
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })
    except Exception as e:
        logger.error(f"Error in retrive_voucher: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })

def check_voucher(request):
    """
    Check voucher validity and return reservation data without logging in.
    Used for pre-filling booking forms.
    """
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'message': 'Invalid request method.'
        })
    
    try:
        data = json.loads(request.body)
        voucher_code = data.get('voucher_code')
        
        if not voucher_code:
            return JsonResponse({
                'success': False,
                'message': 'Voucher code is required.'
            })
        
        logger.info(f"Checking voucher: {voucher_code}")
        
        # Get reservation from database or API
        try:
            reservation, created = VoucherService.authenticate_voucher(voucher_code)
            logger.info(f"Voucher found. Created: {created}")
        except ValidationError as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
        except Exception as e:
            logger.error(f"Error checking voucher: {str(e)}\n{traceback.format_exc()}")
            return JsonResponse({
                'success': False,
                'message': 'Invalid or expired voucher.'
            })
        
        # Get voucher data
        try:
            voucher_data = VoucherService.get_voucher_data(reservation)
        except Exception as e:
            logger.error(f"Error getting voucher data: {str(e)}\n{traceback.format_exc()}")
            return JsonResponse({
                'success': False,
                'message': 'Error retrieving voucher data.'
            })
        
        return JsonResponse({
            'success': True,
            'message': 'Voucher is valid.',
            'return_data': voucher_data
        })
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'message': 'An error occurred while checking the voucher.'
        })
   
def booking_id_page(request):
    """
    Display booking ID entry page for guest users.
    Reuses the existing retrive_voucher endpoint for authentication.
    """
    from .forms import BookingIdForm
    # Redirect authenticated users away from this page
    if request.user.is_authenticated:
        messages.info(request, 'You are already logged in.')
        return redirect('profile', pk=request.user.id)
    
    form = BookingIdForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'main/accounts/booking_id.html', context)
    
#  Sync with Cyberlogic API
def sync_pickup_groups(request):
    if request.method == 'POST':
        try:
            # PickupGroup.objects.all().delete()
            pickup_groups_cl = get_groups()
            total_synced = 0
            for group in pickup_groups_cl:
                pick_name = group['Name']
                pick_id = group['Id']
                pick_code = group['Code']
                pickup_group, created = PickupGroup.objects.get_or_create(
                    id=pick_id,
                    defaults={'name': pick_name, 'code': pick_code}
                )
                if created:
                    print('created pickup group: ' + str(pickup_group))
                    total_synced += 1

                if total_synced > 0:
                    message = 'Sync successful! Total pickup groups synced: ' + str(total_synced)
                else:
                    message = 'Pickup groups are up to date.'
            return JsonResponse({'success': True, 'message': message})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error syncing pickup groups: {str(e)}'})
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

def sync_pickup_points(request):
    if request.method == 'POST':
        try:
            total_synced = 0
            pickup_points_cl = get_pickup_points()
            for point in pickup_points_cl:
                pick_name = point['Name']
                pick_id = point['Id']
                pick_group_id = point['GroupId']
                pickup_point, created = PickupPoint.objects.get_or_create(
                    id=pick_id,
                    defaults={'name': pick_name, 'pickup_group_id': pick_group_id}
                )
                if created:
                    print('created pickup point: ' + str(pickup_point))
                    total_synced += 1

                if total_synced > 0:
                    message = 'Sync successful! Total pickup points synced: ' + str(total_synced)
                else:
                    message = 'Pickup points are up to date.'
            return JsonResponse({'success': True, 'message': message})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error syncing pickup points: {str(e)}'})
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

def sync_hotels(request):
    if request.method == 'POST':
        try:
            hotels_cl = get_hotels()
            total_synced = 0
            for hotel in hotels_cl:
                hotel_name = hotel['Acc_name']
                hotel_id = hotel['Acc_id']
                hotel_address = hotel['Acc_address']
                hotel_zipcode = hotel['acc_zip_code']
                hotel_entry, created = Hotel.objects.get_or_create(
                    id=hotel_id,
                    defaults={'name': hotel_name, 'address': hotel_address, 'zipcode': hotel_zipcode}
                )
                if created:
                    print('created hotel: ' + str(hotel_entry))
                    total_synced += 1

                if total_synced > 0:
                    message = 'Sync successful! Total hotels synced: ' + str(total_synced)
                else:
                    message = 'Hotels are up to date.'
            return JsonResponse({'success': True, 'message': message})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error syncing hotels: {str(e)}'})
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

def sync_excursions(request):
    if request.method == 'POST':
        try:
            excursions_cl = get_excursions()
            total_synced = 0
            for excursion in excursions_cl['Data']:
                
                excursion_name = excursion['Name']
                excursion_id = excursion['Id']
                excursion_provider = excursion['Organizer_Name']
                # print('excursion_name: ' + str(excursion_name))
                # Get the first matching provider (in case there are duplicates)
                provider_profile = UserProfile.objects.filter(name=excursion_provider, role='provider').first()
                if not provider_profile:
                    print(f"Warning: No provider found with name '{excursion_provider}' and role 'provider'")
                    continue
                excursion_provider_id = provider_profile.id
                excursion_description_response = get_excursion_description(excursion_id)
                excursion_description = excursion_description_response['Overview'][0]['Description']['MainDescription']
                excursion_intro_image = excursion_description_response['Media']['DefaultImage']['MainUrl']
                # print('excursion_provider_id: ' + str(excursion_provider_id))
                # print('excursion description: ' + str(excursion_description))
                print('excursion intro image: ' + str(excursion_intro_image))
                                
                excursion_entry, created = Excursion.objects.get_or_create(
                    id=excursion_id,
                    defaults={'title': excursion_name, 'description': excursion_description, 'provider_id': excursion_provider_id, 'intro_image': excursion_intro_image}
                )
                if created:
                    print('created excursion: ' + str(excursion_entry))
                    total_synced += 1

                if total_synced > 0:
                    message = 'Sync successful! Total excursions synced: ' + str(total_synced)
                else:
                    message = 'Excursions are up to date.'
            return JsonResponse({'success': True, 'message': message})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error syncing excursions: {str(e)}'})
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

def sync_providers(request):
    if request.method == 'POST':
        try:
            providers_cl = get_providers()
            total_synced = 0
            for provider in providers_cl:
                provider_name = provider['Name']
                provider_id = provider['Id']
                provider_email = provider['Email']
                provider_phone = provider['Telephone1']
                provider_address = provider['Address']
                provider_zipcode = provider['Zip']

                # 1. Get or create the User instance
                # First try to get existing user by ID, then by username
                try:
                    user = User.objects.get(id=provider_id)
                    user_created = False
                except User.DoesNotExist:
                    try:
                        # Check if user with this username already exists
                        username = provider_email or f"provider_{provider_id}"
                        user = User.objects.get(username=username)
                        user_created = False
                    except User.DoesNotExist:
                        # Create new user
                        user = User.objects.create(
                            id=provider_id,
                            username=provider_email or f"provider_{provider_id}",
                            first_name=provider_name,
                            email=provider_email or "",
                        )
                        user_created = True

                # 2. Get or create the UserProfile instance
                profile, profile_created = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        # 'id': provider_id,
                        'name': provider_name,
                        'role': 'provider',
                        'email': provider_email,
                        'phone': provider_phone,
                        'address': provider_address,
                        'zipcode': provider_zipcode
                    }
                )
                if profile_created:
                    print('created provider: ' + str(profile))
                    total_synced += 1

                if total_synced > 0:
                    message = 'Sync successful! Total providers synced: ' + str(total_synced)
                else:
                    message = 'Providers are up to date.'
            return JsonResponse({'success': True, 'message': message})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error syncing providers: {str(e)}'})
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

# ----- Excursion Views -----
@ensure_csrf_cookie
def excursion_list(request):

    from django.db.models import Q

    excursions = Excursion.objects.filter(status='active')

    categories = Category.objects.all()
    tags = Tag.objects.all()

    search_query = request.GET.get('search', '')
    category_query = request.GET.get('category', '')
    tag_query = request.GET.get('tag', '')
    date_from_query = request.GET.get('date_from', '')
    date_to_query = request.GET.get('date_to', '')

    # Build availability filter
    availability_filter = Q(availabilities__isnull=False, availabilities__is_active=True)
    
    # Date range filtering: check if availability overlaps with search range
    if date_from_query and date_to_query:
        # Both dates provided - availability must overlap the entire range
        availability_filter &= Q(
            availabilities__start_date__lte=date_to_query,
            availabilities__end_date__gte=date_from_query
        )
    elif date_from_query:
        # Only start date - availability must end on or after this date
        availability_filter &= Q(availabilities__end_date__gte=date_from_query)
    elif date_to_query:
        # Only end date - availability must start on or before this date
        availability_filter &= Q(availabilities__start_date__lte=date_to_query)
    
    excursions = excursions.filter(availability_filter)

    if search_query:
        excursions = excursions.filter(Q(title__icontains=search_query) | Q(description__icontains=search_query))
    if category_query:
        excursions = excursions.filter(category__id=category_query)
    if tag_query:
        excursions = excursions.filter(tags__id=tag_query)
    
    # Apply distinct at the end to remove duplicates from availability joins
    excursions = excursions.distinct()

    print('excursions: ' + str(excursions))

    excursions_with_availability = {}

    # for excursion in excursions:
        # excursion = 
    
    # If this is an HTMX request, return only the partial content
    if request.headers.get("HX-Request"):
        return render(request, "main/excursions/partials/_excursion_list_content.html", {
            'excursions': excursions,
        })

    return render(request, 'main/excursions/excursion_list.html', {
        'excursions': excursions,
        'categories': categories,
        'tags': tags,
        'search_query': search_query,
        'category_query': category_query,
        'tag_query': tag_query,
        'date_from_query': date_from_query,
        'date_to_query': date_to_query,
    })

def excursion_detail(request, pk):
    """View for displaying excursion details and handling feedback/booking submissions."""
    excursion = get_object_or_404(Excursion, pk=pk)
    feedbacks = excursion.feedback_entries.all()
    feedback_form, booking_form = None, None
    excursion_availabilities = ExcursionAvailability.objects.filter(excursion=excursion)
    excursion_availability = excursion_availabilities.first()
    
    # Check if user has already submitted feedback for this excursion
    user_has_feedback = FeedbackService.user_has_feedback(request.user, excursion)

    # Handle case when no availability exists
    if not excursion_availability:
        return _render_excursion_without_availability(
            request, excursion, feedbacks, user_has_feedback
        )

    # Process availability data organized by region
    availability_dates_by_region, pickup_points_by_region, region_availability_map = ExcursionService.get_availability_data(
        excursion_availabilities
    )
    region_map = ExcursionService.get_region_map(availability_dates_by_region)
    
    # Get only regions that are in the availabilities (not all regions)
    regions = Region.objects.filter(id__in=availability_dates_by_region.keys())
    
    # Get user's default pickup point (from voucher/reservation or bookings)
    user_pickup_point_id, user_region_id = _get_user_default_pickup_point(
        request, excursion_availabilities, pickup_points_by_region
    )


    # Handle feedback submission
    if request.method == 'POST' and 'feedback_submit' in request.POST:
        return _handle_feedback_submission(request, excursion, user_has_feedback, pk)
        
    # Handle booking submission
    elif request.method == 'POST' and 'booking_submit' in request.POST:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return _handle_ajax_booking_submission(request, excursion_availability)
        

    # Calculate remaining seats and prepare context
    remaining_seats = excursion_availability.max_guests - excursion_availability.booked_guests if excursion_availability else 0
    feedback_form = _get_feedback_form(request.user, user_has_feedback, excursion)
    booking_form = BookingForm(user=request.user)

    return render(request, 'main/excursions/excursion_detail.html', {
        'excursion': excursion,
        'feedbacks': feedbacks,
        'feedback_form': feedback_form,
        'excursion_availabilities': excursion_availabilities,
        'excursion_availability': excursion_availability,
        'booking_form': booking_form,
        'availability_dates_by_region': availability_dates_by_region,
        'pickup_points_by_region': pickup_points_by_region,
        'region_availability_map': region_availability_map,
        'user_has_feedback': user_has_feedback,
        'region_map': region_map,
        'remaining_seats': remaining_seats,
        'regions': regions,
        'user_pickup_point_id': user_pickup_point_id,
        'user_region_id': user_region_id,
    })


def _render_excursion_without_availability(request, excursion, feedbacks, user_has_feedback):
    """Render excursion detail page when no availability exists."""
    feedback_form = _get_feedback_form(request.user, user_has_feedback, excursion)
    booking_form = BookingForm(user=request.user)

    return render(request, 'main/excursions/excursion_detail.html', {
        'excursion': excursion,
        'feedbacks': feedbacks,
        'feedback_form': feedback_form,
        'booking_form': booking_form,
        'excursion_availability': None,
        'availability_dates_by_region': {},
        'pickup_points_by_region': {},
        'region_availability_map': {},
        'user_has_feedback': user_has_feedback,
        'remaining_seats': 0,
        'regions': [],
        'region_map': {},
    })


def _get_feedback_form(user, user_has_feedback, excursion):
    """Get feedback form if user is authenticated and hasn't submitted feedback."""
    if user.is_authenticated and not user_has_feedback:
        return FeedbackForm(author=user, excursion=excursion)
    return None


def _get_user_default_pickup_point(request, excursion_availabilities, pickup_points_by_region):
    """
    Get user's default pickup point from voucher/reservation or recent bookings.
    Check if it's available in the current excursion's availabilities.
    
    Args:
        request: HTTP request object
        excursion_availabilities: QuerySet of ExcursionAvailability objects
        pickup_points_by_region: Dict mapping region IDs to pickup points
    
    Returns:
        tuple: (pickup_point_id, region_id) or (None, None) if not found
    """
    user_pickup_point_id = None
    
    # Try to get pickup point from cookies (set by voucher)
    pickup_point_cookie = request.COOKIES.get('pickup_point')
    if pickup_point_cookie:
        try:
            user_pickup_point_id = int(pickup_point_cookie)
        except (ValueError, TypeError):
            pass
    
    # If not in cookies, try to get from user's most recent reservation
    if not user_pickup_point_id and request.user.is_authenticated:
        try:
            user_profile = UserProfile.objects.get(user=request.user)
            # Get most recent reservation with a pickup point
            latest_reservation = Reservation.objects.filter(
                client_profile=user_profile,
                pickup_point__isnull=False
            ).order_by('-created_at').first()
            
            if latest_reservation and latest_reservation.pickup_point:
                user_pickup_point_id = latest_reservation.pickup_point.id
        except UserProfile.DoesNotExist:
            pass
    
    # If still not found, try to get from user's most recent booking
    if not user_pickup_point_id and request.user.is_authenticated:
        latest_booking = Booking.objects.filter(
            user=request.user,
            pickup_point__isnull=False
        ).order_by('-created_at').first()
        
        if latest_booking and latest_booking.pickup_point:
            user_pickup_point_id = latest_booking.pickup_point.id
    
    # If we have a pickup point, check if it's available in this excursion
    if user_pickup_point_id:
        try:
            pickup_point = PickupPoint.objects.get(id=user_pickup_point_id)
            
            # Check if this pickup point is in any of the excursion's availabilities
            for availability in excursion_availabilities:
                if pickup_point in availability.pickup_points.all():
                    # Find which region contains this pickup point for this excursion
                    for region_id, points in pickup_points_by_region.items():
                        if any(p['id'] == user_pickup_point_id for p in points):
                            return user_pickup_point_id, region_id
        except PickupPoint.DoesNotExist:
            pass
    
    return None, None


def _handle_feedback_submission(request, excursion, user_has_feedback, pk):
    """Handle feedback form submission."""
    if user_has_feedback or not request.user.is_authenticated:
        messages.error(request, 'You have already submitted feedback for this excursion.')
        return redirect('excursion_detail', pk)
    
    feedback_form = FeedbackForm(request.POST, author=request.user, excursion=excursion)
    if feedback_form.is_valid():
        try:
            FeedbackService.create_feedback(
                user=request.user,
                excursion=excursion,
                rating=feedback_form.cleaned_data['rating'],
                comment=feedback_form.cleaned_data['comment']
            )
            messages.success(request, 'Thank you for your feedback.')
        except ValidationError as e:
            messages.error(request, str(e))
    else:
        # Form has errors, will be displayed in template
        pass
    
    return redirect('excursion_detail', pk)


def _handle_ajax_booking_submission(request, excursion_availability):
    """Handle AJAX booking form submission."""
    try:
        booking_form = BookingForm(request.POST, user=request.user)
        
        if not booking_form.is_valid():
            return JsonResponse({
                'success': False,
                'errors': booking_form.errors
            })
        
        # Validate booking data
        booking_data = BookingService.validate_booking_data(request.POST)
        
        # Handle voucher
        voucher_id = request.POST.get('voucher_code')
        voucher_instance = BookingService.handle_voucher(voucher_id)
        
        # Get guest data
        guest_data = {
            'guest_email': request.POST.get('guest_email'),
            'guest_name': request.POST.get('guest_name'),
        }
        
        # Get partial payment method for staff/representatives
        partial_paid_method = ''
        if (request.user and request.user.is_authenticated and 
            (request.user.is_staff or 
             (hasattr(request.user, 'profile') and 
              getattr(request.user.profile, 'role', None) == 'representative'))):
            partial_paid_method = request.POST.get('partial_paid_method', '')
        
        # Get selected date and availability
        selected_date = request.POST.get('selected_date')
        availability_id = request.POST.get('availability_id')
        
        if not selected_date or not availability_id:
            return JsonResponse({
                'success': False,
                'message': 'Please select a date.'
            })
        
        # Get pickup point
        pickup_point_id = request.POST.get('pickup_point')
        pickup_point = None
        if pickup_point_id:
            try:
                pickup_point = PickupPoint.objects.get(id=pickup_point_id)
            except PickupPoint.DoesNotExist:
                pass
        
        # Get region
        region_id = request.POST.get('regions')
        region = None
        if region_id:
            try:
                region = Region.objects.get(id=region_id)
            except Region.DoesNotExist:
                pass
        
        # Create booking (referral code will be applied at checkout)
        booking = BookingService.create_booking(
            user=request.user,
            excursion_availability=excursion_availability,
            booking_data=booking_data,
            guest_data=guest_data,
            voucher_instance=voucher_instance,
            selected_date=selected_date,
            availability_id=availability_id,
            pickup_point=pickup_point
        )
        
        # Set region and partial payment method
        booking.regions = region
        booking.partial_paid_method = partial_paid_method
        booking.save()
        
        # Include token in redirect URL for non-logged-in users
        redirect_url = reverse('checkout', kwargs={'booking_pk': booking.pk})
        if not request.user.is_authenticated and booking.access_token:
            redirect_url += f'?token={booking.access_token}'
        
        return JsonResponse({
            'success': True,
            'redirect_url': redirect_url
        })

    except ValidationError as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e),
            'errors': getattr(booking_form, 'errors', {}) if 'booking_form' in locals() else {}
        })

def validate_referral_code(request):
    """AJAX endpoint to validate referral code and return discount info"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            code = data.get('code', '').strip().upper()
            
            if not code:
                return JsonResponse({
                    'success': False,
                    'message': 'Please enter a referral code.'
                })
            
            from .models import ReferralCode
            from django.utils import timezone
            
            try:
                referral_code = ReferralCode.objects.get(code=code)
                
                # Check if code is active
                if referral_code.status != 'active':
                    return JsonResponse({
                        'success': False,
                        'message': 'This referral code is inactive.'
                    })
                
                # Check if code is expired
                if referral_code.is_expired:
                    # Auto-update status to inactive
                    referral_code.status = 'inactive'
                    referral_code.save()
                    return JsonResponse({
                        'success': False,
                        'message': 'This referral code has expired.'
                    })
                
                # Code is valid!
                return JsonResponse({
                    'success': True,
                    'message': 'Referral code applied successfully!',
                    'discount_percentage': float(referral_code.discount),
                    'code_id': referral_code.id,
                    'code': referral_code.code,
                    'agent_name': referral_code.agent.name if referral_code.agent else 'N/A'
                })
                
            except ReferralCode.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid referral code.'
                })
                
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid request format.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error validating code: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'message': 'Invalid request method.'
    })

def get_user_details_cookies(request):
    
    # user_id = request.POST.get('user_id')

    user_id = manage_cookies(request, 'user_id', None, 'get')
    # print('user_id: ' + str(user_id))
    try:
        user = User.objects.get(id=user_id)
        if user:
            user_profile = UserProfile.objects.get(user=user)
            # print('user_profile: ' + str(user_profile))
            profile_data = {
                'name': user_profile.name,
                'email': user_profile.email,
            }
            return JsonResponse({
                'success': True,
                'user_profile': profile_data
            })
        else:
            return JsonResponse({
                'success': False,
                'user_profile': None
            })
    except User.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'User not found',
            'user_profile': None
        })
    except UserProfile.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'User profile not found',
            'user_profile': None
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'user_profile': None
        })

@user_passes_test(is_staff)
def excursion_create(request):
    if request.method == 'POST':
        form = ExcursionForm(request.POST, request.FILES)
        formset = ExcursionImageFormSet(request.POST, request.FILES)
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    excursion = form.save()
                    formset.instance = excursion
                    formset.save()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': 'Excursion created successfully.',
                        'redirect_url': reverse('excursion_detail', kwargs={'pk': excursion.pk})
                    })
                messages.success(request, 'Excursion created successfully.')
                return redirect('excursion_detail', excursion.pk)
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': str(e)
                    })
                messages.error(request, f'Error creating excursion: {str(e)}')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # Format form errors for display
                error_messages = []
                for field, errors in form.errors.items():
                    field_name = form.fields[field].label if field in form.fields else field
                    for error in errors:
                        error_messages.append(f"{field_name}: {error}")
                
                # Add formset errors
                for i, form_errors in enumerate(formset.errors):
                    for field, errors in form_errors.items():
                        for error in errors:
                            error_messages.append(f"Image {i+1} {field}: {error}")
                
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the following errors:',
                    'errors': error_messages
                })
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ExcursionForm()
        formset = ExcursionImageFormSet()
    
    return render(request, 'main/excursions/excursion_form.html', {
        'form': form,
        'formset': formset,
    })

@user_passes_test(is_staff)
def excursion_update(request, pk):
    excursion = get_object_or_404(Excursion, pk=pk)
    
    if request.method == 'POST':
        form = ExcursionForm(request.POST, request.FILES, instance=excursion)
        formset = ExcursionImageFormSet(request.POST, request.FILES, instance=excursion)
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    excursion = form.save()
                    formset.save()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': 'Excursion updated successfully.',
                        'redirect_url': reverse('excursion_detail', kwargs={'pk': pk})
                    })
                messages.success(request, 'Excursion updated successfully.')
                return redirect('excursion_detail', pk)
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': str(e)
                    })
                messages.error(request, f'Error updating excursion: {str(e)}')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                error_messages = []
                for field, errors in form.errors.items():
                    field_name = form.fields[field].label if field in form.fields else field
                    for error in errors:
                        error_messages.append(f"{field_name}: {error}")
                
                # Add formset errors
                for i, form_errors in enumerate(formset.errors):
                    for field, errors in form_errors.items():
                        for error in errors:
                            error_messages.append(f"Image {i+1} {field}: {error}")
                
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the following errors:',
                    'errors': error_messages
                })
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ExcursionForm(instance=excursion)
        formset = ExcursionImageFormSet(instance=excursion)
    
    return render(request, 'main/excursions/excursion_form.html', {
        'form': form,
        'formset': formset,
        'excursion': excursion,
    })

@user_passes_test(is_staff)
def gallery_image_delete(request, pk):
    """Delete a single gallery image via AJAX"""
    if request.method == 'POST':
        try:
            image = get_object_or_404(ExcursionImage, pk=pk)
            excursion_pk = image.excursion.pk
            image.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Image deleted successfully.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({
        'success': False,
        'message': 'Invalid request method.'
    })

@user_passes_test(is_staff)
def gallery_reorder(request, pk):
    """Reorder gallery images via AJAX"""
    if request.method == 'POST':
        try:
            excursion = get_object_or_404(Excursion, pk=pk)
            image_orders = request.POST.getlist('image_order[]')
            
            for i, image_id in enumerate(image_orders):
                ExcursionImage.objects.filter(
                    id=image_id, 
                    excursion=excursion
                ).update(order=i)
            
            return JsonResponse({
                'success': True,
                'message': 'Gallery order updated successfully.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({
        'success': False,
        'message': 'Invalid request method.'
    })

@user_passes_test(is_staff)
def excursion_delete(request, pk):

    # item_id = request.POST.get('item_id')
    excursion = get_object_or_404(Excursion, pk=pk)

    if request.method == 'POST':
        excursion.delete()
        messages.success(request, 'Excursion deleted.')
        return redirect('excursion_list')
    else:
        messages.error(request, 'Excursion not deleted.')
        return redirect('excursion_list')
    
# ----- Booking Views -----
# Booking detail: only authenticated users (clients/reps/admins)
@login_required
def booking_delete(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check if user is staff or if the booking belongs to the user
    if not (request.user.is_staff or booking.user == request.user):
        return JsonResponse({
            'success': False,
            'message': 'You do not have permission to delete this booking.'
        })
    
    try:
        if request.method == 'POST':
            if booking:
                # Store booking details before deletion/cancellation
                customer_email = booking.guest_email or (booking.user.email if booking.user else None)
                customer_name = booking.guest_name or (booking.user.get_full_name() if booking.user else 'Guest')
                excursion_title = booking.excursion_availability.excursion.title
                booking_date = booking.date.strftime('%B %d, %Y') if booking.date else 'N/A'
                total_price = booking.total_price
                booking_id = booking.id

                # Send cancellation email to customer (both admin and user cancellations)
                try:
                    if customer_email:
                        builder = EmailBuilder()
                        builder.h2(f"Hello {customer_name}!")
                        
                        if request.user.is_staff:
                            # Admin cancelled
                            builder.warning("Your Booking Has Been Cancelled")
                            builder.p(
                                "We're writing to inform you that your booking has been cancelled by our team. "
                                "This may be due to excursion unavailability, weather conditions, or other operational reasons."
                            )
                        else:
                            # Customer cancelled
                            builder.p("Your booking has been cancelled as requested.")
                        
                        builder.card("Cancelled Booking", {
                            'Booking #': f'{booking_id}',
                            'Excursion': excursion_title,
                            'Date': booking_date,
                            'Amount': f"€{total_price:.2f}"
                        }, border_color="#e53935")
                        
                        if request.user.is_staff:
                            # Admin cancellation - offer more support
                            builder.p(
                                "We sincerely apologize for any inconvenience. If you've already made payment, "
                                "a full refund will be processed within 5-7 business days."
                            )
                            builder.list_box("💬 Need Assistance?", [
                                "Contact us for alternative excursion dates",
                                "Browse similar excursions on our website",
                                "Questions about refunds? Reach out to support",
                                "We're here to help make your trip memorable!"
                            ])
                        else:
                            # Customer cancellation
                            builder.p(
                                "If this was a mistake or you'd like to rebook, "
                                "you can browse our available excursions below."
                            )
                        
                        builder.button("Browse Excursions", request.build_absolute_uri(reverse('excursion_list')))
                        
                        if not request.user.is_staff:
                            builder.p("We hope to see you on another adventure soon!")
                        
                        builder.p("Best regards,<br>The iTrip Knossos Team")
                        
                        EmailService.send_dynamic_email(
                            subject='[iTrip Knossos] Booking Cancelled',
                            recipient_list=[customer_email],
                            email_body=builder.build(),
                            preview_text='Your booking has been cancelled',
                            fail_silently=True
                        )
                        logger.info(f'Booking cancellation email sent to {customer_email} for booking #{booking_id} (by {"admin" if request.user.is_staff else "customer"})')
                        
                except Exception as e:
                    logger.error(f'Failed to send cancellation email for booking #{booking_id}: {str(e)}')
                
                # Send admin notification for customer cancellations
                if not request.user.is_staff:
                    try:
                        builder = EmailBuilder()
                        builder.h2("Customer Booking Cancellation")
                        builder.warning("A customer has cancelled their booking")
                        
                        builder.card("Cancelled Booking Details", {
                            'Booking #': f'{booking_id}',
                            'Customer': f'{customer_name} ({customer_email or "No email"})',
                            'Excursion': excursion_title,
                            'Date': booking_date,
                            'Amount': f"€{total_price:.2f}",
                            'Cancelled By': 'Customer'
                        }, border_color="#ff6b35")
                        
                        builder.p("The customer cancelled this booking. Review if refund is needed.")
                        builder.p("Best regards,<br>Automated System")
                        
                        EmailService.send_dynamic_email(
                            subject=f'[iTrip Knossos] Customer Cancelled Booking #{booking_id}',
                            recipient_list=['bokis.angelov@innovade.eu'],
                            email_body=builder.build(),
                            preview_text=f'Customer cancelled booking for {excursion_title}',
                            fail_silently=True
                        )
                        logger.info(f'Admin notification sent for customer booking cancellation #{booking_id}')
                        
                    except Exception as e:
                        logger.error(f'Failed to send admin notification for cancellation #{booking_id}: {str(e)}')
                
                if request.user.is_staff:
                    booking.deleteByUser = False
                    booking.delete()
                else:
                    booking.deleteByUser = True
                    booking.payment_status = 'cancelled'
                    booking.save()
                
                messages.success(request, 'Booking deleted.')
                return JsonResponse({
                    'success': True,
                    'message': 'Booking deleted successfully.'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Booking not found.'
                })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Invalid request method.'
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error deleting booking: {str(e)}'
        })

# @login_required
def booking_detail(request, pk):
    
    booking = get_object_or_404(Booking, pk=pk)
    
    # Access control: Check if user has permission to view this booking
    has_access = False
    token = request.GET.get('token') or request.POST.get('token')
    
    # Staff can always access
    if request.user.is_authenticated and request.user.is_staff:
        has_access = True
    # Logged-in users can access their own bookings
    elif request.user.is_authenticated and booking.user and booking.user == request.user:
        has_access = True
    # Non-logged-in users need a valid token
    elif not request.user.is_authenticated and booking.access_token:
        if token and token == booking.access_token:
            has_access = True
    
    if not has_access:
        from django.http import Http404
        raise Http404("Booking not found or you don't have permission to view it.")

    payment_status = request.GET.get('payment_status')

    if payment_status == 'completed':
        try:
            booking.payment_status = 'completed'
            booking.save()
            messages.success(request, 'Booking completed.')
            # Preserve token in redirect if present
            redirect_url = reverse('booking_detail', kwargs={'pk': pk})
            if token:
                redirect_url += f'?token={token}'
            return redirect(redirect_url)
        except Exception as e:
            messages.error(request, f'Error updating booking: {str(e)}')
    if request.method == 'POST':
        # Handle both form data and JSON data
        if request.headers.get('Content-Type') == 'application/json':
            try:
                data = json.loads(request.body)
                action_type = data.get('action_type')
                # Get token from JSON data if present
                token = data.get('token') or token
            except json.JSONDecodeError:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid JSON data'
                })
        else:
            action_type = request.POST.get('action_type')
            # Get token from POST data if present
            token = request.POST.get('token') or token
        
        try:
            if action_type == 'complete_payment':
                booking.payment_status = 'completed'
                booking.save()
                messages.success(request, 'Booking completed.')

                # Preserve token in redirect if present
                redirect_url = reverse('booking_detail', kwargs={'pk': pk})
                if token:
                    redirect_url += f'?token={token}'
                return JsonResponse({
                    'status': 'success',
                    'message': 'Booking completed successfully.',
                    'redirect_url': redirect_url
                })

            elif action_type == 'cancel_payment':
                # Store info before cancellation
                customer_email = booking.guest_email or (booking.user.email if booking.user else None)
                customer_name = booking.guest_name or (booking.user.get_full_name() if booking.user else 'Guest')
                excursion_title = booking.excursion_availability.excursion.title
                booking_date = booking.date.strftime('%B %d, %Y') if booking.date else 'N/A'
                total_price = booking.total_price
                booking_id = booking.id
                
                booking.payment_status = 'cancelled'
                booking.save()
                
                # Send cancellation email to customer
                try:
                    if customer_email:
                        builder = EmailBuilder()
                        builder.h2(f"Hello {customer_name}!")
                        builder.p("Your booking has been cancelled as requested.")
                        
                        builder.card("Cancelled Booking", {
                            'Booking #': f'{booking_id}',
                            'Excursion': excursion_title,
                            'Date': booking_date,
                            'Cancelled Amount': f"€{total_price:.2f}"
                        }, border_color="#e53935")
                        
                        builder.p(
                            "If this was a mistake or you'd like to rebook, "
                            "you can browse our available excursions below."
                        )
                        builder.button("Browse Excursions", request.build_absolute_uri(reverse('excursion_list')))
                        builder.p("We hope to see you on another adventure soon!")
                        builder.p("Best regards,<br>The iTrip Knossos Team")
                        
                        EmailService.send_dynamic_email(
                            subject='[iTrip Knossos] Booking Cancelled',
                            recipient_list=[customer_email],
                            email_body=builder.build(),
                            preview_text='Your booking has been cancelled',
                            fail_silently=True
                        )
                        logger.info(f'Booking cancellation email sent to {customer_email} for booking #{booking_id}')
                        
                except Exception as e:
                    logger.error(f'Failed to send cancellation email for booking #{booking_id}: {str(e)}')
                
                # Send notification to admin
                try:
                    builder = EmailBuilder()
                    builder.h2("Customer Booking Cancellation")
                    builder.warning("A customer has cancelled their booking")
                    
                    builder.card("Cancelled Booking Details", {
                        'Booking #': f'{booking_id}',
                        'Customer': f'{customer_name} ({customer_email or "No email"})',
                        'Excursion': excursion_title,
                        'Date': booking_date,
                        'Amount': f"€{total_price:.2f}",
                        'Cancelled By': 'Customer'
                    }, border_color="#ff6b35")
                    
                    builder.p("The customer cancelled this booking. No further action required unless refund is needed.")
                    builder.p("Best regards,<br>Automated System")
                    
                    EmailService.send_dynamic_email(
                        subject=f'[iTrip Knossos] Customer Cancelled Booking #{booking_id}',
                        recipient_list=['bokis.angelov@innovade.eu'],
                        email_body=builder.build(),
                        preview_text=f'Customer cancelled booking for {excursion_title}',
                        fail_silently=True
                    )
                    logger.info(f'Admin notification sent for booking cancellation #{booking_id}')
                    
                except Exception as e:
                    logger.error(f'Failed to send admin notification for cancellation #{booking_id}: {str(e)}')
                
                messages.success(request, 'Booking cancelled.')
                return JsonResponse({
                    'status': 'success',
                    'message': 'Booking cancelled successfully.',
                    'redirect_url': reverse('excursion_detail', kwargs={'pk': booking.excursion_availability.excursion.id})
                })

            elif action_type == 'delete_booking':
                booking.delete()
                messages.success(request, 'Booking deleted.')
                return JsonResponse({
                    'status': 'success',
                    'message': 'Booking deleted successfully.',
                    'redirect_url': reverse('bookings_list')
                })
            elif action_type == 'pending_payment':
                booking.payment_status = 'pending'
                booking.save()
                messages.success(request, 'Booking set to pending.')
                # Preserve token in redirect if present
                redirect_url = reverse('booking_detail', kwargs={'pk': pk})
                if token:
                    redirect_url += f'?token={token}'
                return JsonResponse({
                    'status': 'success',
                    'message': 'Booking set to pending successfully.',
                    'redirect_url': redirect_url
                })
        
        except Exception as e:
            error_message = f'Error updating booking: {str(e)}'
            messages.error(request, error_message)
            return JsonResponse({
                'status': 'error',
                'message': error_message
            })

    # Check if excursion date is in the past
    is_date_past = False
    if booking.date:
        is_date_past = booking.date < timezone.now().date()
    
    # Check if user is viewing their own booking (for logged in users)
    is_own_booking = False
    if request.user.is_authenticated and booking.user:
        is_own_booking = booking.user == request.user
    
    return render(request, 'main/bookings/booking_detail.html', {
        'booking': booking,
        'is_date_past': is_date_past,
        'is_own_booking': is_own_booking,
        'access_token': token if not request.user.is_authenticated and booking.access_token else None,
    })

# ----- Checkout View -----
# Guests and clients go through checkout; reps/admins redirected to detail
def checkout(request, booking_pk):
    booking = get_object_or_404(Booking, pk=booking_pk)
    token = request.GET.get('token')
     
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        token = request.POST.get('token') or token
        
        # Handle referral code application
        if action_type == 'apply_referral':
            referral_code_str = request.POST.get('referral_code', '').strip()
            
            if referral_code_str:
                referral_code_instance = BookingService.handle_referral_code(referral_code_str)
                
                if referral_code_instance:
                    try:
                        BookingService.apply_referral_code_to_booking(booking, referral_code_instance)
                        messages.success(request, f'Referral code "{referral_code_instance.code}" applied successfully!')
                    except Exception as e:
                        messages.error(request, f'Error applying code: {str(e)}')
                else:
                    messages.error(request, 'Invalid or expired referral code.')
            else:
                messages.error(request, 'Please enter a referral code.')
            
            redirect_url = reverse('checkout', kwargs={'booking_pk': booking_pk})
            if token:
                redirect_url += f'?token={token}'
            return redirect(redirect_url)
        
        # Handle payment initiation
        # Redirect to JCC payment gateway
        if action_type == 'initiate_payment':
            redirect_url = reverse('payment_initiate', kwargs={'booking_pk': booking_pk})
            if token:
                redirect_url += f'?token={token}'
            return redirect(redirect_url)
        
        # Fallback: just save booking
        booking.save()
        messages.info(request, 'Booking saved.')
        redirect_url = reverse('checkout', kwargs={'booking_pk': booking_pk})
        if token:
            redirect_url += f'?token={token}'
        return redirect(redirect_url)
    

    return render(request, 'main/bookings/checkout.html', {
        'booking': booking,
        'access_token': token if not request.user.is_authenticated and booking.access_token else None,
    })

# ----- JCC Payment Views -----
def payment_initiate(request, booking_pk):
    """
    Initiate JCC payment by registering the order and redirecting to JCC payment page.
    This view is called when user clicks 'Pay' button in checkout.
    """
    booking = get_object_or_404(Booking, pk=booking_pk)
    
    token = request.GET.get('token')
    
    # Check if booking is already paid
    if booking.payment_status == 'completed':
        messages.info(request, 'This booking has already been paid.')
        redirect_url = reverse('booking_detail', kwargs={'pk': booking_pk})
        if token:
            redirect_url += f'?token={token}'
        return redirect(redirect_url)
    
    # Check if booking has a valid final price
    final_price = booking.get_final_price
    if final_price <= 0:
        messages.error(request, 'Invalid booking amount. Please contact support.')
        redirect_url = reverse('checkout', kwargs={'booking_pk': booking_pk})
        if token:
            redirect_url += f'?token={token}'
        return redirect(redirect_url)
    
    # Check if booking already has a JCC order ID
    # If it does, check the status first before creating a new order
    if booking.jcc_order_id:
        try:
            logger.info(f"Booking #{booking_pk} already has JCC order ID: {booking.jcc_order_id}. Checking status...")
            order_status = JCCPaymentService.get_order_status(booking.jcc_order_id)
            
            # Check if payment was successful
            if JCCPaymentService.is_payment_successful(order_status):
                # Payment is already completed, update booking status
                booking.payment_status = 'completed'
                booking.save(update_fields=['payment_status'])
                messages.success(request, 'Payment was already completed. Your booking is confirmed.')
                redirect_url = reverse('booking_detail', kwargs={'pk': booking_pk})
                if token:
                    redirect_url += f'?token={token}'
                return redirect(redirect_url)
            
            # If order is still pending, we need to create a new order with a different order number
            # JCC doesn't allow duplicate order numbers, so we'll use a timestamp-based order number
            logger.info(f"Previous JCC order for booking #{booking_pk} is still pending. Creating new order with unique order number.")
        except Exception as e:
            # If we can't check the status, proceed with creating a new order
            logger.warning(f"Could not check status of existing JCC order for booking #{booking_pk}: {str(e)}. Creating new order.")
    
    try:
        # Build return URLs (success and failure)
        # Using request.build_absolute_uri to ensure full URLs
        return_url = request.build_absolute_uri(
            reverse('payment_success', kwargs={'booking_pk': booking_pk})
        )
        fail_url = request.build_absolute_uri(
            reverse('payment_fail', kwargs={'booking_pk': booking_pk})
        )
        
        # Log URLs for debugging
        logger.info(f"Initiating payment for booking #{booking_pk}. Return URL: {return_url}, Fail URL: {fail_url}")
        
        # Register order with JCC
        # If booking already has a jcc_order_id, use a unique order number to avoid duplicates
        use_unique_order_number = bool(booking.jcc_order_id)
        response_data = JCCPaymentService.register_order(
            booking=booking,
            return_url=return_url,
            fail_url=fail_url,
            description=f"Booking #{booking.id} - {booking.excursion_availability.excursion.title if booking.excursion_availability else 'Excursion'}",
            language='en',  # You can make this dynamic based on user preference
            use_unique_order_number=use_unique_order_number
        )
        
        # Store JCC order ID in booking
        booking.jcc_order_id = response_data['orderId']
        booking.save(update_fields=['jcc_order_id'])
        
        # Redirect user to JCC payment page
        form_url = response_data['formUrl']
        return redirect(form_url)
        
    except ValidationError as e:
        messages.error(request, f'Payment initialization failed: {str(e)}')
        logger.error(f"JCC payment initiation error for booking #{booking_pk}: {str(e)}")
        redirect_url = reverse('checkout', kwargs={'booking_pk': booking_pk})
        if token:
            redirect_url += f'?token={token}'
        return redirect(redirect_url)
    except Exception as e:
        messages.error(request, 'An error occurred while initiating payment. Please try again.')
        logger.error(f"Unexpected error during JCC payment initiation for booking #{booking_pk}: {str(e)}")
        redirect_url = reverse('checkout', kwargs={'booking_pk': booking_pk})
        if token:
            redirect_url += f'?token={token}'
        return redirect(redirect_url)


def payment_success(request, booking_pk=None):
    """
    Handle successful payment return from JCC.
    This is the returnUrl callback - user is redirected here after payment.
    """
    # Log all GET parameters for debugging
    logger.info(f"Payment success callback. GET params: {dict(request.GET)}, booking_pk: {booking_pk}")
    
    # Get orderId from request parameters (JCC may send it as 'orderId' or 'mdOrder')
    order_id = request.GET.get('orderId') or request.GET.get('mdOrder')
    
    # Try to get booking by booking_pk first, then by orderId if booking_pk is missing
    booking = None
    if booking_pk:
        try:
            booking = Booking.objects.get(pk=booking_pk)
        except Booking.DoesNotExist:
            logger.warning(f"Booking #{booking_pk} not found, trying to find by orderId")
    
    # If we have orderId but no booking, try to find booking by orderId
    if not booking and order_id:
        try:
            booking = Booking.objects.get(jcc_order_id=order_id)
            booking_pk = booking.pk
            logger.info(f"Found booking #{booking_pk} by orderId: {order_id}")
        except Booking.DoesNotExist:
            logger.error(f"No booking found with orderId: {order_id}")
        except Booking.MultipleObjectsReturned:
            logger.error(f"Multiple bookings found with orderId: {order_id}")
    
    if not booking:
        messages.error(request, 'Payment verification failed: Booking not found.')
        logger.error(f"Payment success callback but no booking found. booking_pk: {booking_pk}, orderId: {order_id}")
        return redirect('bookings_list')
    
    # Update jcc_order_id if we got it from the request and it's different
    if order_id and order_id != booking.jcc_order_id:
        booking.jcc_order_id = order_id
        booking.save(update_fields=['jcc_order_id'])
    
    # Use the order_id from booking if we don't have it from request
    if not order_id:
        order_id = booking.jcc_order_id
    
    # Get token from booking if it exists (for non-logged-in users)
    token = booking.access_token if booking.access_token and not request.user.is_authenticated else None
    
    if not order_id:
        messages.error(request, 'Payment verification failed: Order ID not found.')
        logger.error(f"Payment success callback for booking #{booking.pk} but no orderId found. Available params: {dict(request.GET)}")
        redirect_url = reverse('booking_detail', kwargs={'pk': booking.pk})
        if token:
            redirect_url += f'?token={token}'
        return redirect(redirect_url)
    
    # Verify payment status with JCC (server-side verification)
    try:
        order_status = JCCPaymentService.get_order_status(order_id)
        
        if JCCPaymentService.is_payment_successful(order_status):
            # Payment is confirmed successful
            booking.payment_status = 'completed'
            booking.save(update_fields=['payment_status'])
            
            # Send booking confirmation email
            try:
                customer_email = booking.guest_email or (booking.user.email if booking.user else None)
                customer_name = booking.guest_name or (booking.user.get_full_name() if booking.user else 'Guest')
                
                if customer_email:
                    # Build booking URL
                    booking_url = request.build_absolute_uri(
                        reverse('booking_detail', kwargs={'pk': booking.pk})
                    )
                    if booking.access_token:
                        booking_url += f'?token={booking.access_token}'
                    
                    # Build email
                    builder = EmailBuilder()
                    builder.h2(f"Hello {customer_name}!")
                    builder.success("Your booking has been confirmed!")
                    builder.p("Thank you for choosing iTrip Knossos. We're excited to have you join us for an unforgettable experience!")
                    
                    # Booking details
                    builder.card("Booking Details", {
                        'Confirmation #': f'{booking.id}',
                        'Excursion': booking.excursion_availability.excursion.title,
                        'Date': booking.date.strftime('%B %d, %Y'),
                        'Pickup Point': booking.pickup_point.name if booking.pickup_point else 'To be confirmed',
                        'Guests': f"{booking.total_adults or 0} Adults, {booking.total_kids or 0} Children, {booking.total_infants or 0} Infants",
                        'Total Paid': f"€{booking.total_price:.2f}"
                    })
                    
                    builder.button("View Full Booking Details", booking_url)
                    
                    # Important information
                    builder.list_box("📋 Important Information", [
                        "Please arrive at the pickup point 10 minutes before the scheduled time",
                        "Bring comfortable shoes, sunscreen, and water",
                        "Pickup time will be confirmed 24-48 hours before the excursion",
                        "For cancellations, contact us at least 24 hours in advance"
                    ])
                    
                    builder.p("If you have any questions, please don't hesitate to contact us.")
                    builder.p("Best regards,<br>The iTrip Knossos Team")
                    
                    EmailService.send_dynamic_email(
                        subject=f'[iTrip Knossos] Booking Confirmed - {booking.excursion_availability.excursion.title}',
                        recipient_list=[customer_email],
                        email_body=builder.build(),
                        preview_text=f'Your booking for {booking.excursion_availability.excursion.title} is confirmed!',
                        fail_silently=True
                    )
                    logger.info(f'Booking confirmation email sent to {customer_email} for booking #{booking.pk}')
                    
            except Exception as e:
                logger.error(f'Failed to send booking confirmation email for booking #{booking.pk}: {str(e)}')
            
            messages.success(request, 'Payment completed successfully! Your booking is confirmed.')
            logger.info(f"Payment confirmed for booking #{booking_pk}, orderId: {order_id}")
        else:
            # Payment was not successful (user may have been redirected but payment failed)
            order_status_code = order_status.get('orderStatus', 'unknown')
            action_code = order_status.get('actionCode', 'unknown')
            messages.warning(
                request, 
                f'Payment verification failed. Status: {order_status_code}, Action: {action_code}. '
                'Please contact support if payment was deducted.'
            )
            logger.warning(
                f"Payment verification failed for booking #{booking.pk}, "
                f"orderId: {order_id}, status: {order_status_code}, action: {action_code}"
            )
        
    except ValidationError as e:
        messages.error(request, f'Payment verification failed: {str(e)}. Please contact support.')
        logger.error(f"Payment verification error for booking #{booking.pk}: {str(e)}")
    except Exception as e:
        messages.error(request, 'An error occurred while verifying payment. Please contact support.')
        logger.error(f"Unexpected error during payment verification for booking #{booking.pk}: {str(e)}")
    
    # Get token from booking if it exists (for non-logged-in users)
    token = booking.access_token if booking.access_token and not request.user.is_authenticated else None
    redirect_url = reverse('booking_detail', kwargs={'pk': booking.pk})
    if token:
        redirect_url += f'?token={token}'
    return redirect(redirect_url)


def payment_fail(request, booking_pk=None):
    """
    Handle failed payment return from JCC.
    This is the failUrl callback - user is redirected here if payment fails or is cancelled.
    """
    # Log all GET parameters for debugging
    logger.info(f"Payment fail callback. GET params: {dict(request.GET)}, booking_pk: {booking_pk}")
    
    # Get orderId from request parameters (JCC may send it as 'orderId' or 'mdOrder')
    order_id = request.GET.get('orderId') or request.GET.get('mdOrder')
    
    # Try to get booking by booking_pk first, then by orderId if booking_pk is missing
    booking = None
    if booking_pk:
        try:
            booking = Booking.objects.get(pk=booking_pk)
        except Booking.DoesNotExist:
            logger.warning(f"Booking #{booking_pk} not found, trying to find by orderId")
    
    # If we have orderId but no booking, try to find booking by orderId
    if not booking and order_id:
        try:
            booking = Booking.objects.get(jcc_order_id=order_id)
            booking_pk = booking.pk
            logger.info(f"Found booking #{booking_pk} by orderId: {order_id}")
        except Booking.DoesNotExist:
            logger.error(f"No booking found with orderId: {order_id}")
        except Booking.MultipleObjectsReturned:
            logger.error(f"Multiple bookings found with orderId: {order_id}")
    
    if not booking:
        messages.warning(request, 'Payment was not completed. Could not find booking.')
        logger.error(f"Payment fail callback but no booking found. booking_pk: {booking_pk}, orderId: {order_id}")
        return redirect('bookings_list')
    
    # Use the order_id from booking if we don't have it from request
    if not order_id:
        order_id = booking.jcc_order_id
    
    # Optionally verify status to get more details
    if order_id:
        try:
            order_status = JCCPaymentService.get_order_status(order_id)
            order_status_code = order_status.get('orderStatus', 'unknown')
            action_code = order_status.get('actionCode', 'unknown')
            
            logger.info(
                f"Payment failed for booking #{booking_pk}, "
                f"orderId: {order_id}, status: {order_status_code}, action: {action_code}"
            )
        except Exception as e:
            logger.warning(f"Could not verify payment status for booking #{booking_pk}: {str(e)}")
    
    # Send payment failed email
    try:
        customer_email = booking.guest_email or (booking.user.email if booking.user else None)
        customer_name = booking.guest_name or (booking.user.get_full_name() if booking.user else 'Guest')
        
        if customer_email:
            # Build checkout URL
            checkout_url = request.build_absolute_uri(
                reverse('checkout', kwargs={'booking_pk': booking.pk})
            )
            if booking.access_token:
                checkout_url += f'?token={booking.access_token}'
            
            # Build email
            builder = EmailBuilder()
            builder.h2(f"Hello {customer_name}!")
            builder.error("Payment was not successful")
            builder.p(
                f"We were unable to process your payment for booking #{booking.id}. "
                "This may happen due to insufficient funds, incorrect card details, "
                "or a temporary issue with your payment provider."
            )
            
            # Booking info
            builder.card("Booking Information", {
                'Booking #': f'{booking.id}',
                'Excursion': booking.excursion_availability.excursion.title,
                'Date': booking.date.strftime('%B %d, %Y'),
                'Amount Due': f"€{booking.total_price:.2f}"
            })
            
            builder.button("Retry Payment", checkout_url, color="#ff6b35")
            
            builder.p(
                "If you continue to experience issues, please check with your bank or "
                "reach out to our support team for assistance."
            )
            builder.p("Best regards,<br>The iTrip Knossos Team")
            
            EmailService.send_dynamic_email(
                subject='[iTrip Knossos] Payment Failed - Action Required',
                recipient_list=[customer_email],
                email_body=builder.build(),
                preview_text='Payment failed for your booking. Please retry.',
                fail_silently=True
            )
            logger.info(f'Payment failed email sent to {customer_email} for booking #{booking.pk}')
            
    except Exception as e:
        logger.error(f'Failed to send payment failed email for booking #{booking.pk}: {str(e)}')
    
    # Keep payment status as pending (don't mark as cancelled automatically)
    # User can retry payment
    messages.warning(request, 'Payment was not completed. You can try again from the checkout page.')
    
    # Get token from booking if it exists (for non-logged-in users)
    token = booking.access_token if booking.access_token and not request.user.is_authenticated else None
    redirect_url = reverse('checkout', kwargs={'booking_pk': booking.pk})
    if token:
        redirect_url += f'?token={token}'
    return redirect(redirect_url)

# ----- Auth Views -----
def signup(request):
    """
    Improved signup view with email verification.
    Creates user account and sends verification email.
    """
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    from .utils import EmailService
    
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            try:
                # Check if email already exists
                email = form.cleaned_data['username']  # username is actually email
                if User.objects.filter(email=email).exists() or User.objects.filter(username=email).exists():
                    messages.error(request, 'An account with this email already exists. Please use a different email or try logging in.')
                    return render(request, 'main/accounts/signup.html', {'form': form})
                
                # Create user
                user = form.save()
                if not user:
                    messages.error(request, 'Failed to create account. Please try again.')
                    return render(request, 'main/accounts/signup.html', {'form': form})
                
                # Create user profile
                user_profile = UserProfile.objects.create(
                    user=user,
                    role='client',
                    name=form.cleaned_data['name'],
                    email=email,
                    phone=form.cleaned_data.get('phone', ''),
                    email_verified=False  # Email not verified yet
                )
                
                # Generate email verification token
                token = default_token_generator.make_token(user)
                user_profile.email_verification_token = token
                user_profile.save()
                
                # Create verification URL
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                verification_url = f"{request.scheme}://{request.get_host()}/verify_email/{uid}/{token}/"
                
                # Build verification email
                builder = EmailBuilder()
                builder.h2(f"Hello {form.cleaned_data['name']}!")
                builder.p("Thank you for signing up for iTrip Knossos!")
                builder.p("Please verify your email address to activate your account.")
                builder.button("Verify Email Address", verification_url)
                builder.p(
                    f'Or copy and paste this link into your browser:<br>'
                    f'<a href="{verification_url}" style="color: #2196f3; word-break: break-all;">{verification_url}</a>',
                    size="14px"
                )
                builder.list_box("⏱️ Important", [
                    "This link will expire in 24 hours",
                    "If you did not create an account, please ignore this email"
                ])
                builder.p("Best regards,<br>The iTrip Knossos Team")
                
                try:
                    EmailService.send_dynamic_email(
                        subject='[iTrip Knossos] Verify Your Email Address',
                        recipient_list=[email],
                        email_body=builder.build(),
                        preview_text='Verify your email to activate your account',
                        fail_silently=False
                    )
                    messages.success(
                        request, 
                        'Account created successfully! Please check your email to verify your account. '
                        'You can log in after verification.'
                    )
                except Exception as email_error:
                    # If email fails, still create account but warn user
                    logger.error(f"Failed to send verification email: {str(email_error)}")
                    messages.warning(
                        request,
                        'Account created, but we could not send the verification email. '
                        'Please contact support for assistance.'
                    )
                
                # Don't log in automatically - require email verification first
                return redirect('login')
                
            except Exception as e:
                logger.error(f"Error during signup: {str(e)}", exc_info=True)
                messages.error(request, f'An error occurred while creating your account. Please try again.')
                return render(request, 'main/accounts/signup.html', {'form': form})
        else:
            # Form validation errors
            error_messages = []
            for field, errors in form.errors.items():
                for error in errors:
                    error_messages.append(f"{form.fields[field].label if field in form.fields else field}: {error}")
            
            if error_messages:
                messages.error(request, 'Please correct the following errors: ' + ' '.join(error_messages))
            else:
                messages.error(request, 'Please correct the errors below.')
            
            return render(request, 'main/accounts/signup.html', {'form': form})
    else:
        form = SignupForm()

    return render(request, 'main/accounts/signup.html', {'form': form})

@ensure_csrf_cookie
def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user:
                login(request, user)
                if user.profile.role == 'admin':
                    response = redirect('admin_dashboard', user.profile.id)
                else:
                    response = redirect('excursion_list')
            else:
                return redirect('login')
            
            response.delete_cookie('voucher_code')
            
            response.set_cookie('user_id', user.id)
            response.set_cookie('user_role', user.profile.role)
            return response
        else:
            messages.error(request, 'Invalid credentials, username and password do not match.')
            return redirect('login')
    else:
        form = AuthenticationForm()
    return render(request, 'main/accounts/login.html', {'form': form})

def logout_view(request):
    logout(request)
    response = redirect('excursion_list')
    response.delete_cookie('voucher_code')
    response.delete_cookie('user_id')
    response.delete_cookie('user_role')
    return response

def password_reset_form(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        
        if email:
            user = User.objects.filter(email=email).first()
        else:
            messages.error(request, 'Email is required.')
            return render(request, 'main/accounts/password_reset_form.html')
        
        if user:
            # Generate password reset token
            token = PasswordResetTokenGenerator().make_token(user)
            print(f'Generated token: {token}')
            
            # Store the token in UserProfile
            try:
                user_profile = user.profile
                user_profile.password_reset_token = token
                user_profile.save()
            except UserProfile.DoesNotExist:
                messages.error(request, 'User profile not found.')
                return render(request, 'main/accounts/password_reset_form.html')
            
            # Build reset URL
            reset_url = f"{request.scheme}://{request.get_host()}/password_reset_token/{token}/"
            user_name = user_profile.name or user.username
            
            # Build email content
            builder = EmailBuilder()
            builder.h2(f"Hello {user_name}!")
            builder.p(
                "We received a request to reset your password for your iTrip Knossos account. "
                "If you didn't make this request, you can safely ignore this email."
            )
            builder.button("Reset Password", reset_url)
            builder.p(
                f'Or copy and paste this link into your browser:<br>'
                f'<a href="{reset_url}" style="color: #2196f3; word-break: break-all;">{reset_url}</a>',
                size="14px"
            )
            builder.p("Best regards,<br>The iTrip Knossos Team")
            
            # Send email
            EmailService.send_dynamic_email(
                subject='[iTrip Knossos] Password Reset Request',
                recipient_list=[email],
                email_body=builder.build(),
                preview_text='Reset your password for iTrip Knossos',
                fail_silently=True
            )
            
            messages.success(request, 'Password reset email sent. Please check your email.')
            return redirect('login')
        else:
            messages.error(request, 'Email not found.')
            
    return render(request, 'main/accounts/password_reset_form.html')

def password_reset_token(request, token):
    
    if request.method == 'POST':
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        if not password or not confirm_password:
            messages.error(request, 'Please fill in all fields.')
            return render(request, 'main/accounts/password_reset_token.html', {'token': token})
        
        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'main/accounts/password_reset_token.html', {'token': token})
        else:
            user_profile = UserProfile.objects.filter(password_reset_token=token).first()
            
            if not user_profile:
                messages.error(request, 'Invalid or expired token.')
                return redirect('password_reset_form')
                
            user = user_profile.user

            if user:
                check_token = PasswordResetTokenGenerator().check_token(user, token)
                if not check_token:
                    messages.error(request, 'Invalid token.')
                    return redirect('password_reset_form')
                else:   
                    user.set_password(password)
                    user_profile.password_reset_token = None
                    user_profile.save()
                    user.save()
                    messages.success(request, 'Password reset successfully! You can now login with your new password.')
                    return redirect('login')
            else:
                messages.error(request, 'Invalid token.')
                return redirect('password_reset_form')
            
    return render(request, 'main/accounts/password_reset_token.html', {'token': token})

def verify_email(request, uidb64, token):
    """
    Verify user email address using secure token.
    """
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_decode
    from django.utils.encoding import force_str
    from django.contrib.auth import login
    
    try:
        # Decode user ID from base64
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
        logger.warning(f"Invalid uidb64 in email verification: {uidb64}")
    
    if user is None:
        messages.error(request, 'Invalid verification link. Please request a new verification email.')
        return redirect('signup')
    
    # Check if user profile exists
    try:
        user_profile = user.profile
    except UserProfile.DoesNotExist:
        messages.error(request, 'User profile not found. Please contact support.')
        return redirect('signup')
    
    # Check if email is already verified
    if user_profile.email_verified:
        messages.info(request, 'Your email is already verified. You can log in now.')
        if not request.user.is_authenticated:
            login(request, user)
        return redirect('excursion_list')
    
    # Verify token
    if not default_token_generator.check_token(user, token):
        messages.error(request, 'Invalid or expired verification link. Please request a new verification email.')
        return redirect('signup')
    
    # Check if token matches stored token (additional security check)
    if user_profile.email_verification_token != token:
        messages.error(request, 'Invalid verification token. Please request a new verification email.')
        return redirect('signup')
    
    # Mark email as verified
    user_profile.email_verified = True
    user_profile.email_verification_token = None  # Clear token after verification
    user_profile.save()
    
    # Automatically log in the user after verification
    login(request, user)
    
    messages.success(
        request, 
        'Email verified successfully! Your account is now active. Welcome to iTrip Knossos!'
    )
    
    # Redirect based on user role
    if user_profile.role == 'client':
        return redirect('excursion_list')
    elif user_profile.role == 'admin':
        return redirect('admin_dashboard', user_profile.id)
    else:
        return redirect('profile', user_profile.id)

@login_required
def profile(request, pk):
    user = get_object_or_404(User, pk=pk)
    profile = UserProfile.objects.get(user=user)
    
    # Get bookings - for agents, include bookings using their referral codes
    if profile.role == 'agent':
        # Include both: bookings made by this user AND bookings using their referral codes
        bookings = Booking.objects.filter(
            Q(user=user, deleteByUser=False) | 
            Q(referral_code__agent=profile, deleteByUser=False)
        ).distinct().order_by('-created_at')
    else:
        # For non-agents, only show their own bookings
        bookings = Booking.objects.filter(user=user, deleteByUser=False).order_by('-created_at')
    
    # Get reservations linked to this user profile
    reservations = Reservation.objects.filter(client_profile=profile).order_by('-created_at')

    # Only allow users to view their own profile unless they're staff
    if request.user.id != user.id and not request.user.is_staff:
        messages.error(request, "You don't have permission to view this profile.")
        return redirect('homepage')
    
    # Get referral codes if profile is an agent
    referral_codes = None
    if profile.role == 'agent':
        from .models import ReferralCode
        referral_codes = ReferralCode.objects.filter(agent=profile).order_by('-created_at')
    
    return render(request, 'main/accounts/profile.html', {
        'bookings': bookings,
        'user_profile': profile,
        'reservations': reservations,
        'referral_codes': referral_codes,
    })    

@user_passes_test(is_staff)
def manage_referral_codes(request):
    """Handle referral code generation and editing for agents"""
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        agent_id = request.POST.get('agent_id')
        
        if not agent_id:
            messages.error(request, 'Agent ID is required.')
            return redirect('agents_list')
        
        agent = get_object_or_404(UserProfile, id=agent_id, role='agent')
        
        if action_type == 'generate_code':
            discount = request.POST.get('discount', '').strip()
            expires_at = request.POST.get('expires_at', '').strip()
            
            if not discount or not expires_at:
                messages.error(request, 'Discount and expiration date are required.')
                return redirect('profile', pk=agent.user.id)
            
            try:
                from .models import ReferralCode
                from django.utils import timezone
                import datetime
                
                # Parse the expiration date
                expires_datetime = datetime.datetime.strptime(expires_at, '%Y-%m-%d')
                expires_datetime = timezone.make_aware(
                    datetime.datetime.combine(expires_datetime.date(), datetime.time(23, 59, 59))
                )
                
                # Generate unique code
                code = ReferralCode.generate_unique_code(agent.name, float(discount))
                
                # Create the referral code
                ReferralCode.objects.create(
                    code=code,
                    agent=agent,
                    discount=float(discount),
                    expires_at=expires_datetime,
                    status='active'
                )
                
                messages.success(request, f'Referral code "{code}" generated successfully!')
                return redirect('profile', pk=agent.user.id)
                
            except ValueError as e:
                messages.error(request, f'Invalid discount or date format: {str(e)}')
                return redirect('profile', pk=agent.user.id)
            except Exception as e:
                messages.error(request, f'Error generating code: {str(e)}')
                return redirect('profile', pk=agent.user.id)
        
        elif action_type == 'edit_code':
            code_id = request.POST.get('code_id')
            discount = request.POST.get('discount', '').strip()
            expires_at = request.POST.get('expires_at', '').strip()
            status = request.POST.get('status', '').strip()
            
            if not code_id:
                messages.error(request, 'Code ID is required.')
                return redirect('profile', pk=agent.user.id)
            
            try:
                from .models import ReferralCode
                from django.utils import timezone
                import datetime
                
                code = get_object_or_404(ReferralCode, id=code_id, agent=agent)
                
                if discount:
                    code.discount = float(discount)
                
                if expires_at:
                    expires_datetime = datetime.datetime.strptime(expires_at, '%Y-%m-%d')
                    code.expires_at = timezone.make_aware(
                        datetime.datetime.combine(expires_datetime.date(), datetime.time(23, 59, 59))
                    )
                
                if status:
                    code.status = status
                
                code.save()
                messages.success(request, f'Referral code "{code.code}" updated successfully!')
                return redirect('profile', pk=agent.user.id)
                
            except ValueError as e:
                messages.error(request, f'Invalid discount or date format: {str(e)}')
                return redirect('profile', pk=agent.user.id)
            except Exception as e:
                messages.error(request, f'Error updating code: {str(e)}')
                return redirect('profile', pk=agent.user.id)
        
        elif action_type == 'delete_code':
            code_id = request.POST.get('code_id')
            
            if not code_id:
                messages.error(request, 'Code ID is required.')
                return redirect('profile', pk=agent.user.id)
            
            try:
                from .models import ReferralCode
                code = get_object_or_404(ReferralCode, id=code_id, agent=agent)
                code_str = code.code
                code.delete()
                messages.success(request, f'Referral code "{code_str}" deleted successfully!')
                return redirect('profile', pk=agent.user.id)
                
            except Exception as e:
                messages.error(request, f'Error deleting code: {str(e)}')
                return redirect('profile', pk=agent.user.id)
    
    return redirect('agents_list')

@login_required
def profile_edit(request, pk):
    # Get the user first, then their profile
    user = get_object_or_404(User, pk=pk)
    profile = get_object_or_404(UserProfile, user=user)

    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        try:
            if form.is_valid():
                # Save profile data
                form.save()
                
                # Handle password change if provided
                password1 = form.cleaned_data.get('password1')
                if password1:
                    user.set_password(password1)
                    user.save()
                    messages.success(request, 'Profile and password updated successfully.')
                else:
                    messages.success(request, 'Profile updated successfully.')
                
                return redirect('profile', pk=pk)
        except Exception as e:
            messages.error(request, f'Error updating profile: {str(e)}')
    else:
        # Initialize form with existing profile data for GET requests
        form = UserProfileForm(instance=profile)
    
    return render(request, 'main/accounts/edit_profile.html', {
        'form': form,
        'user_profile': profile,
    })

# @login_required
@user_passes_test(is_staff)
def admin_dashboard(request, pk):
    # Get admin stats
    active_excursions_count = Excursion.objects.filter(status='active').count()
    total_excursions_count = Excursion.objects.all().count()
    reps_count = User.objects.filter(profile__role='representative').exclude(is_staff=True).count()
    clients_count = User.objects.filter(profile__role='client').exclude(is_staff=True).count()
    user = User.objects.get(profile__id=pk)
    user_profile = UserProfile.objects.get(user=user)

    upcoming_excursions = AvailabilityDays.objects.filter(excursion_availability__status='active', date_day__gte=timezone.now()).order_by('date_day')[:5]

    total_revenue = Booking.objects.filter(payment_status='completed').aggregate(
        total=Sum('total_price')
    )['total'] or 0
    
    # Recent bookings
    recent_bookings = Booking.objects.all().order_by('-created_at')[:5]

    # pickup_groups = get_groups()
    # hotels = get_hotels()
    # print(hotels)
    # for hotel in hotels:
    #     print(f'  - {hotel}')
    
    context = {
        'active_excursions_count': active_excursions_count,
        'reps_count': reps_count,
        'clients_count': clients_count,
        'total_revenue': total_revenue,
        'recent_bookings': recent_bookings,
        'booking_count': Booking.objects.filter(payment_status='completed').count(),
        'user_profile': user_profile,
        'total_excursions_count': total_excursions_count,
        'upcoming_excursions': upcoming_excursions,
    }
    
    return render(request, 'main/admin/dashboard.html', context)

# ----- Group Views -----
# Only admins can manage groups
@user_passes_test(is_staff)
def group_list(request):
    groups = Group.objects.select_related('excursion').prefetch_related('bookings').all().order_by('-date')

    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        groups = groups.filter(
            Q(name__icontains=search_query) |
            Q(excursion__title__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(groups, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'main/groups/group_list.html', {
        'groups': page_obj.object_list,
        'search_query': search_query,
        'page_obj': page_obj,
    })

@user_passes_test(is_staff)
def group_create(request):
    if request.method == 'POST':
        form = GroupForm(request.POST)
        if form.is_valid():
            group = form.save()  # Form now handles bookings assignment
            
            # Check capacity and warn if exceeded
            if group.bus:
                from .utils import TransportGroupService
                total_guests = TransportGroupService.calculate_total_guests(
                    list(group.bookings.values_list('id', flat=True))
                )
                if total_guests > group.bus.capacity:
                    messages.warning(request, f'Warning: Group has {total_guests} guests, exceeding the bus capacity of {group.bus.capacity}.')
            
            messages.success(request, 'Group created successfully.')
            return redirect('group_detail', pk=group.pk)
    else:
        form = GroupForm()
    
    return render(request, 'main/groups/group_form.html', {
        'form': form,
        'is_update': False,
    })

@user_passes_test(is_staff)
def group_detail(request, pk):
    from .models import GroupPickupPoint
    
    group = get_object_or_404(Group.objects.prefetch_related(
        'bookings', 
        'bookings__pickup_point',
        'bookings__pickup_point__pickup_group',
        'bookings__voucher_id',
        'pickup_times',
        'pickup_times__pickup_point'
    ), pk=pk)
    
    # Group bookings by pickup point for display
    from .utils import TransportGroupService
    bookings = group.bookings.all().order_by(
        'pickup_point__pickup_group__name',
        'pickup_point__name'
    )
    
    # Get pickup group summary (hierarchical structure)
    pickup_summary = TransportGroupService.get_pickup_group_summary(bookings)
    
    # Get all unique pickup points from bookings
    unique_pickup_points = set()
    for booking in bookings:
        if booking.pickup_point:
            unique_pickup_points.add(booking.pickup_point)
    
    # Get or create GroupPickupPoint entries for each pickup point
    pickup_times_dict = {}
    for pickup_point in unique_pickup_points:
        gpp, created = GroupPickupPoint.objects.get_or_create(
            group=group,
            pickup_point=pickup_point
        )
        pickup_times_dict[pickup_point.id] = gpp.pickup_time
    
    # Add pickup times to the pickup summary structure
    for pickup_group in pickup_summary:
        for pickup_point_summary in pickup_group['pickup_point_summaries']:
            if pickup_point_summary['pickup_point']:
                pickup_point_id = pickup_point_summary['pickup_point'].id
                pickup_point_summary['pickup_time'] = pickup_times_dict.get(pickup_point_id)
    
    # Check if all pickup times are set
    all_times_set = all(time is not None for time in pickup_times_dict.values()) and len(pickup_times_dict) > 0
    
    return render(request, 'main/groups/group_detail.html', {
        'group': group,
        'bookings': bookings,
        'pickup_groups': pickup_summary,
        'all_times_set': all_times_set,
    })

@user_passes_test(is_staff)
def group_update(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        form = GroupForm(request.POST, instance=group)
        if form.is_valid():
            group = form.save()  # Form now handles bookings assignment
            
            # Check capacity and warn if exceeded
            if group.bus:
                from .utils import TransportGroupService
                total_guests = TransportGroupService.calculate_total_guests(
                    list(group.bookings.values_list('id', flat=True))
                )
                if total_guests > group.bus.capacity:
                    messages.warning(request, f'Warning: Group has {total_guests} guests, exceeding the bus capacity of {group.bus.capacity}.')
            
            messages.success(request, 'Group updated successfully.')
            return redirect('group_detail', pk=group.pk) 
    else:
        form = GroupForm(instance=group)
    
    # Get existing booking IDs for JavaScript
    existing_booking_ids = list(group.bookings.values_list('id', flat=True))
    
    return render(request, 'main/groups/group_form.html', {
        'form': form,
        'group': group,
        'is_update': True,
        'existing_booking_ids': existing_booking_ids,
    })

@user_passes_test(is_staff)
def group_delete(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        group_name = group.name
        
        # Note: AvailabilityDays reactivation is handled automatically via post_delete signal (see signals.py)
        group.delete()
        
        messages.success(request, f'Group "{group_name}" deleted successfully.')
        return redirect('group_list')
    
    # If GET request, redirect to group detail instead
    return redirect('group_detail', pk=pk)

@user_passes_test(is_staff)
def set_pickup_time(request, pk):
    """AJAX endpoint to save pickup time for a specific pickup point in a group"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)
    
    try:
        from .models import GroupPickupPoint
        import json
        
        data = json.loads(request.body)
        pickup_point_id = data.get('pickup_point_id')
        pickup_time = data.get('pickup_time')
        
        if not pickup_point_id or not pickup_time:
            return JsonResponse({'success': False, 'message': 'Missing required fields'}, status=400)
        
        group = get_object_or_404(Group, pk=pk)
        pickup_point = get_object_or_404(PickupPoint, pk=pickup_point_id)
        
        # Get or create GroupPickupPoint entry
        gpp, created = GroupPickupPoint.objects.get_or_create(
            group=group,
            pickup_point=pickup_point
        )
        gpp.pickup_time = pickup_time
        gpp.save()
        
        # Check if all pickup times are now set
        bookings = group.bookings.all()
        unique_pickup_points = set()
        for booking in bookings:
            if booking.pickup_point:
                unique_pickup_points.add(booking.pickup_point.id)
        
        all_times_set = True
        for pp_id in unique_pickup_points:
            try:
                gpp = GroupPickupPoint.objects.get(group=group, pickup_point_id=pp_id)
                if not gpp.pickup_time:
                    all_times_set = False
                    break
            except GroupPickupPoint.DoesNotExist:
                all_times_set = False
                break
        
        return JsonResponse({
            'success': True,
            'message': 'Pickup time saved successfully',
            'all_times_set': all_times_set
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@user_passes_test(is_staff)
def group_send(request, pk):
    """Send group list to transportation company and mark availability as inactive"""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method')
        return redirect('group_detail', pk=pk)
    
    try:
        from .models import GroupPickupPoint, AvailabilityDays
        from django.core.mail import send_mail
        from django.conf import settings
        
        group = get_object_or_404(Group, pk=pk)
        
        # Check if all pickup times are set
        bookings = group.bookings.all()
        unique_pickup_points = set()
        for booking in bookings:
            if booking.pickup_point:
                unique_pickup_points.add(booking.pickup_point.id)
        
        if not unique_pickup_points:
            messages.error(request, 'No pickup points found in this group')
            return redirect('group_detail', pk=pk)
        
        # Verify all times are set
        missing_times = []
        for pp_id in unique_pickup_points:
            try:
                gpp = GroupPickupPoint.objects.get(group=group, pickup_point_id=pp_id)
                if not gpp.pickup_time:
                    pickup_point = PickupPoint.objects.get(pk=pp_id)
                    missing_times.append(pickup_point.name)
            except GroupPickupPoint.DoesNotExist:
                pickup_point = PickupPoint.objects.get(pk=pp_id)
                missing_times.append(pickup_point.name)
        
        if missing_times:
            messages.error(request, f'Please set pickup times for: {", ".join(missing_times)}')
            return redirect('group_detail', pk=pk)
        
        # Note: AvailabilityDays status is now updated via signals (see signals.py)
        # The signal will automatically mark dates as inactive when group.status = 'sent'
        # and reactivate them when a sent group is deleted
        
        # Mark group as sent
        group.status = 'sent'
        group.save()
        
        # Send email notifications
        notifications_sent = send_group_notifications(request, group)
        
        messages.success(
            request, 
            f'Group sent successfully! Notifications sent to provider and {notifications_sent} customer(s).'
        )
        return redirect('group_detail', pk=pk)
        
    except Exception as e:
        messages.error(request, f'Error sending group list: {str(e)}')
        return redirect('group_detail', pk=pk)

def send_group_notifications(request, group):
    """Send email notifications to provider and customers when group is sent."""
    from .models import GroupPickupPoint
    
    customers_notified = 0
    
    # 1. Send email to provider
    if group.provider and group.provider.email:
        try:
            builder = EmailBuilder()
            builder.h2(f"Hello {group.provider.name}!")
            builder.success(f"New Transport Group: {group.name}")
            builder.p(
                f"A new transport group has been assigned to you for {group.excursion.title}. "
                "Please review the details below."
            )
            
            # Group details
            builder.card("Group Information", {
                'Group Name': group.name,
                'Excursion': group.excursion.title,
                'Date': group.date.strftime('%B %d, %Y'),
                'Total Guests': group.total_guests,
                'Bus': group.bus.name if group.bus else 'Not assigned',
                'Guide': group.guide.name if group.guide else 'Not assigned'
            })
            
            # Pickup schedule
            pickup_points = GroupPickupPoint.objects.filter(group=group).select_related('pickup_point').order_by('pickup_time')
            if pickup_points.exists():
                pickup_data = []
                for gpp in pickup_points:
                    pickup_data.append((
                        gpp.pickup_point.name,
                        gpp.pickup_time.strftime('%I:%M %p') if gpp.pickup_time else 'Not set'
                    ))
                builder.card("Pickup Schedule", pickup_data, border_color="#4caf50")
            
            builder.button("View Group Details", request.build_absolute_uri(reverse('group_detail', kwargs={'pk': group.pk})))
            builder.p("Please confirm receipt and prepare accordingly.")
            builder.p("Best regards,<br>The iTrip Knossos Team")
            
            EmailService.send_dynamic_email(
                subject=f'[iTrip Knossos] New Transport Group - {group.name}',
                recipient_list=[group.provider.email],
                email_body=builder.build(),
                preview_text=f'New transport group for {group.excursion.title}',
                fail_silently=True
            )
            logger.info(f'Group notification sent to provider {group.provider.email}')
            
        except Exception as e:
            logger.error(f'Failed to send notification to provider for group #{group.pk}: {str(e)}')
    
    # 2. Send email to each customer with their specific pickup time
    bookings = group.bookings.all()
    for booking in bookings:
        try:
            customer_email = booking.guest_email or (booking.user.email if booking.user else None)
            customer_name = booking.guest_name or (booking.user.get_full_name() if booking.user else 'Guest')
            
            if not customer_email or not booking.pickup_point:
                continue
            
            # Get pickup time for this booking's pickup point
            pickup_time_str = 'To be confirmed'
            try:
                gpp = GroupPickupPoint.objects.get(group=group, pickup_point=booking.pickup_point)
                if gpp.pickup_time:
                    pickup_time_str = gpp.pickup_time.strftime('%I:%M %p')
            except GroupPickupPoint.DoesNotExist:
                pass
            
            # Build email
            builder = EmailBuilder()
            builder.h2(f"Hello {customer_name}!")
            builder.success("Your Pickup Time Has Been Confirmed!")
            builder.p("We're excited for your upcoming excursion! Your pickup details are ready.")
            
            # Pickup information - highlighted
            builder.card("Pickup Information", {
                'Excursion': group.excursion.title,
                'Date': group.date.strftime('%B %d, %Y'),
                'Pickup Time': f'⏰ {pickup_time_str}',
                'Pickup Location': booking.pickup_point.name,
                'Booking #': f'{booking.id}'
            }, border_color="#4caf50")
            
            # Important reminders
            builder.list_box("⚠️ Please Remember", [
                f"Be at {booking.pickup_point.name} by {pickup_time_str}",
                "Arrive 10 minutes early to ensure you don't miss the departure",
                "Bring your booking confirmation",
                "Wear comfortable clothing and shoes",
                "Don't forget water, sunscreen, and a camera!"
            ])
            
            # Booking URL
            booking_url = request.build_absolute_uri(reverse('booking_detail', kwargs={'pk': booking.pk}))
            if booking.access_token:
                booking_url += f'?token={booking.access_token}'
            
            builder.button("View Your Booking", booking_url)
            builder.p("If you have any questions, please don't hesitate to contact us.")
            builder.p("Best regards,<br>The iTrip Knossos Team")
            
            EmailService.send_dynamic_email(
                subject=f'[iTrip Knossos] Your Pickup Time - {group.excursion.title}',
                recipient_list=[customer_email],
                email_body=builder.build(),
                preview_text=f'Your pickup time is {pickup_time_str} at {booking.pickup_point.name}',
                fail_silently=True
            )
            customers_notified += 1
            logger.info(f'Pickup time notification sent to {customer_email} for booking #{booking.id}')
            
        except Exception as e:
            logger.error(f'Failed to send pickup notification to booking #{booking.id}: {str(e)}')
    
    return customers_notified

@user_passes_test(is_staff)
def debug_availability_days(request, excursion_id, date):
    """Debug endpoint to check AvailabilityDays status for a specific excursion and date"""
    from .models import AvailabilityDays, Excursion
    from datetime import datetime
    
    try:
        excursion = get_object_or_404(Excursion, pk=excursion_id)
        date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        
        # Get all AvailabilityDays for this excursion and date
        availability_days = AvailabilityDays.objects.filter(
            excursion_availability__excursion=excursion,
            date_day=date_obj
        ).select_related('excursion_availability')
        
        if not availability_days.exists():
            return JsonResponse({
                'found': False,
                'message': f'No AvailabilityDays found for {excursion.title} on {date}',
                'excursion': excursion.title,
                'date': date
            })
        
        results = []
        for ad in availability_days:
            results.append({
                'id': ad.id,
                'date': str(ad.date_day),
                'status': ad.status,
                'capacity': ad.capacity,
                'booked_guests': ad.booked_guests,
                'availability_id': ad.excursion_availability.id,
                'availability_range': f"{ad.excursion_availability.start_date} to {ad.excursion_availability.end_date}"
            })
        
        return JsonResponse({
            'found': True,
            'count': len(results),
            'excursion': excursion.title,
            'date': date,
            'availability_days': results
        })
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)

@user_passes_test(is_staff)
def get_bookings_for_group(request):
    """HTMX endpoint to fetch bookings filtered by excursion and date"""
    from .utils import TransportGroupService
    from django.template.loader import render_to_string
    
    excursion_id = request.GET.get('excursion') or request.GET.get('excursion_id')
    date = request.GET.get('date')
    group_id = request.GET.get('group_id')  # For editing existing groups
    
    if not excursion_id or not date:
        return render(request, 'main/groups/partials/_bookings_selection.html', {
            'pickup_groups': None,
            'no_bookings': True,
            'message': 'Please select both excursion and date'
        })
    
    try:
        excursion = Excursion.objects.get(id=excursion_id)
        
        # Get available bookings (excluding other groups, but not the current group)
        bookings = TransportGroupService.get_completed_bookings_for_grouping(
            excursion=excursion,
            date=date,
            exclude_group_id=group_id
        )
        
        # If editing a group, also include its existing bookings
        existing_booking_ids = []
        if group_id:
            try:
                group = Group.objects.get(pk=group_id)
                existing_bookings = group.bookings.all()
                existing_booking_ids = list(existing_bookings.values_list('id', flat=True))
                # Combine with available bookings (union to avoid duplicates)
                bookings = bookings | existing_bookings
            except Group.DoesNotExist:
                pass
        
        # Get pickup group summary
        pickup_summary = TransportGroupService.get_pickup_group_summary(bookings)
        
        if not pickup_summary:
            return render(request, 'main/groups/partials/_bookings_selection.html', {
                'pickup_groups': None,
                'no_bookings': True,
                'message': 'No available bookings found for the selected excursion and date',
                'existing_booking_ids': existing_booking_ids
            })
        
        return render(request, 'main/groups/partials/_bookings_selection.html', {
            'pickup_groups': pickup_summary,
            'no_bookings': False,
            'existing_booking_ids': existing_booking_ids
        })
        
    except Excursion.DoesNotExist:
        return render(request, 'main/groups/partials/_bookings_selection.html', {
            'pickup_groups': None,
            'no_bookings': True,
            'message': 'Excursion not found'
        })
    except Exception as e:
        return render(request, 'main/groups/partials/_bookings_selection.html', {
            'pickup_groups': None,
            'no_bookings': True,
            'message': f'Error: {str(e)}'
        })

@user_passes_test(is_staff)
def test_simple_pdf(request):
    """Test simple PDF generation"""
    from fpdf import FPDF
    from django.http import HttpResponse
    import sys
    
    try:
        # Create simplest possible PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, 'Test PDF', 0, 1, 'C')
        pdf.set_font('Arial', '', 12)
        pdf.cell(0, 10, 'This is a simple test.', 0, 1)
        pdf.cell(0, 10, 'If you can see this, fpdf2 works!', 0, 1)
        
        # Output
        pdf_bytes = pdf.output()
        
        # Debug info
        print(f"PDF generated successfully!", file=sys.stderr)
        print(f"Size: {len(pdf_bytes)} bytes", file=sys.stderr)
        print(f"Type: {type(pdf_bytes)}", file=sys.stderr)
        print(f"First 20 bytes: {pdf_bytes[:20]}", file=sys.stderr)
        
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="test.pdf"'
        return response
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return HttpResponse(f"Error: {e}", status=500)

@user_passes_test(is_staff)
def group_export_pdf(request, pk):
    from xhtml2pdf import pisa
    from io import BytesIO
    from collections import defaultdict
    from .models import GroupPickupPoint

    group = get_object_or_404(Group.objects.prefetch_related(
        'bookings',
        'bookings__pickup_point',
        'bookings__pickup_point__pickup_group',
        'bookings__voucher_id',
        'bookings__voucher_id__hotel',
        'pickup_times',
        'pickup_times__pickup_point'
    ), pk=pk)

    # Get pickup times dictionary
    pickup_times = {}
    for gpp in group.pickup_times.all():
        pickup_times[gpp.pickup_point.id] = gpp.pickup_time

    # Get bookings for the group
    bookings = group.bookings.all().order_by(
        'pickup_point__pickup_group__name',
        'pickup_point__name',
        'guest_name'
    )

    # Organize bookings by pickup group and pickup point with subtotals
    organized_data = []
    current_pickup_group = None
    pickup_group_data = None
    
    for booking in bookings:
        # Get pickup group - handle None pickup_point case
        if booking.pickup_point:
            pickup_group = booking.pickup_point.pickup_group
            pickup_point = booking.pickup_point
        else:
            pickup_group = None
            pickup_point = None
        
        # Check if we need to start a new pickup group
        if pickup_group != current_pickup_group:
            if pickup_group_data:
                organized_data.append(pickup_group_data)
            
            current_pickup_group = pickup_group
            pickup_group_data = {
                'pickup_group': pickup_group,
                'pickup_points': []
            }
        
        # Find or create pickup point in current group
        pickup_point_data = None
        for pp in pickup_group_data['pickup_points']:
            if pp['pickup_point'] == pickup_point:
                pickup_point_data = pp
                break
        
        if not pickup_point_data:
            # Get pickup time for this pickup point
            pickup_time = None
            if pickup_point:
                pickup_time = pickup_times.get(pickup_point.id)
            
            pickup_point_data = {
                'pickup_point': pickup_point,
                'pickup_time': pickup_time,
                'bookings': [],
                'subtotal': {'adults': 0, 'kids': 0, 'infants': 0, 'total': 0}
            }
            pickup_group_data['pickup_points'].append(pickup_point_data)
        
        # Add booking and update subtotal
        guest_total = (booking.total_adults or 0) + (booking.total_kids or 0) + (booking.total_infants or 0)
        pickup_point_data['bookings'].append(booking)
        pickup_point_data['subtotal']['adults'] += booking.total_adults or 0
        pickup_point_data['subtotal']['kids'] += booking.total_kids or 0
        pickup_point_data['subtotal']['infants'] += booking.total_infants or 0
        pickup_point_data['subtotal']['total'] += guest_total
    
    # Don't forget to add the last pickup group
    if pickup_group_data:
        organized_data.append(pickup_group_data)

    # HTML content to be converted.
    html_content = render_to_string('main/groups/group_pdf.html', {
        'group': group,
        'bookings': bookings,
        'organized_data': organized_data,
    })

    filename = f'transport_group_{group.name}_{group.date}.pdf'
    
    # Create a BytesIO buffer to receive PDF data
    buffer = BytesIO()
    
    # Convert HTML to PDF
    pisa_status = pisa.CreatePDF(html_content, dest=buffer)
    
    if pisa_status.err:
        return HttpResponse(f'PDF generation error: {pisa_status.err}', status=500)
    
    # Get the PDF content from buffer
    pdf_content = buffer.getvalue()
    buffer.close()
    
    # Create the HTTP response with PDF
    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


@user_passes_test(is_staff)
def group_export_csv(request, pk):
    import csv
    from io import StringIO
    from .models import GroupPickupPoint
    
    group = get_object_or_404(Group.objects.prefetch_related(
        'bookings',
        'bookings__pickup_point',
        'bookings__pickup_point__pickup_group',
        'bookings__voucher_id',
        'bookings__voucher_id__hotel',
        'pickup_times',
        'pickup_times__pickup_point'
    ), pk=pk)
    
    # Get pickup times dictionary
    pickup_times = {}
    for gpp in group.pickup_times.all():
        pickup_times[gpp.pickup_point.id] = gpp.pickup_time
    
    # Get bookings for the group
    bookings = group.bookings.all().order_by(
        'pickup_point__pickup_group__name',
        'pickup_point__name',
        'guest_name'
    )
    
    # Organize bookings by pickup group and pickup point with subtotals
    organized_data = []
    current_pickup_group = None
    pickup_group_data = None
    
    for booking in bookings:
        # Get pickup group - handle None pickup_point case
        if booking.pickup_point:
            pickup_group = booking.pickup_point.pickup_group
            pickup_point = booking.pickup_point
        else:
            pickup_group = None
            pickup_point = None
        
        # Check if we need to start a new pickup group
        if pickup_group != current_pickup_group:
            if pickup_group_data:
                organized_data.append(pickup_group_data)
            
            current_pickup_group = pickup_group
            pickup_group_data = {
                'pickup_group': pickup_group,
                'pickup_points': []
            }
        
        # Find or create pickup point in current group
        pickup_point_data = None
        for pp in pickup_group_data['pickup_points']:
            if pp['pickup_point'] == pickup_point:
                pickup_point_data = pp
                break
        
        if not pickup_point_data:
            # Get pickup time for this pickup point
            pickup_time = None
            if pickup_point:
                pickup_time = pickup_times.get(pickup_point.id)
            
            pickup_point_data = {
                'pickup_point': pickup_point,
                'pickup_time': pickup_time,
                'bookings': [],
                'subtotal': {'adults': 0, 'kids': 0, 'infants': 0, 'total': 0}
            }
            pickup_group_data['pickup_points'].append(pickup_point_data)
        
        # Add booking and update subtotal
        guest_total = (booking.total_adults or 0) + (booking.total_kids or 0) + (booking.total_infants or 0)
        pickup_point_data['bookings'].append(booking)
        pickup_point_data['subtotal']['adults'] += booking.total_adults or 0
        pickup_point_data['subtotal']['kids'] += booking.total_kids or 0
        pickup_point_data['subtotal']['infants'] += booking.total_infants or 0
        pickup_point_data['subtotal']['total'] += guest_total
    
    # Don't forget to add the last pickup group
    if pickup_group_data:
        organized_data.append(pickup_group_data)
    
    # Create CSV content
    output = StringIO()
    writer = csv.writer(output)
    
    # Header information
    writer.writerow(['TRANSPORT GROUP MANIFEST'])
    writer.writerow([])
    writer.writerow(['Excursion:', group.excursion.title])
    writer.writerow(['Group:', group.name])
    writer.writerow(['Date:', group.date.strftime('%A, %B %d, %Y')])
    writer.writerow(['Total Guests:', group.total_guests])
    writer.writerow(['Total Bookings:', bookings.count()])
    writer.writerow([])
    writer.writerow([])
    
    # Column headers
    headers = ['#', 'Pickup Group', 'Pickup Point', 'Pickup Time', 'Guest Name', 'Phone', 'Hotel/Location', 'Adults', 'Children', 'Infants', 'Total']
    writer.writerow(headers)
    
    # Data rows
    row_number = 1
    for pg_data in organized_data:
        pickup_group_name = pg_data['pickup_group'].name if pg_data['pickup_group'] else 'No Pickup Group'
        
        for pp_data in pg_data['pickup_points']:
            pickup_point_name = pp_data['pickup_point'].name if pp_data['pickup_point'] else 'No Pickup Point'
            pickup_time_str = pp_data['pickup_time'].strftime('%H:%M') if pp_data['pickup_time'] else 'Not Set'
            
            for booking in pp_data['bookings']:
                phone = ''
                if booking.voucher_id and booking.voucher_id.client_phone:
                    phone = booking.voucher_id.client_phone
                
                hotel = ''
                if booking.voucher_id and booking.voucher_id.hotel:
                    hotel = booking.voucher_id.hotel.name
                
                adults = booking.total_adults or 0
                kids = booking.total_kids or 0
                infants = booking.total_infants or 0
                total = adults + kids + infants
                
                writer.writerow([
                    row_number,
                    pickup_group_name,
                    pickup_point_name,
                    pickup_time_str,
                    booking.guest_name,
                    phone,
                    hotel,
                    adults,
                    kids,
                    infants,
                    total
                ])
                row_number += 1
            
            # Subtotal row
            writer.writerow([
                '',
                '',
                f'SUBTOTAL - {pickup_point_name}',
                '',
                f'{len(pp_data["bookings"])} booking(s)',
                '',
                '',
                pp_data['subtotal']['adults'],
                pp_data['subtotal']['kids'],
                pp_data['subtotal']['infants'],
                pp_data['subtotal']['total']
            ])
            writer.writerow([])  # Empty row for spacing
    
    # Grand total
    writer.writerow([])
    writer.writerow(['', '', 'GRAND TOTAL', f'{bookings.count()} bookings', '', '', '', '', '', group.total_guests])
    
    # Create response
    filename = f'transport_group_{group.name}_{group.date}.csv'
    response = HttpResponse(output.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

@user_passes_test(is_staff)
def buses_list(request):
    buses = Bus.objects.all().order_by('capacity')

    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        buses = buses.filter(
            Q(name__icontains=search_query) |
            Q(capacity__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(buses, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'main/admin/buses.html', {
        'buses': page_obj.object_list,
        'search_query': search_query,
        'page_obj': page_obj,
    })

@user_passes_test(is_staff)
def manage_buses(request):
    buses = Bus.objects.all().order_by('capacity')

    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        buses = buses.filter(
            Q(name__icontains=search_query) |
            Q(capacity__icontains=search_query)
        )

    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')
        
        if action_type == 'add_bus':
            name = request.POST.get('name', '').strip()
            capacity = request.POST.get('capacity', '').strip()
            if name and capacity:
                try:
                    Bus.objects.create(name=name, capacity=int(capacity))
                    messages.success(request, 'Bus added successfully.')
                except ValueError:
                    messages.error(request, 'Invalid capacity value.')
            else:
                messages.error(request, 'Please fill in all fields.')
            return redirect('manage_buses')

        elif action_type == 'edit_bus':
            bus = get_object_or_404(Bus, pk=item_id)
            name = request.POST.get('name', '').strip()
            capacity = request.POST.get('capacity', '').strip()
            if name and capacity:
                try:
                    bus.name = name
                    bus.capacity = int(capacity)
                    bus.save()
                    messages.success(request, 'Bus updated successfully.')
                except ValueError:
                    messages.error(request, 'Invalid capacity value.')
            else:
                messages.error(request, 'Please fill in all fields.')
            return redirect('manage_buses')

        elif action_type == 'delete_bus':
            bus = get_object_or_404(Bus, pk=item_id)
            bus_name = bus.name
            bus.delete()
            messages.success(request, f'Bus "{bus_name}" deleted successfully.')
            return redirect('manage_buses')

    # Pagination
    paginator = Paginator(buses, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'main/admin/buses.html', {
        'buses': page_obj.object_list,
        'search_query': search_query,
        'page_obj': page_obj,
    })

# ----- Category and Tag Management -----
@user_passes_test(is_staff)
def manage_categories_tags(request):
    """Combined view for managing both categories and tags with inline editing"""
    categories = Category.objects.all()
    tags = Tag.objects.all()

    # print('request.POST', request)
    
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')
      
        if action_type == 'add_category':
            name = request.POST.get('name', '').strip()
            if name:
                Category.objects.create(name=name)
                messages.success(request, 'Category added successfully.')
                return redirect('manage_categories_tags')
                
        elif action_type == 'edit_category':
            category = get_object_or_404(Category, pk=item_id)
            name = request.POST.get('name', '').strip()
            if name:
                category.name = name
                category.save()
                messages.success(request, 'Category updated successfully.')
                return redirect('manage_categories_tags')
                
        elif action_type == 'delete_category':
            category = get_object_or_404(Category, pk=item_id)
            category.delete()
            messages.success(request, 'Category deleted successfully.')
            return redirect('manage_categories_tags')
            
        elif action_type == 'add_tag':
            name = request.POST.get('name', '').strip()
            if name:
                Tag.objects.create(name=name)
                messages.success(request, 'Tag added successfully.')
                return redirect('manage_categories_tags')
                
        elif action_type == 'edit_tag':
            tag = get_object_or_404(Tag, pk=item_id)
            name = request.POST.get('name', '').strip()
            if name:
                tag.name = name
                tag.save()
                messages.success(request, 'Tag updated successfully.')
                return redirect('manage_categories_tags')
                
        elif action_type == 'delete_tag':
            tag = get_object_or_404(Tag, pk=item_id)
            tag.delete()
            messages.success(request, 'Tag deleted successfully.')
            return redirect('manage_categories_tags')
    
    return render(request, 'main/admin/categories_tags_management.html', {
        'categories': categories,
        'tags': tags,
    })

# ----- Providers and Representatives Views -----
@user_passes_test(is_staff)
def providers_list(request):
    providers = UserProfile.objects.filter(role='provider').order_by('name')
    regions = Region.objects.all()
    
    # Convert pickup groups to JSON-serializable format
    regions_json = json.dumps([{'id': region.id, 'name': region.name} for region in regions])

    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        providers = providers.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )

    paginator = Paginator(providers, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
        
    return render(request, 'main/admin/providers.html', {
        'providers': page_obj.object_list,
        'page_obj': page_obj,
        'regions_json': regions_json,
        'regions_data': regions,
    })

@user_passes_test(is_staff)
def manage_providers(request):
    regions = Region.objects.all()
    regions_json = json.dumps([{'id': region.id, 'name': region.name} for region in regions])

    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')
        
        if action_type == 'add_provider':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            region_id = request.POST.get('region', '').strip()
            
            if name and email:
                try:
                    region_instance = Region.objects.get(id=region_id)
                    # Create User first
                    user = User.objects.create_user(
                        username=email,
                        email=email,
                    )

                    # Create UserProfile
                    UserProfile.objects.create(
                        user=user,
                        name=name,
                        email=email,
                        phone=phone,
                        region=region_instance,
                        role='provider'
                    )
                    messages.success(request, 'Provider created successfully.')
                    return redirect('manage_providers')
                except Exception as e:
                    messages.error(request, f'Error creating provider: {str(e)}')
                    return redirect('manage_providers')

        elif action_type == 'edit_provider':
            provider = get_object_or_404(UserProfile, pk=item_id)
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            region_id = request.POST.get('region', '').strip()

            if name:
                try:
                    region_instance = Region.objects.get(id=region_id)
                    provider.name = name
                    provider.email = email
                    provider.phone = phone
                    provider.region = region_instance
                    provider.save()
                    messages.success(request, 'Provider updated successfully.')
                    return redirect('manage_providers')
                except Region.DoesNotExist:
                    messages.error(request, 'Invalid region selected.')

        elif action_type == 'delete_provider':
            provider = get_object_or_404(UserProfile, pk=item_id)
            # Delete the associated user as well
            provider.user.delete()
            messages.success(request, 'Provider deleted successfully.')
            return redirect('manage_providers')

    return render(request, 'main/admin/providers.html', {
        'providers': UserProfile.objects.filter(role='provider'),
        'regions_json': regions_json,
        'regions_data': regions,
    })

@user_passes_test(is_staff)
def reps_list(request):
    reps = UserProfile.objects.filter(role='representative')
        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        reps = reps.filter(
            Q(name__icontains=search_query)
        )

    return render(request, 'main/admin/reps.html', {
        'reps': reps,
    })

@user_passes_test(is_staff)

def manage_reps(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')
        
        if action_type == 'add_rep':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            password = request.POST.get('password', '').strip()
            
            if name and email and phone and password:
                username = email.split('@')[0] 
                base_username = username
                counter = 1

                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                # Create User first
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=name.split()[0],
                    last_name=' '.join(name.split()[1:]),
                )
                rep = UserProfile.objects.create(
                    user=user,
                    name=name,
                    email=email,
                    phone=phone,
                    role='representative'
                )
                messages.success(request, 'Representative created successfully.')
                return redirect('manage_reps')
            
        elif action_type == 'edit_rep':
            rep = get_object_or_404(UserProfile, pk=item_id)
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            status = request.POST.get('status', '').strip()
            password = request.POST.get('password', '').strip()
            
            if name:
                rep.name = name
                rep.email = email
                rep.phone = phone
                # Handle status update
                if status:
                    rep.status = status.lower()
                if password:
                    rep.user.set_password(password)
                    rep.user.save()
                rep.save()
                messages.success(request, 'Representative updated successfully.')
                return redirect('reps_list')

        elif action_type == 'delete_rep':
            rep = get_object_or_404(UserProfile, pk=item_id)    
            rep.user.delete()
            rep.delete()
            messages.success(request, 'Representative deleted successfully.')
            return redirect('manage_reps')

    return render(request, 'main/admin/reps.html', {
        'reps': UserProfile.objects.filter(role='representative'),
    })

@user_passes_test(is_staff)
def clients_list(request):
    clients = UserProfile.objects.filter(role='client').order_by('name')    
    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        clients = clients.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
    
    paginator = Paginator(clients, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'main/admin/clients.html', {
        'clients': page_obj.object_list,
        'page_obj': page_obj,
        'search_query': search_query,
    })

@user_passes_test(is_staff)
def manage_clients(request):
    # Get all clients
    clients = UserProfile.objects.filter(role='client').order_by('name')
    
    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        clients = clients.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
    
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')

        if action_type == 'add_client':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            password = request.POST.get('password', '').strip()
            
            if name and email and password:
                username = email.split('@')[0] 
                base_username = username
                counter = 1

                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                # Create User first
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                )
                if user:
                    # Create UserProfile
                    UserProfile.objects.create(
                        user=user,
                        name=name,
                        email=email,
                        phone=phone,
                        role='client'
                    )
                    messages.success(request, 'Client created successfully.')
                    return redirect('clients_list')
                else:
                    messages.error(request, 'Error creating user.')
                    return redirect('clients_list')
            
        elif action_type == 'edit_client':
            client = get_object_or_404(UserProfile, user__id=item_id, role='client')
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()   
            
            if name:
                client.name = name
                client.email = email
                client.phone = phone
                client.save()
                messages.success(request, 'Client updated successfully.')
    
        elif action_type == 'delete_client':
            user = get_object_or_404(User, pk=item_id)
            user.delete()
            messages.success(request, 'Client deleted successfully.')
            return redirect('clients_list')
        
        elif action_type == 'bulk_delete':
            selected_ids = request.POST.getlist('selected_clients')
            if selected_ids:
                clients_to_delete = UserProfile.objects.filter(id__in=selected_ids, role='client')
                count = clients_to_delete.count()
                clients_to_delete.delete()
                messages.success(request, f'{count} client(s) deleted successfully.')
            return redirect('clients_list')
        
    paginator = Paginator(clients, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'main/admin/clients.html', {
        'clients': page_obj.object_list,
        'page_obj': page_obj,
        'search_query': search_query,
    })

@user_passes_test(is_staff)
def agents_list(request):
    """List all agents with their latest active referral code"""
    agents = UserProfile.objects.filter(role='agent').order_by('name')
    
    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        agents = agents.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
    
    paginator = Paginator(agents, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'main/admin/agents_list.html', {
        'agents': page_obj.object_list,
        'page_obj': page_obj,
        'search_query': search_query,
    })

@user_passes_test(is_staff)
def manage_agents(request):
    """Manage agents CRUD operations"""
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')

        if action_type == 'add_agent':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            password = request.POST.get('password', '').strip()
            
            if name and email and password:
                try:
                    username = email.split('@')[0] 
                    base_username = username
                    counter = 1

                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}{counter}"
                        counter += 1
                    
                    # Create User first
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                    )
                    
                    if user:
                        # Create UserProfile for agent
                        UserProfile.objects.create(
                            user=user,
                            name=name,
                            email=email,
                            phone=phone,
                            role='agent'
                        )
                        messages.success(request, 'Agent created successfully.')
                        return redirect('agents_list')
                    else:
                        messages.error(request, 'Error creating user.')
                        return redirect('agents_list')
                except Exception as e:
                    messages.error(request, f'Error creating agent: {str(e)}')
                    return redirect('agents_list')
            else:
                messages.error(request, 'Please fill in all required fields.')
                return redirect('agents_list')
            
        elif action_type == 'edit_agent':
            agent = get_object_or_404(UserProfile, user__id=item_id, role='agent')
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            status = request.POST.get('status', '').strip()
            
            if name:
                agent.name = name
                agent.email = email
                agent.phone = phone
                # Handle status update (referral codes will be updated by signal)
                if status:
                    agent.status = status.lower()
                agent.save()
                messages.success(request, 'Agent updated successfully.')
            return redirect('agents_list')
    
        elif action_type == 'delete_agent':
            user = get_object_or_404(User, pk=item_id)
            user.delete()
            messages.success(request, 'Agent deleted successfully.')
            return redirect('agents_list')
        
        elif action_type == 'bulk_delete':
            selected_ids = request.POST.getlist('selected_agents')
            if selected_ids:
                agents_to_delete = UserProfile.objects.filter(id__in=selected_ids, role='agent')
                count = agents_to_delete.count()
                # Delete associated users
                for agent in agents_to_delete:
                    if agent.user:
                        agent.user.delete()
                messages.success(request, f'{count} agent(s) deleted successfully.')
            return redirect('agents_list')
        
    return redirect('agents_list')
    
@user_passes_test(is_staff)
def guides_list(request):
    guides = UserProfile.objects.filter(role='guide')

        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        guides = guides.filter(
            Q(name__icontains=search_query)
        )

    return render(request, 'main/admin/guides.html', {
        'guides': guides,
    })

@user_passes_test(is_staff)
def manage_guides(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')
        
        if action_type == 'add_guide':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            
            if name and email:
                # Create User first
                user = User.objects.create_user(
                    username=email,
                    email=email,
                )
                # Create UserProfile    
                UserProfile.objects.create(
                    user=user,
                    name=name,
                    email=email,
                    phone=phone,
                    role='guide'
                )
                messages.success(request, 'Guide created successfully.')
                return redirect('guides_list')
            
        elif action_type == 'edit_guide':
            guide = get_object_or_404(UserProfile, pk=item_id)
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            status = request.POST.get('status', '').strip()

            if name:
                guide.name = name
                guide.email = email
                guide.phone = phone
                # Handle status update
                if status:
                    guide.status = status.lower()
                guide.save()
                messages.success(request, 'Guide updated successfully.')
                return redirect('guides_list')

        elif action_type == 'delete_guide':
            guide = get_object_or_404(UserProfile, pk=item_id)
            guide.delete()
            messages.success(request, 'Guide deleted successfully.')
            return redirect('guides_list')

    return render(request, 'main/admin/guides.html', {
        'guides': UserProfile.objects.filter(role='guide'),
    })

# ----- Availability Views -----
@user_passes_test(is_staff)
def availability_list(request):
    availabilities = ExcursionAvailability.objects.all().order_by('status', 'excursion__title')
    excursions = Excursion.objects.all().order_by('title')

        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        availabilities = availabilities.filter(
            Q(excursion__title__icontains=search_query)
        )

    paginator = Paginator(availabilities, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'main/availabilities/availabilities_list.html', {
        'availabilities': availabilities,
        'excursions': excursions,
        'page_obj': page_obj,
    })

@user_passes_test(is_staff)
def admin_reservations(request):
    reservations = Reservation.objects.all().order_by('check_in')

    client_users = User.objects.filter(username__icontains='client_')
    updated_clients = UserProfile.objects.filter(role='client', user__in=client_users)

    print('updated_clients: ' + str(updated_clients))

    try:
        # Handle search
        search_query = request.GET.get('search', '').strip()
        if search_query:
            reservations = reservations.filter(
                Q(client_name__icontains=search_query) |
                Q(client_email__icontains=search_query) |
                Q(client_phone__icontains=search_query) |
                Q(voucher_id__icontains=search_query)
            )

        paginator = Paginator(reservations, 15)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        return render(request, 'main/admin/admin_reservations.html', {
            'reservations': reservations,
            'page_obj': page_obj,
            'updated_clients': updated_clients,
        })   
    except Reservation.DoesNotExist:
        messages.error(request, 'No reservations found')
        return redirect('admin_reservations')
    except Exception as e:
        messages.error(request, f'Error fetching reservations: {str(e)}')
        return redirect('admin_reservations')

@user_passes_test(is_staff)
def bookings_list(request):

    search_query = request.GET.get('search', '')
    bookings = Booking.objects.all().order_by('-id')
    
    # Apply search filter if search query is provided
    if search_query:
        bookings = bookings.filter(
            Q(guest_name__icontains=search_query) |
            Q(guest_email__icontains=search_query) |
            Q(payment_status__icontains=search_query) |
            Q(excursion_availability__excursion__title__icontains=search_query)
        )    

    paginator = Paginator(bookings, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    
    return render(request, 'main/bookings/bookings_list.html', {
        'bookings': page_obj.object_list,
        'search_query': search_query,
        'page_obj': page_obj,
    })
# ?? CONFIRM IF NEEDED
def filter_bookings(request):
    status = request.GET.get('status')

    bookings = Booking.objects.all().order_by('-created_at')

    if status:
        bookings = bookings.filter(payment_status=status)
    
    return render(request, 'main/filters/filter_bookings.html', {
        'bookings': bookings,
    })

@user_passes_test(is_staff)
def booking_edit(request, pk):
    try:
        booking = get_object_or_404(Booking, pk=pk)
        
        if request.method == 'POST':
            form = BookingForm(request.POST, instance=booking, user=request.user)
            
            # Debug: Print form data and errors
            print(f"Form data: {request.POST}")
            print(f"Form fields: {list(form.fields.keys())}")
            print(f"Form is valid: {form.is_valid()}")
            if not form.is_valid():
                print(f"Form errors: {form.errors}")
                print(f"Form non-field errors: {form.non_field_errors()}")
            
            if form.is_valid():
                try:
                    with transaction.atomic():
                        booking = form.save()
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': 'Booking updated successfully.',
                            'redirect_url': reverse('booking_detail', kwargs={'pk': pk})
                        })
                    
                    messages.success(request, 'Booking updated successfully.')
                    return redirect('booking_detail', pk=pk)
                except Exception as e:
                    print(f"Error saving booking: {str(e)}")
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'message': f'Error updating booking: {str(e)}'
                        })
                    messages.error(request, f'Error updating booking: {str(e)}')
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    # Format form errors for display
                    error_messages = []
                    for field, errors in form.errors.items():
                        field_name = form.fields[field].label if field in form.fields else field
                        for error in errors:
                            error_messages.append(f"{field_name}: {error}")
                    
                    return JsonResponse({
                        'success': False,
                        'message': 'Please correct the following errors:',
                        'errors': error_messages
                    })
                messages.error(request, 'Please correct the errors below.')
        else:
            form = BookingForm(instance=booking, user=request.user)
        
        return render(request, 'main/bookings/booking_edit.html', {
            'booking': booking,
            'form': form,
        })
    except Exception as e:
        print(f"Unexpected error in booking_edit: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': f'An unexpected error occurred: {str(e)}'
            })
        messages.error(request, f'An unexpected error occurred: {str(e)}')
        return redirect('bookings_list')

@user_passes_test(is_staff)
def manage_reservations(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')

        if action_type == 'add_reservation':
            reservation_id = request.POST.get('voucher_id', '').strip()

            if reservation_id is not None:
                booking_data = get_reservation(int(reservation_id))
                print('booking_data from manage reservations: ' + str(booking_data))
                if booking_data.get('ErrorMessage') is None:
                    reservation_obj, response_data = create_reservation(booking_data)
                    print('reservation_response from manage reservations: ' + str((reservation_obj, response_data)))
                    if response_data and response_data.get('message') == "Reservation found.":
                        messages.error(request, f'Reservation {reservation_id} already exists.')
                        return redirect('admin_reservations')
                    else:
                        messages.success(request, f'Reservation {reservation_id} created successfully.')
                        return redirect('admin_reservations')
                else:
                    messages.error(request, f'No reservation found with ID: {reservation_id}.')
                    return redirect('admin_reservations')   

            else:
                messages.error(request, 'Please fill in all fields')
                return redirect('admin_reservations')
            
        elif action_type == 'edit_reservation':
            reservation = get_object_or_404(Reservation, pk=item_id)

            current_departure_time = reservation.departure_time
            
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            departure_time = request.POST.get('departure_time', '').strip()

            if email and phone and departure_time:
                reservation.client_email = email
                reservation.client_phone = phone
                reservation.departure_time = departure_time

                if current_departure_time != departure_time:
                    # we need to inform the client 
                    # def inform_client(reservation_id, email, phone, new_departure_time)
                    print('departure_time changed')

                reservation.save()
                messages.success(request, 'Reservation updated successfully.')
                return redirect('admin_reservations')
            else:
                messages.error(request, 'Please fill in all fields')
                return redirect('admin_reservations')
            
        elif action_type == 'delete_reservation':
            reservation = get_object_or_404(Reservation, pk=item_id)
            reservation.delete()
            messages.success(request, 'Reservation deleted successfully.')
            return redirect('admin_reservations')
        
    return render(request, 'main/admin/admin_reservations.html', {
        'reservations': Reservation.objects.filter(status='active').order_by('check_in'),
        'page_obj': page_obj,
    })

def check_excursion_pickup_groups(request):
    """Legacy endpoint - can be removed if not used elsewhere"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            excursion_id = data.get('excursion_id')
            
            pickup_groups = ExcursionAvailability.objects.filter(excursion=excursion_id).values('pickup_groups').distinct()

            return JsonResponse({'pickup_groups': list(pickup_groups)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

def get_available_regions(request):
    """
    API endpoint to get available regions for an excursion and date range.
    Uses AvailabilityValidationService for business logic.
    """
    if request.method == 'POST':
        try:
            from .utils import AvailabilityValidationService
            from .models import Region
            
            data = json.loads(request.body)
            excursion_id = data.get('excursion_id')
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            current_availability_id = data.get('current_availability_id')
            
            if not excursion_id or not start_date or not end_date:
                return JsonResponse({'error': 'Missing required parameters'}, status=400)
            
            # Use service to get conflicting regions
            used_region_ids = AvailabilityValidationService.get_conflicting_regions(
                excursion_id=excursion_id,
                start_date=start_date,
                end_date=end_date,
                current_availability_id=current_availability_id
            )
            
            # Get all regions and mark disabled ones
            all_regions = Region.objects.all().order_by('name')
            regions_data = [
                {
                    'id': region.id,
                    'name': region.name,
                    'disabled': region.id in used_region_ids
                }
                for region in all_regions
            ]
            
            return JsonResponse({'regions': regions_data})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@user_passes_test(is_staff)
def availability_form(request, pk=None):
    """
    Create or update availability.
    Uses Django's form validation system with service classes for business logic.
    """
    availability = None
    if pk:
        availability = get_object_or_404(ExcursionAvailability, pk=pk)
    
    if request.method == 'POST':
        form = ExcursionAvailabilityForm(request.POST, instance=availability)
        
        # Form validation handles all business logic via clean() method
        if form.is_valid():
            try:
                # Get M2M field data from POST
                selected_weekday_ids = request.POST.getlist('weekdays')
                pickup_point_ids = request.POST.getlist('pickup_points')
                region_ids = request.POST.getlist('regions')

                # Save the instance (without M2M relationships yet)
                availability = form.save(commit=False)
                
                # Ensure excursion is set
                if not availability.excursion:
                    excursion_pk = request.POST.get('excursion')
                    if not excursion_pk:
                        raise ValueError("Excursion ID is required")
                    availability.excursion = get_object_or_404(Excursion, pk=excursion_pk)
                
                # Save to get an ID before setting M2M relationships
                availability.save()
                
                # Set M2M relationships
                availability.weekdays.set(selected_weekday_ids)
                availability.pickup_points.set(pickup_point_ids)
                availability.regions.set(region_ids)
                
                # Activate excursion if it's not already active
                if availability.excursion.status != 'active':
                    availability.excursion.status = 'active'
                    availability.excursion.save()

                # Regenerate AvailabilityDays entries
                AvailabilityDays.objects.filter(excursion_availability=availability).delete()
                
                # Get the selected weekdays and create days
                selected_weekdays = availability.weekdays.all()
                weekday_mapping = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}
                weekday_numbers = [weekday_mapping[w.code] for w in selected_weekdays if w.code in weekday_mapping]
                
                # Create AvailabilityDays for each matching day in date range
                current_date = availability.start_date
                while current_date <= availability.end_date:
                    if current_date.weekday() in weekday_numbers:
                        AvailabilityDays.objects.create(
                            excursion_availability=availability,
                            date_day=current_date,
                            capacity=availability.max_guests
                        )
                    current_date += timedelta(days=1)

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': f'Availability {"updated" if pk else "created"} successfully.',
                        'redirect_url': reverse('availability_detail', kwargs={'pk': availability.pk})
                    })
                
                messages.success(request, f'Availability {"updated" if pk else "created"} successfully.')
                return redirect('availability_detail', pk=availability.pk)

            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': str(e)
                    })
                messages.error(request, f'Error {"updating" if pk else "creating"} availability: {str(e)}')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # Format form errors for display
                error_messages = []
                for field, errors in form.errors.items():
                    field_name = form.fields[field].label if field in form.fields else field
                    for error in errors:
                        error_messages.append(f"{field_name}: {error}")
                
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the following errors:',
                    'errors': error_messages
                })
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ExcursionAvailabilityForm(instance=availability)
    
    return render(request, 'main/availabilities/availability_form.html', {
        'form': form,
        'availability': availability,
        'is_update': bool(pk),
    })

@user_passes_test(is_staff)
def availability_detail(request, pk):
    availability = get_object_or_404(ExcursionAvailability, pk=pk)
    pickup_points = availability.pickup_points.all().select_related('pickup_group').order_by('pickup_group__priority', 'priority', 'name')
    regions = availability.regions.all().order_by('name')
    return render(request, 'main/availabilities/availability_detail.html', {
        'availability': availability,
        'pickup_points': pickup_points,
        'regions': regions,
    })

@user_passes_test(is_staff)
def availability_delete(request, pk):
    availability = get_object_or_404(ExcursionAvailability, pk=pk)
    if request.method == 'POST':
        excursion = availability.excursion

        # Delete all AvailabilityDays entries for this availability
        # AvailabilityDays.objects.filter(excursion=excursion).delete()
        availability.delete()
        
        # Check if there are any remaining availabilities for this excursion
        remaining_availabilities = ExcursionAvailability.objects.filter(excursion=excursion).exists()
        if not remaining_availabilities:
            excursion.status = 'inactive'
            excursion.save()
            
        messages.success(request, 'Availability deleted successfully.')
        return redirect('availability_list')
    else:
        return redirect('availability_list')
    
@user_passes_test(is_staff)
def pickup_points_list(request):
    pickup_points = PickupPoint.objects.all().select_related('pickup_group').order_by('-pickup_group__priority', 'name')
    pickup_groups = PickupGroup.objects.all().order_by('priority')
    
    # Convert pickup groups to JSON-serializable format
    pickup_groups_json = json.dumps([{'id': group.id, 'name': group.name, 'priority': group.priority} for group in pickup_groups])
    
    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        pickup_points = pickup_points.filter(
            Q(name__icontains=search_query) |
            # Q(address__icontains=search_query) |
            Q(pickup_group__name__icontains=search_query)
        )
    
    paginator = Paginator(pickup_points, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'pickup_points': page_obj.object_list,
        'pickup_groups': pickup_groups,
        'pickup_groups_json': pickup_groups_json,
        'page_obj': page_obj,
    }
    return render(request, 'main/admin/pickup_points_list.html', context)

@user_passes_test(is_staff)
def manage_pickup_points(request):
    if request.method != 'POST':
        return redirect('pickup_points_list')
    
    action_type = request.POST.get('action_type')
    
    try:
        if action_type == 'add_point':
            name = request.POST.get('name', '').strip()
            # address = request.POST.get('address', '').strip()
            priority = request.POST.get('priority', '').strip()
            pickup_group_id = request.POST.get('pickup_group')
            google_maps_link = request.POST.get('google_maps_link', '').strip()

            if not all([name, pickup_group_id, priority]):
                messages.error(request, 'Please fill in all required fields')
                return redirect('pickup_points_list')
            
            try:
                pickup_group = PickupGroup.objects.get(id=pickup_group_id)
            except PickupGroup.DoesNotExist:
                messages.error(request, 'Invalid pickup group selected')
                return redirect('pickup_points_list')
            
            PickupPoint.objects.create(
                name=name,
                priority=priority,
                pickup_group=pickup_group,
                google_maps_link=google_maps_link if google_maps_link else None,
            )
            messages.success(request, 'Pickup point added successfully')
            
        elif action_type == 'edit_point':
            item_id = request.POST.get('item_id')
            name = request.POST.get('name', '').strip()
            # address = request.POST.get('address', '').strip()
            priority = request.POST.get('priority', '').strip()
            pickup_group_id = request.POST.get('pickup_group')
            google_maps_link = request.POST.get('google_maps_link', '').strip()

            if not all([item_id, name, pickup_group_id, priority]):
                messages.error(request, 'Please fill in all required fields')
                return redirect('pickup_points_list')
            
            try:
                point = PickupPoint.objects.get(id=item_id)
                pickup_group = PickupGroup.objects.get(id=pickup_group_id)
            except (PickupPoint.DoesNotExist, PickupGroup.DoesNotExist):
                messages.error(request, 'Invalid pickup point or group selected')
                return redirect('pickup_points_list')
            
            point.name = name
            point.priority = priority
            point.pickup_group = pickup_group
            point.google_maps_link = google_maps_link if google_maps_link else None
            point.save()
            messages.success(request, 'Pickup point updated successfully')
            
        elif action_type == 'delete_point':
            item_id = request.POST.get('item_id')
            if not item_id:
                messages.error(request, 'Invalid pickup point selected')
                return redirect('pickup_points_list')
            
            try:    
                point = PickupPoint.objects.get(id=item_id)
                point.delete()
                messages.success(request, 'Pickup point deleted successfully')
            except PickupPoint.DoesNotExist:
                messages.error(request, 'Pickup point not found')
                return redirect('pickup_points_list')
            
        else:
            messages.error(request, 'Invalid action type')
            
    except Exception as e:
        messages.error(request, f'Error managing pickup point: {str(e)}')
    
    return redirect('pickup_points_list')

@user_passes_test(is_staff)
def staff_list(request):
    staff = UserProfile.objects.filter(role='admin') 
        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        staff = staff.filter(
            Q(name__icontains=search_query)
        )

    paginator = Paginator(staff, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'main/admin/staff.html', {
        'staffs': page_obj.object_list,
        'page_obj': page_obj,
    })

@user_passes_test(is_staff) 
def manage_staff(request):
    
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')

        if action_type == 'add_staff':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            password = request.POST.get('password', '').strip()
            is_superadmin = request.POST.get('is_superadmin', '').strip()
            is_superadmin = True if is_superadmin == 'true' else False


            if name and email and password:
                username = email.split('@')[0] 
                base_username = username
                counter = 1

                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                # Create User first
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    first_name=name.split()[0],
                    last_name=' '.join(name.split()[1:]),
                    email=email,
                    is_staff=True,
                )   
                # Create UserProfile
                UserProfile.objects.create(
                    user=user,
                    name=name,
                    email=email,
                    phone=phone,
                    role='admin',
                    is_superadmin=is_superadmin,
                )   
                messages.success(request, 'Staff member created successfully.')
                return redirect('staff_list')
            
        elif action_type == 'edit_staff':
            staff_profile = get_object_or_404(UserProfile, pk=item_id)
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            # role = request.POST.get('role', '').strip()
            new_password = request.POST.get('password', '').strip()
            is_superadmin = request.POST.get('is_superadmin', '').strip()
            is_superadmin = True if is_superadmin == 'true' else False

            if name:
                staff_profile.name = name
                staff_profile.email = email
                staff_profile.phone = phone
                staff_profile.role = "admin"
                if new_password:
                    staff_profile.user.set_password(new_password)
                    staff_profile.user.save()
                staff_profile.is_superadmin = is_superadmin
                staff_profile.save()
                messages.success(request, 'Staff member updated successfully.')
                return redirect('staff_list')

        elif action_type == 'delete_staff':
            staff_profile = get_object_or_404(UserProfile, pk=item_id)
            # Delete the user, which will cascade delete the UserProfile
            staff_profile.user.delete()
            messages.success(request, 'Staff member deleted successfully.')
            return redirect('staff_list')
    
    # Get all staff profiles (UserProfile objects with role='admin')
    staff = UserProfile.objects.filter(role='admin', user__is_staff=True).select_related('user')
    
    paginator = Paginator(staff, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)


    return render(request, 'main/admin/staff.html', {
        'staffs': staff,
        'page_obj': page_obj,
    })

@user_passes_test(is_staff)
def admin_excursions(request):
    excursions = Excursion.objects.all().order_by('status', 'title')

        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        excursions = excursions.filter(
            Q(title__icontains=search_query)
        )

    paginator = Paginator(excursions, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)


    return render(request, 'main/admin/admin_excursions.html', {
        'excursions': excursions,
        'page_obj': page_obj,
    })

@user_passes_test(is_staff)
def excursion_analytics(request):
    """Display excursion analytics with bookings and capacity per date."""
    from .forms import ExcursionAnalyticsForm
    
    analytics_data = None
    form = ExcursionAnalyticsForm(request.GET or None)
    
    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date']
        
        # Get analytics data from service
        analytics_data = ExcursionAnalyticsService.get_analytics_data(start_date, end_date)
    
    return render(request, 'main/admin/excursion_analytics.html', {
        'form': form,
        'analytics_data': analytics_data,
    })

@user_passes_test(is_staff)
def revenue_dashboard(request):
    """Display comprehensive revenue analytics dashboard."""
    from .forms import ExcursionAnalyticsForm  # Reuse the same date range form
    
    revenue_data = None
    form = ExcursionAnalyticsForm(request.GET or None)
    
    if form.is_valid():
        start_date = form.cleaned_data['start_date']
        end_date = form.cleaned_data['end_date']
        
        # Get revenue data from service
        revenue_data = RevenueAnalyticsService.get_revenue_data(start_date, end_date)
    
    return render(request, 'main/admin/revenue_dashboard.html', {
        'form': form,
        'revenue_data': revenue_data,
    })

@user_passes_test(is_staff)
def hotel_list(request):
    hotels = Hotel.objects.all()
    pickup_groups = PickupGroup.objects.all()
    pickup_groups_json = json.dumps([{'id': pickup_group.id, 'name': pickup_group.name} for pickup_group in pickup_groups])

    search_query = request.GET.get('search', '').strip()
    if search_query:
        hotels = hotels.filter(
            Q(name__icontains=search_query) |
            Q(address__icontains=search_query) 
        )

    # Create paginator with filtered results
    paginator = Paginator(hotels, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'main/admin/hotel_list.html', {
        'hotels': page_obj.object_list,
        'pickup_groups': pickup_groups,
        'pickup_groups_json': pickup_groups_json,
        'page_obj': page_obj,
    })

@user_passes_test(is_staff)
def manage_hotels(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')

        try:
            if action_type == 'add_hotel':
                name = request.POST.get('name', '').strip()
                address = request.POST.get('address', '').strip()
                phone = request.POST.get('phone', '').strip()
                email = request.POST.get('email', '').strip()
                pickup_group_id = request.POST.get('pickup_group', '').strip()

                # Validate phone number
                phone_regex = re.compile(r'^[+]?[0-9\s\-()]{8,20}$')
                if not phone_regex.match(phone):
                    messages.error(request, 'Please enter a valid phone number (8-20 digits, may include +, spaces, hyphens, and parentheses)')
                    return redirect('hotel_list')

                # Validate email
                try:
                    validate_email(email)
                except ValidationError:
                    messages.error(request, 'Please enter a valid email address')
                    return redirect('hotel_list')

                if name and address and pickup_group_id:
                    try:
                        pickup_group = get_object_or_404(PickupGroup, id=pickup_group_id)
                        Hotel.objects.create(
                            name=name,
                            address=address,
                            phone_number=phone,
                            email=email,
                            pickup_group=pickup_group,
                        )
                        messages.success(request, 'Hotel created successfully.')
                        return redirect('hotel_list')
                    except Exception as e:
                        messages.error(request, f'Error creating hotel: {str(e)}')
                        return redirect('hotel_list')
            
            elif action_type == 'edit_hotel':
                hotel = get_object_or_404(Hotel, pk=item_id)
                name = request.POST.get('name', '').strip()
                address = request.POST.get('address', '').strip()
                phone = request.POST.get('phone', '').strip()
                email = request.POST.get('email', '').strip()
                pickup_group_id = request.POST.get('pickup_group', '').strip()

                # Validate phone number
                phone_regex = re.compile(r'^[+]?[0-9\s\-()]{8,20}$')
                if not phone_regex.match(phone):
                    messages.error(request, 'Please enter a valid phone number (8-20 digits, may include +, spaces, hyphens, and parentheses)')
                    return redirect('hotel_list')

                # Validate email
                try:
                    validate_email(email)
                except ValidationError:
                    messages.error(request, 'Please enter a valid email address')
                    return redirect('hotel_list')

                if name:    
                    hotel.name = name
                    hotel.address = address
                    hotel.phone_number = phone
                    hotel.email = email
                    if pickup_group_id:
                        pickup_group = get_object_or_404(PickupGroup, id=pickup_group_id)
                        hotel.pickup_group = pickup_group
                    hotel.save()
                    messages.success(request, 'Hotel updated successfully.')
                    return redirect('hotel_list')
                
            elif action_type == 'delete_hotel':
                hotel = get_object_or_404(Hotel, pk=item_id)
                hotel.delete()
                messages.success(request, 'Hotel deleted successfully.')
                return redirect('hotel_list')
            
        except Exception as e:
            messages.error(request, f'Error {"updating" if item_id else "creating"} hotel: {str(e)}')
            return redirect('hotel_list')
        
    return render(request, 'main/admin/hotel_list.html', {
        'hotels': Hotel.objects.all(),
    })

def region_list(request):
    regions = Region.objects.all()
    return render(request, 'main/admin/region_list.html', {
        'regions': regions,
    })

@user_passes_test(is_staff)
def manage_regions(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')

        print(action_type, item_id)

        if action_type == 'add_region':
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip()

            if name and code:
                Region.objects.create(name=name, slug=code)
                messages.success(request, 'Region created successfully.')
                return redirect('region_list')
            
        elif action_type == 'edit_region':
            region = get_object_or_404(Region, pk=item_id)
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip()

            if name and code:
                region.name = name
                region.slug = code
                region.save()
                messages.success(request, 'Region updated successfully.')
                return redirect('region_list')
            
        elif action_type == 'delete_region':
            region = get_object_or_404(Region, pk=item_id)
            region.delete()
            messages.success(request, 'Region deleted successfully.')
            return redirect('region_list')
        
    return render(request, 'main/admin/region_list.html', {
        'regions': Region.objects.all(),
    })
                     
@user_passes_test(is_staff)
def pickup_groups_list(request):
    pickup_groups = PickupGroup.objects.all().order_by('priority')
    regions = Region.objects.all()
    # Convert regions to JSON-serializable format
    regions_json = json.dumps([{'id': region.id, 'name': region.name} for region in regions])

    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        pickup_groups = pickup_groups.filter(
            Q(name__icontains=search_query) |
            Q(region__name__icontains=search_query)
        )


    return render(request, 'main/admin/pickup_groups_list.html', {
        'pickup_groups': pickup_groups,
        'regions': regions,
        'regions_json': regions_json,
    })

@user_passes_test(is_staff)
def manage_pickup_groups(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')

        try:
            if action_type == 'add_group':
                name = request.POST.get('name', '').strip()
                code = request.POST.get('code', '').strip()
                priority = request.POST.get('priority', '').strip()

                if name and code and priority:
                    try:
                        PickupGroup.objects.create(
                            name=name,
                            code=code,
                            priority=priority,
                        )
                        messages.success(request, 'Pickup group created successfully.')
                        return redirect('pickup_groups_list')
                    except Exception as e:
                        messages.error(request, f'Error creating pickup group: {str(e)}')
                        return redirect('pickup_groups_list')
            
            elif action_type == 'edit_group':
                group = get_object_or_404(PickupGroup, pk=item_id)
                name = request.POST.get('name', '').strip()
                code = request.POST.get('code', '').strip()
                priority = request.POST.get('priority', '').strip()
                if name:    
                    group.name = name
                    if code:
                        group.code = code
                    if priority:
                        group.priority = priority
                    group.save()
                    messages.success(request, 'Pickup group updated successfully.')
                    return redirect('pickup_groups_list')
                
            elif action_type == 'delete_group':
                group = get_object_or_404(PickupGroup, pk=item_id)
                group.delete()
                messages.success(request, 'Pickup group deleted successfully.')
                return redirect('pickup_groups_list')
            
        except Exception as e:
            messages.error(request, f'Error {"updating" if item_id else "creating"} pickup group: {str(e)}')
            return redirect('pickup_groups_list')
        
    return render(request, 'main/admin/pickup_groups_list.html', {
        'pickup_groups': PickupGroup.objects.all(),
    })

