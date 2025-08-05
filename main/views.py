from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
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
    GroupForm
)
from django.core.validators import validate_email, RegexValidator
from django.core.exceptions import ValidationError
import re
import json
from django.db.models import Q, Sum, Count
from django.apps import apps
from .cyber_api import get_groups, get_hotels, get_pickup_points, get_excursions, get_excursion_description, get_providers, get_excursion_availabilities, get_reservation

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
    excursions = Excursion.objects.all().filter(status='active').distinct()
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
   
def create_reservation(booking_data):
    if booking_data is not None:
        try:
        
            booking_id = booking_data.get("Id")
            lead_name = booking_data.get("LeadName")
            lead_email = booking_data.get("LeadEmail")
            lead_phone = booking_data.get("LeadPhone")
            adults = booking_data.get("Adults")
            children = booking_data.get("Children")
            date_from_full = booking_data.get("DateFrom")
            date_from = date_from_full.split("T")[0]
            # date_from = datetime.strptime(date_from_part, "%Y-%m-%d").strftime("%d-%m-%Y")
            date_to_full = booking_data.get("DateTo")
            date_to = date_to_full.split("T")[0]
            print('date_to - create_reservation function: ' + str(date_to))
            # date_to = datetime.strptime(date_to_part, "%Y-%m-%d").strftime("%d-%m-%Y")

            pickup_point_id = None
            hotel_id = None
            pickup_time = None
            for service in booking_data.get("Services", []):
                if "PickupPoint" in service and pickup_point_id is None:
                    pickup_point_id = service["PickupPoint"].get("Id")
                if service.get("Type") == "Hotel" and hotel_id is None:
                    hotel_id = service.get("Id")

                if service.get("TransferType") == "DepartureTransfer":
                    pickup_time = service.get("PickupTime")

                if pickup_point_id is not None and hotel_id is not None and pickup_time is not None:
                    break

            pickup_point_instance = PickupPoint.objects.get(id=pickup_point_id) if pickup_point_id else None
            pickup_group_instance = pickup_point_instance.pickup_group if pickup_point_instance else None

            # Convert pickup_time string to time object
            departure_time_obj = None
            if pickup_time:
                try:
                    departure_time_obj = datetime.strptime(pickup_time, '%H:%M').time()
                except (ValueError, TypeError):
                    departure_time_obj = None

            print(f"Pickup Group ID: {pickup_group_instance.id if pickup_group_instance else None}")
            print(f"Pickup Time: {pickup_time}")
            print(f"Date From: {date_from}")
            print(f"Date To: {date_to}")

            hotel_instance = Hotel.objects.get(id=hotel_id) if hotel_id else None

            reservation_obj, created = Reservation.objects.get_or_create(
                voucher_id=booking_id,
                defaults={
                    'client_name': lead_name,
                    'client_email': lead_email,
                    'client_phone': lead_phone,
                    'total_adults': adults,
                    'total_kids': children,
                    'check_in': date_from,
                    'check_out': date_to,
                    'pickup_point': pickup_point_instance,
                    'pickup_group': pickup_group_instance,
                    'hotel': hotel_instance,
                    'departure_time': departure_time_obj,
                }
            )

            if created:
                print(f"Booking created: {reservation_obj}")
            else:
                print(f"Booking already exists: {reservation_obj}")

            response_data = {
                'success': True,
                'message': 'Reservation found.' if not created else 'Reservation created successfully.',
                'return_data': {
                    'client_name': lead_name,
                    'pickup_group': pickup_group_instance.name if pickup_group_instance else None,
                    'pickup_point': pickup_point_instance.name if pickup_point_instance else None,
                    'pickup_group_id': pickup_group_instance.id if pickup_group_instance else None,
                    'pickup_point_id': pickup_point_instance.id if pickup_point_instance else None,
                    'client_email': lead_email,
                },
                'created': created
            }
            
            return reservation_obj, response_data

        except Exception as e:
            return None, {
                'success': False,
                'message': str(e)
            }
    else:
        return None, {
            'success': False,
            'message': 'Reservation not found.'
        }
    
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
                excursion_provider_id = UserProfile.objects.get(name=excursion_provider, role='provider').id
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
                user, user_created = User.objects.get_or_create(
                    id=provider_id,
                    username=provider_email or f"provider_{provider_id}",
                    defaults={
                        'first_name': provider_name,
                        'email': provider_email or "",
                    }
                )

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

