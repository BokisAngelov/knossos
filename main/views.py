from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import Paginator
from datetime import date, datetime, time, timedelta
from django.contrib.auth.models import User
from django.http import JsonResponse, Http404, HttpResponse
from django.utils.text import slugify
from .models import (
    Excursion, ExcursionImage, ExcursionAvailability,
    Booking, Feedback, UserProfile, Region, 
        Group, Category, Tag, PickupPoint, AvailabilityDays, DayOfWeek, Hotel, PickupGroup, PickupGroupAvailability, Reservation
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
from django.db.models import Q, Sum, Count
from django.apps import apps
from .cyber_api import get_groups, get_hotels, get_pickup_points, get_excursions, get_excursion_description, get_providers, get_excursion_availabilities, get_reservation
from .utils import FeedbackService, BookingService, ExcursionService, create_reservation

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
            secure=True,
            httponly=False,
            samesite='None'
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

def check_voucher(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        return_data = {}
        voucher_code = data.get('voucher_code')
        if voucher_code:
            voucher = Reservation.objects.filter(voucher_id=voucher_code).first()
            if voucher:
                return_data = {
                    'client_name': voucher.client_name,
                    'pickup_group_id': voucher.pickup_group.id,
                    'pickup_point_id': voucher.pickup_point.id,
                    'client_email': voucher.client_email,
                }
                return JsonResponse({'success': True, 'message': 'Voucher found in database.', 'return_data': return_data})
            else:
                return JsonResponse({'success': False, 'message': 'Voucher not found in database.', 'return_data': return_data})
        else:
            return JsonResponse({'success': False, 'message': 'Voucher code is required.', 'return_data': return_data})
    else:
        return JsonResponse({'success': False, 'message': 'Invalid request method.'})
    
def retrive_voucher(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            action = data.get('action')
            
            if action == 'clear':
                response = JsonResponse({
                    'success': True,
                    'message': 'Voucher cleared successfully.'
                })
                response.delete_cookie('voucher_code')
                response.delete_cookie('pickup_group')
                response.delete_cookie('pickup_point')
                return response
                
            voucher_code = data.get('voucher_code')

            # print('voucher_code from ajax: ' + str(voucher_code))
            # vouchers = Reservation.objects.all()
            # print('vouchers: ' + str(vouchers))
            # for voucher in vouchers:
            #     print('voucher in for: ' + str(voucher.client_name) + ' id: ' + str(voucher.voucher_id))
                
            voucher = Reservation.objects.filter(voucher_id=voucher_code).first()
            
            if voucher:
                # pickup_group_id = voucher.pickup_group
                # print('voucher: ' + str(voucher.client_name) + ' ' + str(voucher.voucher_id))
                # Create response with cookie
                response = JsonResponse({
                    'success': True,
                    'message': 'Voucher is valid.',
                    'return_data': {
                        'client_name': voucher.client_name,
                        'pickup_group_id': voucher.pickup_group.id,
                        'pickup_point_id': voucher.pickup_point.id,
                    }
                })
                if request.COOKIES.get('voucher_code') is None:
                    response.set_cookie(
                        'voucher_code',
                        voucher_code,
                        max_age=86400,
                        secure=True,
                        httponly=False,
                        samesite='None'
                    )
                if request.COOKIES.get('pickup_group') is None:
                    response.set_cookie('pickup_group', voucher.pickup_group.id, max_age=86400, secure=True, httponly=False, samesite='None')
                if request.COOKIES.get('pickup_point') is None:
                    response.set_cookie('pickup_point', voucher.pickup_point.id, max_age=86400, secure=True, httponly=False, samesite='None')


                print('response: ' + str(response))
                return response
            else:
                booking_data = get_reservation(voucher_code)
                # print(booking_data)
                reservation_instance, reservation_response = create_reservation(booking_data)
                print('reservation_response: ' + str(reservation_response))
                if reservation_response.get('success') is not False:
                    print('get success: ' + str(reservation_response.get('success')))
                    return_data = reservation_response.get('return_data', {})
                    print('return_data: ' + str(return_data))

                    response = JsonResponse({
                        'success': True,
                        'message': 'Reservation created successfully.',
                        'return_data': return_data
                    })
                    response.set_cookie('voucher_code', booking_data.get("Id"), max_age=86400, secure=True, httponly=False, samesite='None')
                    response.set_cookie('pickup_group', return_data.get('pickup_group_id'), max_age=86400, secure=True, httponly=False, samesite='None')
                    response.set_cookie('pickup_point', return_data.get('pickup_point_id'), max_age=86400, secure=True, httponly=False, samesite='None')


                    return response
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'Reservation not created or found.'
                    })

                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    else:
        return JsonResponse({
            'success': False,
            'message': 'Invalid request method.'
        })
   
    
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
def excursion_list(request):
    excursions = Excursion.objects.filter(availabilities__isnull=False).filter(status='active').distinct()
    return render(request, 'main/excursions/excursion_list.html', {
        'excursions': excursions,
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

    # Process availability data
    availability_dates_by_region, pickup_points = ExcursionService.get_availability_data(
        excursion_availabilities
    )
    pickup_group_map = ExcursionService.get_pickup_group_map(availability_dates_by_region)


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
        'pickup_points': pickup_points,
        'user_has_feedback': user_has_feedback,
        'pickup_group_map': pickup_group_map,
        'remaining_seats': remaining_seats,
    })


# Helper functions for better code organization

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
        'pickup_points': [],
        'user_has_feedback': user_has_feedback,
        'remaining_seats': 0,
    })


