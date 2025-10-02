"""
Utility functions for booking and feedback operations.
"""
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import (
    Excursion, Feedback, Booking, Reservation, 
    AvailabilityDays, ExcursionAvailability, PickupPoint, Hotel
)
from .cyber_api import get_reservation
from datetime import datetime


class FeedbackService:
    """Service class for handling feedback operations."""
    
    @staticmethod
    def user_has_feedback(user, excursion):
        """Check if user has already submitted feedback for an excursion."""
        if not user or not user.is_authenticated:
            return False
        return Feedback.objects.filter(author=user, excursion=excursion).exists()
    
    @staticmethod
    def create_feedback(user, excursion, rating, comment):
        """Create a new feedback entry."""
        if FeedbackService.user_has_feedback(user, excursion):
            raise ValidationError("You have already submitted feedback for this excursion.")
        
        feedback = Feedback.objects.create(
            excursion=excursion,
            author=user,
            rating=rating,
            comment=comment,
            created_at=timezone.now()
        )
        return feedback


class BookingService:
    """Service class for handling booking operations."""
    
    @staticmethod
    def validate_booking_data(request_data):
        """Validate booking form data."""
        adults = int(request_data.get('adults', '0') or '0')
        children = int(request_data.get('children', '0') or '0')
        infants = int(request_data.get('infants', '0') or '0')
        total_price = int(request_data.get('total_price', '0') or '0')
        partial_price = int(request_data.get('partial_payment', '0') or '0')
        
        # Validate at least one participant
        if adults + children + infants == 0:
            raise ValidationError('Please select at least one participant.')
        
        return {
            'adults': adults,
            'children': children,
            'infants': infants,
            'total_price': total_price,
            'partial_price': partial_price,
            'total_guests': adults + children + infants
        }
    
    @staticmethod
    def get_remaining_seats(availability, selected_date):
        """Calculate remaining seats for a specific date."""
        try:
            day_availability = AvailabilityDays.objects.get(
                date_day=selected_date, 
                excursion_availability=availability
            )
            return day_availability.capacity - day_availability.booked_guests
        except AvailabilityDays.DoesNotExist:
            return 0
    
    @staticmethod
    def handle_voucher(voucher_id):
        """Handle voucher/reservation lookup or creation."""
        if not voucher_id:
            return None
            
        try:
            return Reservation.objects.get(voucher_id=voucher_id)
        except Reservation.DoesNotExist:
            prepare_data = get_reservation(voucher_id)
            reservation_instance, _ = create_reservation(prepare_data)
            return reservation_instance
    
    @staticmethod
    def calculate_pricing(total_price, partial_price):
        """Calculate final pricing after partial payment."""
        if partial_price > 0:
            final_price = total_price - partial_price
            return {
                'total_price': final_price,
                'partial_paid': partial_price
            }
        else:
            return {
                'total_price': total_price,
                'partial_paid': 0 if partial_price else None
            }
    
    @staticmethod
    @transaction.atomic
    def create_booking(user, excursion_availability, booking_data, guest_data, 
                      voucher_instance, selected_date, availability_id):
        """Create a booking with all related operations."""
        # Validate remaining seats
        remaining_seats = BookingService.get_remaining_seats(
            excursion_availability, selected_date
        )
        
        if booking_data['total_guests'] > remaining_seats:
            raise ValidationError(
                f'The availability has not enough guests. Remaining seats: {remaining_seats}'
            )
        
        # Create booking
        booking = Booking.objects.create(
            user=user if user.is_authenticated else None,
            excursion_availability=excursion_availability,
            voucher_id=voucher_instance,
            guest_name=guest_data.get('guest_name'),
            guest_email=guest_data.get('guest_email'),
            total_adults=booking_data['adults'],
            total_kids=booking_data['children'],
            total_infants=booking_data['infants'],
            date=selected_date,
            price=booking_data['total_price'],
            **BookingService.calculate_pricing(
                booking_data['total_price'], 
                booking_data['partial_price']
            )
        )
        
        # Update availability counts
        day_availability = AvailabilityDays.objects.get(
            date_day=selected_date, 
            excursion_availability=excursion_availability
        )
        day_availability.booked_guests += booking_data['total_guests']
        day_availability.save()
        
        excursion_availability.booked_guests += booking_data['total_guests']
        excursion_availability.save()
        
        return booking


class ExcursionService:
    """Service class for handling excursion-related operations."""
    
    @staticmethod
    def get_availability_data(excursion_availabilities):
        """Process excursion availabilities and return structured data."""
        availability_dates_by_region = {}
        pickup_points = []
        
        for availability in excursion_availabilities:
            for pickup_group in availability.pickup_groups.all():
                group_id = str(pickup_group.id)
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
                from .models import PickupPoint
                points = PickupPoint.objects.filter(pickup_group=pickup_group).order_by('name')
                pickup_points.append({
                    "pickup_group": group_id,
                    "points": list(points.values('id', 'name'))
                })
        
        return availability_dates_by_region, pickup_points
    
    @staticmethod
    def get_pickup_group_map(availability_dates_by_region):
        """Get pickup group mapping for JavaScript."""
        from .models import PickupGroup
        pickup_group_ids = [int(gid) for gid in availability_dates_by_region.keys()]
        pickup_groups = PickupGroup.objects.filter(id__in=pickup_group_ids).values('id', 'name')
        return {str(g['id']): g['name'] for g in pickup_groups}


def create_reservation(booking_data):
    """Create a reservation from booking data."""
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
            date_to_full = booking_data.get("DateTo")
            date_to = date_to_full.split("T")[0]

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