def sync_excursion_availabilities(request):
    if request.method == 'POST':
        try:
            # excursion_availabilities_cl = get_excursion_availabilities()
            excursions = Excursion.objects.all()
            availabilities = []
            today = datetime.now().strftime("%Y-%m-%d")
            excursion_availabilities_cl = get_excursion_availabilities(excursion_id=3909)
            availability = excursion_availabilities_cl[0]['Availability']
            if availability:
                # print('availability: ' + str(availability[0]['Date']))
                availabilities.append(availability)
                # print('excursion id with availability: ' + str(excursion_id))


            print('availabilities: ' + str(availabilities))

            for i, av in enumerate(availabilities):
                av_date = av[i]['Date']
                print('av_date: ' + str(av_date))

            # for excursion in excursions:
            #     excursion_id = excursion.id
            #     excursion_availabilities_cl = get_excursion_availabilities(excursion_id)
            #     availability = excursion_availabilities_cl[0]['Availability']
            #     if availability:
            #         # print('availability: ' + str(availability[0]['Date']))
            #         availabilities.append(availability)
            #         print('excursion id with availability: ' + str(excursion_id))


            #     print('availabilities: ' + str(availabilities))
                # for av in availabilities:
                #     av_date = av[0]['Date']
                #     # av_date = datetime.strptime(av_date_str, "%Y-%m-%d")
                #     print('av_date: ' + str(av_date))
                    # print('today: ' + str(today))
                    # print('today: ' + str(today))
                    # if av_date > today:
                    #     print('av_date is in the future: ' + str(av_date))

                # print('availability: ' + str(availability))
                        
            total_synced = 0
            # for availability in excursion_availabilities_cl[0]['Availability']:
            #     print('availability: ' + str(availability['Date']))

                # availability = excursion_availabilities['Data'][0]
                # excursion_availability_id = excursion_availability['Id']
                # excursion_id = excursion_availability['ExcursionId']
                # excursion = Excursion.objects.get(id=excursion_id)

                # excursion_availability_entry, created = ExcursionAvailability.objects.get_or_create(
                #     id=excursion_availability_id,
                #     defaults={'excursion': excursion}
                # )
                # if created:
                #     print('created excursion availability: ' + str(excursion_availability_entry))
                #     total_synced += 1

                # if total_synced > 0:
                #     message = 'Sync successful! Total excursion availabilities synced: ' + str(total_synced)
                # else:
                #     message = 'Excursion availabilities are up to date.'
            message = 'Hiiiii.'
            return JsonResponse({'success': True, 'message': message})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error syncing excursion availabilities: {str(e)}'})
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

# ----- Excursion Views -----
def excursion_list(request):
    excursions = Excursion.objects.filter(availabilities__isnull=False).filter(status='active').distinct()
    return render(request, 'main/excursions/excursion_list.html', {
        'excursions': excursions,
    })