def _get_feedback_form(user, user_has_feedback, excursion):
    """Get feedback form if user is authenticated and hasn't submitted feedback."""
    if user.is_authenticated and not user_has_feedback:
        return FeedbackForm(author=user, excursion=excursion)
    return None


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
        
        # Create booking
        booking = BookingService.create_booking(
            user=request.user,
            excursion_availability=excursion_availability,
            booking_data=booking_data,
            guest_data=guest_data,
            voucher_instance=voucher_instance,
            selected_date=selected_date,
            availability_id=availability_id
        )
        
        # Set partial payment method
        booking.partial_paid_method = partial_paid_method
        booking.save()
        
        return JsonResponse({
            'success': True,
            'redirect_url': reverse('checkout', kwargs={'booking_pk': booking.pk})
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

    payment_status = request.GET.get('payment_status')

    if payment_status == 'completed':
        try:
            booking.payment_status = 'completed'
            booking.save()
            messages.success(request, 'Booking completed.')
            return redirect('booking_detail', pk)
        except Exception as e:
            messages.error(request, f'Error updating booking: {str(e)}')
    if request.method == 'POST':
        # Handle both form data and JSON data
        if request.headers.get('Content-Type') == 'application/json':
            try:
                data = json.loads(request.body)
                action_type = data.get('action_type')
            except json.JSONDecodeError:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid JSON data'
                })
        else:
            action_type = request.POST.get('action_type')
        
        try:
            if action_type == 'complete_payment':
                booking.payment_status = 'completed'
                booking.save()
                messages.success(request, 'Booking completed.')

                return JsonResponse({
                    'status': 'success',
                    'message': 'Booking completed successfully.',
                    'redirect_url': reverse('booking_detail', kwargs={'pk': pk})
                })

            elif action_type == 'cancel_payment':
                booking.payment_status = 'cancelled'
                booking.save()
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
                return JsonResponse({
                    'status': 'success',
                    'message': 'Booking set to pending successfully.',
                    'redirect_url': reverse('booking_detail', kwargs={'pk': pk})
                })
        
        except Exception as e:
            error_message = f'Error updating booking: {str(e)}'
            messages.error(request, error_message)
            return JsonResponse({
                'status': 'error',
                'message': error_message
            })

    return render(request, 'main/bookings/booking_detail.html', {
        'booking': booking,
    })

# ----- Checkout View -----
# Guests and clients go through checkout; reps/admins redirected to detail
def checkout(request, booking_pk):
    booking = get_object_or_404(Booking, pk=booking_pk)
     

    if request.method == 'POST':
        # TODO: integrate Stripe payment here
        # booking.payment_status = 'completed'
        booking.save()
        messages.success(request, 'Booking saved. Please proceed to payment.')
        return redirect('booking_detail', booking_pk)
    

    return render(request, 'main/bookings/checkout.html', {
        'booking': booking,
    })