def excursion_detail(request, pk):

    excursion = get_object_or_404(Excursion, pk=pk)    
    feedback_form, booking_form = None, None
    excursion_availabilities = ExcursionAvailability.objects.filter(excursion=excursion)
    excursion_availability = excursion_availabilities.first()
    
    availability_dates_by_region = {}
    pickup_points = []
    # return_data = {}

    # voucher_code = manage_cookies(request, 'voucher_code', None, 'get')
    # print('found voucher code in cookies: ' + str(voucher_code))
    
    # if voucher_code:
    #     voucher = Reservation.objects.get(voucher_id=voucher_code)
    #     print('found voucher object: ' + str(voucher))
    #     if voucher:
    #         pickup_group_id = voucher.pickup_group

    #         return_data = {
    #             'client_name': voucher.client_name,
    #             'pickup_group_id': pickup_group_id,
    #         }
    # else:
    #     voucher_code = None
    #     print('no voucher code found in cookies')

    if not excursion_availability:
        feedback_form = FeedbackForm()
        booking_form = BookingForm()

        return render(request, 'main/excursions/excursion_detail.html', {
            'excursion': excursion,
            'feedback_form': feedback_form,
            'booking_form': booking_form,
            'excursion_availability': excursion_availability,
            'availability_dates_by_region': availability_dates_by_region,
            'pickup_points': pickup_points,
            # 'voucher_code': voucher_code,
            # 'return_data': return_data,
            'remaining_seats': 0,
        })


    for availability in excursion_availabilities:
        for pickup_group in availability.pickup_groups.all():
            group_id = str(pickup_group.id)
            # days = availability.availability_days.filter(excursion_availability=availability)
            days = availability.availability_days.all()
            
            # Convert queryset to list of dicts
            date_entries = [
                {"date": day.date_day.isoformat(), "id": day.id}
                for day in days
            ]
            # If the group already exists, append dates; else, create new entry
            if group_id not in availability_dates_by_region:
                availability_dates_by_region[group_id] = []
            availability_dates_by_region[group_id].extend(date_entries)

            # Get pickup points for this group
            points = PickupPoint.objects.filter(pickup_group=pickup_group).order_by('name')
            pickup_points.append({
                "pickup_group": group_id,
                "points": list(points.values('id', 'name'))
            })

    pickup_group_ids = [int(gid) for gid in availability_dates_by_region.keys()]
    pickup_groups = PickupGroup.objects.filter(id__in=pickup_group_ids).values('id', 'name')
    # Optionally, build a dict for easy lookup in JS
    pickup_group_map = {str(g['id']): g['name'] for g in pickup_groups}
    # print('pickup points: ' + str(pickup_points))


    # Handle feedback submission
    if request.method == 'POST' and 'feedback_submit' in request.POST:
        feedback_form = FeedbackForm(request.POST)
        if feedback_form.is_valid() and request.user.is_authenticated:
            feedback = feedback_form.save(commit=False)
            feedback.excursion = excursion
            feedback.author = request.user
            feedback.created_at = timezone.now()
            feedback.save()
            messages.success(request, 'Thank you for your feedback.')
            return redirect('excursion_detail', pk)
        
    # Handle booking submission
    elif request.method == 'POST' and 'booking_submit' in request.POST:
        # print(request.POST)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                booking_form = BookingForm(request.POST)
                
                if not booking_form.is_valid():
                    return JsonResponse({
                        'success': False,
                        'errors': booking_form.errors
                    })
                
                booking = booking_form.save(commit=False)
                
                # Handle empty strings by converting them to 0 before int conversion
                adults = int(request.POST.get('adults', '0') or '0')
                children = int(request.POST.get('children', '0') or '0')
                infants = int(request.POST.get('infants', '0') or '0')
                total_price = int(request.POST.get('total_price', '0') or '0')
                partial_price = int(request.POST.get('partial_payment', '0') or '0')
                voucher_id = request.POST.get('voucher_code', None)
                # print('voucher_id: ' + str(voucher_id))
                reservation_instance = None
                if voucher_id:
                    try:
                        reservation_instance = Reservation.objects.get(voucher_id=voucher_id)
                    except Reservation.DoesNotExist:
                        prepare_data = get_reservation(voucher_id)
                        # print(prepare_data)
                        reservation_instance, reservation_response = create_reservation(prepare_data)
                        print('reservation_instance: ' + str(reservation_instance))

                guest_email = request.POST.get('guest_email', None)
                guest_name = request.POST.get('guest_name', None)

                user = request.user
                user_instance = user if user else None

                if user.is_staff == True:
                    booking.payment_status = 'completed'
                else:
                    booking.payment_status = 'pending'               
                
                booking.excursion_availability = excursion_availability
                booking.user = user_instance
                booking.total_adults = adults
                booking.total_kids = children
                booking.total_infants = infants
                booking.voucher_id = reservation_instance
                booking.guest_email = guest_email
                booking.guest_name = guest_name
                booking.price = total_price # price before discount or partial payment

                if partial_price > 0:
                    final_price = total_price - partial_price
                    booking.partial_paid = partial_price
                else:
                    final_price = total_price
                    booking.partial_paid = 0

                booking.total_price = final_price # price after discount or partial payment

                selected_date = request.POST.get('selected_date')
                availability_id = request.POST.get('availability_id')
                
                if not selected_date or not availability_id:
                    return JsonResponse({
                        'success': False,
                        'message': 'Please select a date.'
                    })
                
                # Validate at least one participant                
                if adults + children + infants == 0:
                    return JsonResponse({
                        'success': False,
                        'message': 'Please select at least one participant.'
                    })

                booking.date = selected_date
                booking.availability_id = availability_id
                booking.save()

                # Check if the availability has enough guests
                total_guests = adults + children + infants
                availability_guests = availability.max_guests

                if total_guests > availability_guests:
                    return JsonResponse({
                        'success': False,
                        'message': 'The availability has not enough guests.'
                    })
                else:
                    availability.booked_guests += total_guests
                    availability.save()

                return JsonResponse({
                    'success': True,
                    'redirect_url': reverse('booking_detail', kwargs={'pk': booking.pk})
                })

            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': str(e),
                    'errors': booking_form.errors
                })
        # else:
        #     # Handle non-AJAX form submission
        #     booking_form = BookingForm(request.POST)
        #     if booking_form.is_valid():
        #         try:
        #             booking = booking_form.save(commit=False)
        #             booking.excursion_availability = excursion_availability
        #             user = request.user
        #             if user:
        #                 user_instance = user
        #             else:
        #                 user_instance = None
        #             booking.user = user_instance

        #             selected_date = request.POST.get('selected_date')
        #             availability_id = request.POST.get('availability_id')
                    
        #             if not selected_date or not availability_id:
        #                 messages.error(request, 'Please select a date.')
        #                 return redirect('excursion_detail', excursion.pk)
                    
        #             adults = int(request.POST.get('adults', 0))
        #             children = int(request.POST.get('children', 0))
        #             infants = int(request.POST.get('infants', 0))
                    
        #             if adults + children + infants == 0:
        #                 messages.error(request, 'Please select at least one participant.')
        #                 return redirect('excursion_detail', excursion.pk)

        #             booking.date = selected_date
        #             booking.availability_id = availability_id
        #             booking.save()

        #             messages.success(request, 'Booking created successfully.')
        #             return redirect('booking_detail', booking.pk)

        #         except Exception as e:
        #             messages.error(request, f'An error occurred: {str(e)}')
        #             return redirect('excursion_detail', excursion.pk)
        #     else:
        #         messages.error(request, 'Please correct the errors below.')
        #         return redirect('excursion_detail', excursion.pk)

    # pickup_points = PickupPoint.objects.none()
    # if excursion_availability:
    #     pickup_points = PickupPoint.objects.filter(pickup_group__in=excursion_availability.pickup_groups.all()).order_by('priority')

    # Calculate remaining seats for the first availability
    remaining_seats = 0
    if excursion_availability:
        remaining_seats = excursion_availability.max_guests - excursion_availability.booked_guests

    return render(request, 'main/excursions/excursion_detail.html', {
        'excursion': excursion,
        'feedback_form': feedback_form,
        'excursion_availabilities': excursion_availabilities,
        'excursion_availability': excursion_availability,
        'booking_form': booking_form,
        'availability_dates_by_region': availability_dates_by_region,
        'pickup_points': pickup_points,
        # 'voucher_code': voucher_code,
        # 'return_data': return_data,
        'pickup_group_map': pickup_group_map,
        'remaining_seats': remaining_seats,
    })

@user_passes_test(is_staff)
def excursion_create(request):
    if request.method == 'POST':
        form = ExcursionForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    excursion = form.save()
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
                
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the following errors:',
                    'errors': error_messages
                })
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ExcursionForm()
    
    return render(request, 'main/excursions/excursion_form.html', {
        'form': form,
    })

@user_passes_test(is_staff)
def excursion_update(request, pk):
    excursion = get_object_or_404(Excursion, pk=pk)
    form = ExcursionForm(request.POST, request.FILES, instance=excursion)
    
    if request.method == 'POST':
        if form.is_valid():
            try:
                with transaction.atomic():
                    excursion = form.save()
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
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the errors below.',
                    'errors': form.errors
                })
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ExcursionForm(instance=excursion)
    
    return render(request, 'main/excursions/excursion_form.html', {
        'form': form,
        'excursion': excursion,
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
# def booking_create(request, availability_pk):
    availability = get_object_or_404(ExcursionAvailability, pk=availability_pk)
    if request.method == 'POST':
        form = BookingForm(request.POST, user=request.user if request.user.is_authenticated else None)
        if form.is_valid():
            booking = form.save(commit=False)
            # booking.user = request.user if request.user.is_authenticated else None
            booking.excursion_availability = availability
            
            if request.user:
                booking.user = request.user
                role = getattr(request.user.profile, 'role', None)

                if request.user.is_staff == True:
                    booking.payment_status = 'completed'
                elif role == 'representative':
                    booking.payment_status = 'pending'
                else:
                    booking.user = None
                    booking.payment_status = 'pending'


            booking.save()
            messages.success(request, 'Booking created.')
            # Redirect logic: reps/admin skip checkout
            if request.user.is_authenticated and (request.user.is_staff or getattr(request.user.profile, 'role', None) == 'representative'):
                return redirect('booking_detail', booking.pk)
            # Guests/clients go to checkout
            return redirect('checkout', booking.pk)
    else:
        form = BookingForm(user=request.user if request.user.is_authenticated else None)
    return render(request, 'main/bookings/booking_form.html', {
        'form': form,
        'availability': availability,
    })

# Booking detail: only authenticated users (clients/reps/admins)
@user_passes_test(is_staff)
def booking_delete(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    # if request.method == 'POST':
    try:
        if request.method == 'POST':
            booking.delete()
            messages.success(request, 'Booking deleted.')
        else:
            messages.error(request, 'Booking not deleted.')
    except Exception as e:
        messages.error(request, f'Error deleting booking: {str(e)}')
        
    # else:
    #     messages.error(request, 'Booking not deleted.')

    return redirect('admin_dashboard', pk=request.user.profile.id)


@login_required 
def booking_detail(request, pk):
    
    booking = get_object_or_404(Booking, pk=pk)

    print('request.user.is_staff: ' + str(request.user.is_staff))
    print('request.user.profile.role: ' + str(request.user.profile.role))

    # print('booking: ' + str(booking.user.profile.name))
    # print('booking price: ' + str(booking.price))
    # print('booking total price: ' + str(booking.total_price))
    # print('booking total adults: ' + str(booking.total_adults))
    # print('booking total kids: ' + str(booking.total_kids))
    # print('booking total infants: ' + str(booking.total_infants))
    # print('booking date: ' + str(booking.date))
    # print('booking pickup point: ' + str(booking.pickup_point))
    # print('booking voucher: ' + str(booking.voucher_id))

    return render(request, 'main/bookings/booking_detail.html', {
        'booking': booking,
    })

# ----- Checkout View -----
# Guests and clients go through checkout; reps/admins redirected to detail
def checkout(request, booking_pk):
    booking = get_object_or_404(Booking, pk=booking_pk)
    # Redirect reps/admins immediately to detail
    if request.user.is_authenticated:
        role = getattr(request.user.profile, 'role', None)
        if request.user.is_staff or role == 'representative':
            return redirect('booking_detail', booking_pk)
    # Process payment (placeholder for Stripe integration)
    if request.method == 'POST':
        # TODO: integrate Stripe payment here
        booking.payment_status = 'completed'
        booking.save()
        messages.success(request, 'Payment successful.')
        return redirect('booking_detail', booking_pk)
    return render(request, 'main/bookings/checkout.html', {
        'booking': booking,
    })

# ----- Auth Views -----
def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Create associated profile with default client role
            UserProfile.objects.create(user=user, role='client')
            login(request, user)
            messages.success(request, 'Account created successfully. Please verify your email to continue.')
            return redirect('excursion_list')
    else:
        form = UserCreationForm()
    return render(request, 'main/accounts/signup.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('excursion_list')
    else:
        form = AuthenticationForm()
    return render(request, 'main/accounts/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('excursion_list')

@login_required
def profile(request, pk):
    user = get_object_or_404(User, pk=pk)
    bookings = Booking.objects.filter(user=user)
    user_profile = user.profile
    
    # Only allow users to view their own profile unless they're staff
    if request.user.id != user_profile.id and not request.user.is_staff:
        messages.error(request, "You don't have permission to view this profile.")
        return redirect('profile', pk=request.user.profile.id)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=user_profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('profile', pk=pk)
    else:
        form = UserProfileForm(instance=user_profile)
    
    return render(request, 'main/accounts/profile.html', {
        'form': form,
        'bookings': bookings,
        'user_profile': user_profile,
    }
    )    

def profile_edit(request, pk):
    profile = get_object_or_404(UserProfile, pk=pk)
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('profile', pk=pk)
    else:
        form = UserProfileForm(instance=profile)
    return render(request, 'main/accounts/profile_edit.html', {
        'form': form,
    })

# @login_required
@user_passes_test(is_staff)
def admin_dashboard(request, pk):
    # Get admin stats
    active_excursions_count = Excursion.objects.filter(status='active').count()
    total_excursions_count = Excursion.objects.all().count()
    reps_count = User.objects.filter(profile__role='representative').exclude(is_staff=True).count()
    clients_count = User.objects.filter(profile__role='client').exclude(is_staff=True).count()
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
        'booking_count': Booking.objects.count(),
        'user': User.objects.get(profile__id=pk),
        'total_excursions_count': total_excursions_count,
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
                    role='client'
                )
                messages.success(request, 'Client created successfully.')
                return redirect('manage_clients')
            
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
            client = get_object_or_404(UserProfile, pk=item_id)
            client.delete()
            messages.success(request, 'Client deleted successfully.')
            return redirect('manage_clients')
        
        elif action_type == 'bulk_delete':
            selected_ids = request.POST.getlist('selected_clients')
            if selected_ids:
                clients_to_delete = UserProfile.objects.filter(id__in=selected_ids, role='client')
                count = clients_to_delete.count()
                clients_to_delete.delete()
                messages.success(request, f'{count} client(s) deleted successfully.')
            return redirect('manage_clients')
        

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

    return render(request, 'main/availabilities/availabilities_list.html', {
        'availabilities': availabilities,
        'excursions': excursions,
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
    bookings = Booking.objects.all()
    return render(request, 'main/bookings/bookings_list.html', {
        'bookings': bookings,
    })

@user_passes_test(is_staff)
def booking_edit(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    form = BookingForm(instance=booking)
    if request.method == 'POST':
        form = BookingForm(request.POST, instance=booking)
        if form.is_valid():
            booking = form.save(commit=False)
            # booking.save()
            # booking.payment_status = 'completed'
            booking.save()
            messages.success(request, 'Booking updated successfully.')
            return redirect('booking_detail', pk=pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    return render(request, 'main/bookings/booking_edit.html', {
        'booking': booking,
        'form': form,
    })

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
                    reservation_response = create_reservation(booking_data)
                    print('reservation_response from manage reservations: ' + str(reservation_response))
                    if reservation_response.get('message') == "Reservation found.":
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

@user_passes_test(is_staff)
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

            if name and email:
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
            role = request.POST.get('role', '').strip()
            # password = request.POST.get('password', '').strip()

            if name:
                staff.name = name
                staff.email = email
                staff.phone = phone
                staff.role = role
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


    return render(request, 'main/admin/admin_excursions.html', {
        'excursions': excursions,
    })

@user_passes_test(is_staff)
def hotel_list(request):
    hotels = Hotel.objects.all()
    pickup_groups = PickupGroup.objects.all()
    pickup_groups_json = json.dumps([{'id': pickup_group.id, 'name': pickup_group.name} for pickup_group in pickup_groups])

    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        hotels = hotels.filter(
            Q(name__icontains=search_query) |
            Q(address__icontains=search_query) 
        )

    return render(request, 'main/admin/hotel_list.html', {
        'hotels': hotels,
        'pickup_groups': pickup_groups,
        'pickup_groups_json': pickup_groups_json,
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