# ----- Auth Views -----
def signup(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                if user:
                    user_profile = UserProfile.objects.create(
                        user=user,
                        role='client',
                        name=form.cleaned_data['name'],
                        email=form.cleaned_data['username'],
                        phone=form.cleaned_data.get('phone', '')
                    )
                    print(f'this is the user_profile: {user_profile}')
                    login(request, user)
                    messages.success(request, 'Account created successfully. Please verify your email to continue.')
                    return redirect('excursion_list')
                else:
                    messages.error(request, 'Failed to create account.')
                    return redirect('signup')
            except Exception as e:
                messages.error(request, f'Error creating account: {str(e)}')
                return redirect('signup')
        else:
            messages.error(request, 'Please correct the errors below. ')
            return render(request, 'main/accounts/signup.html', {'form': form})
    else:
        form = SignupForm()

    return render(request, 'main/accounts/signup.html', {'form': form})

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
            
            # TODO: Send password reset email
            # email_subject = 'Password Reset'
            # email_body = f'Click the link to reset your password: {request.scheme}://{request.get_host()}/password_reset_token/{token}/'
            # email_from = settings.EMAIL_HOST_USER
            # recipient_list = [email]
            # send_mail(email_subject, email_body, email_from, recipient_list)

            messages.success(request, 'Password reset email sent. Please check your email.')
            # TO BE UPDATED
            # return redirect('excursion_list')
            return redirect('password_reset_token', token=token)
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

@login_required
def profile(request, pk):
    user = get_object_or_404(User, pk=pk)
    bookings = Booking.objects.filter(user=user, deleteByUser=False).order_by('-created_at')
    profile = UserProfile.objects.get(user=user)

    # Only allow users to view their own profile unless they're staff
    if request.user.id != user.id and not request.user.is_staff:
        messages.error(request, "You don't have permission to view this profile.")
        return redirect('homepage')
    
    return render(request, 'main/accounts/profile.html', {
        'bookings': bookings,
        'user_profile': profile,
    })    

@login_required
def profile_edit(request, pk):
    # Get the user first, then their profile
    user = get_object_or_404(User, pk=pk)
    profile = get_object_or_404(UserProfile, user=user)

    print(f'this is the profile: {profile}')
    print(f'this is the user: {user}')
    print(f'this is the pk: {pk}')
    
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
        total=Sum('price')
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
    groups = Group.objects.all()

        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        groups = groups.filter(
            Q(name__icontains=search_query)
        )


    return render(request, 'main/groups/group_list.html', {
        'groups': groups,
    })

@user_passes_test(is_staff)
def group_create(request):
    if request.method == 'POST':
        form = GroupForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Group created successfully.')
            return redirect('group_list')
    else:
        form = GroupForm()
    return render(request, 'main/groups/group_form.html', {
        'form': form,
    })

@user_passes_test(is_staff)
def group_detail(request, pk):
    group = get_object_or_404(Group, pk=pk)
    return render(request, 'main/groups/group_detail.html', {
        'group': group,
    })

@user_passes_test(is_staff)
def group_update(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        form = GroupForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            messages.success(request, 'Group updated successfully.')
            return redirect('group_detail', pk) 
    else:
        form = GroupForm(instance=group)
    return render(request, 'main/groups/group_form.html', {
        'form': form,
        'group': group,
    })

@user_passes_test(is_staff)
def group_delete(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        group.delete()
        messages.success(request, 'Group deleted successfully.')
        return redirect('group_list')
    return render(request, 'main/groups/group_confirm_delete.html', {
        'group': group,
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
    providers = UserProfile.objects.filter(role='provider')
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
        
    return render(request, 'main/admin/providers.html', {
        'providers': providers,
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
            
            if name and email:
                # Create User first
                user = User.objects.create_user(
                    username=email,
                    email=email,
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
            
            if name:
                rep.name = name
                rep.email = email
                rep.phone = phone
                rep.save()
                messages.success(request, 'Representative updated successfully.')

        elif action_type == 'delete_rep':
            rep = get_object_or_404(User, pk=item_id)    

            messages.success(request, 'Representative deleted successfully.')
            return redirect('manage_reps')

    return render(request, 'main/admin/reps.html', {
        'reps': UserProfile.objects.filter(role='representative'),
    })

@user_passes_test(is_staff)
def clients_list(request):
    clients = UserProfile.objects.filter(role='client')    
    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        clients = clients.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
    
    # Handle sorting
    sort_by = request.GET.get('sort', 'name')
    sort_order = request.GET.get('order', 'asc')
    
    # Validate sort field
    valid_sort_fields = ['name', 'email', 'phone', 'status', 'created_at']
    if sort_by not in valid_sort_fields:
        sort_by = 'name'
    
    # Apply sorting
    if sort_order == 'desc':
        sort_by = f'-{sort_by}'
    
    clients = clients.order_by(sort_by)


    return render(request, 'main/admin/clients.html', {
        'clients': clients,
        'current_sort': request.GET.get('sort', 'name'),
        'current_order': request.GET.get('order', 'asc'),
    })

@user_passes_test(is_staff)
def manage_clients(request):
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
            client = get_object_or_404(UserProfile, pk=item_id)
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
        

    return render(request, 'main/admin/clients.html', {
        'clients': UserProfile.objects.filter(role='client'),
    })
    
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

            if name:
                guide.name = name
                guide.email = email
                guide.phone = phone
                guide.save()
                messages.success(request, 'Guide updated successfully.')

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
    reservations = Reservation.objects.all()

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

        return render(request, 'main/admin/admin_reservations.html', {
            'reservations': reservations,
        })   
    except Reservation.DoesNotExist:
        messages.error(request, 'No reservations found')
        return redirect('admin_reservations')
    except Exception as e:
        messages.error(request, f'Error fetching reservations: {str(e)}')
        return redirect('admin_reservations')

@user_passes_test(is_staff)
def bookings_list(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        
        if action_type == 'bulk_delete':
            selected_ids = request.POST.getlist('selected_bookings')
            if selected_ids:
                bookings_to_delete = Booking.objects.filter(id__in=selected_ids)
                count = bookings_to_delete.count()
                bookings_to_delete.delete()
                messages.success(request, f'{count} booking(s) deleted successfully.')
            return redirect('bookings_list')
    
    # Get sorting parameters
    sort_by = request.GET.get('sort_by', 'created_at')
    sort_order = request.GET.get('sort_order', 'desc')
    search_query = request.GET.get('search', '')
    
    # Validate sort_by parameter
    valid_sort_fields = ['created_at', 'payment_status', 'price', 'guest_name', 'date']
    if sort_by not in valid_sort_fields:
        sort_by = 'created_at'
    
    # Validate sort_order parameter
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'
    
    # Apply sorting
    if sort_order == 'desc':
        sort_field = f'-{sort_by}'
    else:
        sort_field = sort_by
    
    # Start with all bookings
    bookings = Booking.objects.all().order_by('created_at')
    
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
    
    # Apply sorting
    bookings = bookings.order_by(sort_field)
    
    return render(request, 'main/bookings/bookings_list.html', {
        'bookings': bookings,
        'current_sort_by': sort_by,
        'current_sort_order': sort_order,
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
        'reservations': Reservation.objects.filter(status='active'),
    })

def check_excursion_pickup_groups(request):

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            excursion_id = data.get('excursion_id')
            
            pickup_groups = ExcursionAvailability.objects.filter(excursion=excursion_id).values('pickup_groups').distinct()

            return JsonResponse({'pickup_groups': list(pickup_groups)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

@user_passes_test(is_staff)
def availability_form(request, pk=None):

    availability = None
    if pk:
        availability = get_object_or_404(ExcursionAvailability, pk=pk)
    
    if request.method == 'POST':
        form = ExcursionAvailabilityForm(request.POST, instance=availability)
        pickup_groups = request.POST.getlist('pickup_groups')
        excursion = request.POST.get('excursion')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        # region = request.POST.get('region')


        overlapping_query = ExcursionAvailability.objects.filter(
            excursion=excursion,
            start_date__lte=end_date,
            end_date__gte=start_date,
            pickup_groups__in=pickup_groups,
            # region=region,
            status='active'
        )

        if pk:
            overlapping_query = overlapping_query.exclude(pk=pk)
        
        if overlapping_query.exists():
            error_message = 'Availability already exists for this excursion during the selected dates with the selected pickup groups.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': [error_message]
                })
            form.add_error(None, error_message)
        elif form.is_valid():
            try:
                # First validate weekday capacities from form data
                # max_guests = int(request.POST.get('max_guests', 0))
                selected_weekday_ids = request.POST.getlist('weekdays')
                pickup_group_ids = pickup_groups

                # Validate capacities before saving
                # for weekday_id in selected_weekday_ids:
                #     capacity_name = f'weekdays_capacity_{weekday_id}'
                #     capacity = request.POST.get(capacity_name)
                #     if capacity:
                #         try:
                #             capacity = int(capacity)
                #             if capacity > max_guests:
                #                 raise ValueError(f"Capacity for {DayOfWeek.objects.get(id=weekday_id).get_code_display()} cannot be greater than the maximum number of guests.")
                #         except ValueError as e:
                #             if str(e).startswith("Capacity for"):
                #                 raise e
                #             raise ValueError(f"Invalid capacity value for {DayOfWeek.objects.get(id=weekday_id).get_code_display()}")

                
                availability = form.save(commit=False)
                excursion_pk = request.POST.get('excursion')

                if not excursion_pk:
                    raise ValueError("Excursion ID is required")
                    
                excursion = get_object_or_404(Excursion, pk=excursion_pk)
                availability.excursion = excursion
                
                # Save the availability to get an ID
                availability.save()
                
                # Manually set the weekdays and pickup groups relationships
                availability.weekdays.set(selected_weekday_ids)
                availability.pickup_groups.set(pickup_group_ids)
                
                # Update weekday capacities
                # for weekday_id in selected_weekday_ids:
                #     capacity_name = f'weekdays_capacity_{weekday_id}'
                #     capacity = request.POST.get(capacity_name)
                #     if capacity:
                #         try:
                #             capacity = int(capacity)
                #             if capacity == 0:
                #                 capacity = max_guests
                #             DayOfWeek.objects.filter(id=weekday_id).update(capacity=capacity)
                #         except ValueError:
                #             pass  
                
                if excursion.status != 'active':
                    excursion.status = 'active'
                    excursion.save()

                # Delete existing AvailabilityDays entries (for both create and update)
                AvailabilityDays.objects.filter(excursion_availability=availability).delete()

                # Delete existing PickupGroupAvailability entries (for both create and update)
                PickupGroupAvailability.objects.filter(excursion_availability=availability).delete()
                
                # Get the selected weekdays after saving
                selected_weekdays = availability.weekdays.all()
                
                # Convert selected weekdays to Python's weekday numbers (0=Monday, 6=Sunday)
                weekday_numbers = []
                weekday_mapping = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}
                
                for weekday in selected_weekdays:
                    if weekday.code in weekday_mapping:
                        weekday_numbers.append(weekday_mapping[weekday.code])
                
                # Create an entry for each day in the range that matches selected weekdays
                current_date = availability.start_date
                while current_date <= availability.end_date:
                    if current_date.weekday() in weekday_numbers:
                        AvailabilityDays.objects.create(
                            excursion_availability=availability,
                            date_day=current_date,
                            capacity=availability.max_guests
                        )
                    current_date += timedelta(days=1)

                # Create entries for each pickup group
                # region_id = availability.region_id
                for pickup_group in PickupGroup.objects.filter(id__in=pickup_group_ids):
                    PickupGroupAvailability.objects.create(
                        excursion_availability=availability,
                        pickup_group=pickup_group
                    )

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
        'pickup_groups': PickupGroup.objects.all(),
    })

@user_passes_test(is_staff)
def availability_detail(request, pk):
    availability = get_object_or_404(ExcursionAvailability, pk=pk)
    pickup_points = PickupPoint.objects.filter(pickup_group__in=availability.pickup_groups.all())
    pickup_groups = PickupGroup.objects.filter(id__in=availability.pickup_groups.all())
    return render(request, 'main/availabilities/availability_detail.html', {
        'availability': availability,
        'pickup_points': pickup_points,
        'pickup_groups': pickup_groups,
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
    pickup_points = PickupPoint.objects.all().select_related('pickup_group').order_by('name')
    pickup_groups = PickupGroup.objects.all()
    
    # Convert pickup groups to JSON-serializable format
    pickup_groups_json = json.dumps([{'id': group.id, 'name': group.name} for group in pickup_groups])
    
    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        pickup_points = pickup_points.filter(
            Q(name__icontains=search_query) |
            Q(address__icontains=search_query) |
            Q(pickup_group__name__icontains=search_query)
        )
    
    context = {
        'pickup_points': pickup_points,
        'pickup_groups': pickup_groups,
        'pickup_groups_json': pickup_groups_json,
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
            address = request.POST.get('address', '').strip()
            pickup_group_id = request.POST.get('pickup_group')
            google_maps_link = request.POST.get('google_maps_link', '').strip()

            if not all([name, address, pickup_group_id]):
                messages.error(request, 'Please fill in all required fields')
                return redirect('pickup_points_list')
            
            try:
                pickup_group = PickupGroup.objects.get(id=pickup_group_id)
            except PickupGroup.DoesNotExist:
                messages.error(request, 'Invalid pickup group selected')
                return redirect('pickup_points_list')
            
            PickupPoint.objects.create(
                name=name,
                address=address,
                pickup_group=pickup_group,
                google_maps_link=google_maps_link if google_maps_link else None,
            )
            messages.success(request, 'Pickup point added successfully')
            
        elif action_type == 'edit_point':
            item_id = request.POST.get('item_id')
            name = request.POST.get('name', '').strip()
            address = request.POST.get('address', '').strip()
            pickup_group_id = request.POST.get('pickup_group')
            google_maps_link = request.POST.get('google_maps_link', '').strip()

            if not all([item_id, name, address, pickup_group_id]):
                messages.error(request, 'Please fill in all required fields')
                return redirect('pickup_points_list')
            
            try:
                point = PickupPoint.objects.get(id=item_id)
                pickup_group = PickupGroup.objects.get(id=pickup_group_id)
            except (PickupPoint.DoesNotExist, PickupGroup.DoesNotExist):
                messages.error(request, 'Invalid pickup point or group selected')
                return redirect('pickup_points_list')
            
            point.name = name
            point.address = address
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

    return render(request, 'main/admin/staff.html', {
        'staffs': staff,
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
                    is_staff=True,
                )   
                # Create UserProfile
                UserProfile.objects.create(
                    user=user,
                    name=name,
                    email=email,
                    phone=phone,
                    role='admin',
                )   
                messages.success(request, 'Staff member created successfully.')
                return redirect('staff_list')
            
        elif action_type == 'edit_staff':
            staff = get_object_or_404(UserProfile, pk=item_id)
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            # role = request.POST.get('role', '').strip()
            password = request.POST.get('password', '').strip()

            if name:
                staff.name = name
                staff.email = email
                staff.phone = phone
                staff.role = "admin"
                staff.password = password
                staff.save()
                messages.success(request, 'Staff member updated successfully.')
                return redirect('staff_list')

        elif action_type == 'delete_staff':
            staff = get_object_or_404(User, pk=item_id)
            staff.delete()
            messages.success(request, 'Staff member deleted successfully.')
            return redirect('staff_list')
        

    return render(request, 'main/admin/staff.html', {
        'staffs': User.objects.filter(is_staff=True),
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
    pickup_groups = PickupGroup.objects.all()
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

                if name and code:
                    try:
                        PickupGroup.objects.create(
                            name=name,
                            code=code,
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

                if name:    
                    group.name = name
                    if code:
                        group.code = code
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

