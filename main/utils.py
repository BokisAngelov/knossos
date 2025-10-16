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
        """Handle voucher/reservation lookup or creation using VoucherService."""
        if not voucher_id:
            return None
        
        try:
            # Use VoucherService for consistent voucher handling
            reservation, _ = VoucherService.authenticate_voucher(voucher_id)
            return reservation
        except ValidationError:
            # Voucher is invalid or expired
            return None
    
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
                      voucher_instance, selected_date, availability_id, pickup_point=None):
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
            pickup_point=pickup_point,
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


class VoucherService:
    """Service class for handling voucher/reservation authentication and validation."""
    
    @staticmethod
    def authenticate_voucher(voucher_code):
        """
        Main entry point - authenticate voucher and get or create reservation.
        
        Args:
            voucher_code: The booking ID / voucher code
            
        Returns:
            tuple: (reservation, created) where created is True if fetched from API
            
        Raises:
            ValidationError: If voucher is invalid or expired
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not voucher_code:
            raise ValidationError('Voucher code is required.')
        
        # First, try to get from database
        try:
            # Only select_related on client_profile if it exists (migrations may not be run)
            try:
                reservation = Reservation.objects.select_related(
                    'pickup_group', 'pickup_point', 'hotel', 'client_profile'
                ).get(voucher_id=voucher_code)
            except Exception:
                # Fallback without client_profile if field doesn't exist
                reservation = Reservation.objects.select_related(
                    'pickup_group', 'pickup_point', 'hotel'
                ).get(voucher_id=voucher_code)
            
            # Validate reservation status and expiration
            from django.utils import timezone
            from datetime import date, datetime
            
            # Check status field (this always exists)
            if reservation.status != 'active':
                raise ValidationError('This reservation is not active.')
            
            # Check if expired (check_out date has passed)
            # Handle both date objects and strings
            checkout_date = reservation.check_out
            if isinstance(checkout_date, str):
                try:
                    checkout_date = datetime.strptime(checkout_date, '%Y-%m-%d').date()
                except:
                    checkout_date = datetime.fromisoformat(checkout_date).date()
            
            # if checkout_date < timezone.now().date():
            #     raise ValidationError('This voucher has expired.')
            
            logger.info(f"Voucher {voucher_code} found in database")
            
            # Update last_used_at if field exists in database
            try:
                if hasattr(reservation, 'last_used_at'):
                    reservation.last_used_at = timezone.now()
                    reservation.save(update_fields=['last_used_at'])
            except Exception as e:
                # Field doesn't exist in database yet (migrations not run)
                logger.debug(f"Could not update last_used_at (migrations may not be applied): {str(e)}")
                pass
            
            return reservation, False
            
        except Reservation.DoesNotExist:
            # Not in database, fetch from API
            logger.info(f"Voucher {voucher_code} not in database, fetching from API")
            return VoucherService._create_from_api(voucher_code)
    
    @staticmethod
    @transaction.atomic
    def _create_from_api(voucher_code):
        """
        Fetch reservation from Cyberlogic API and create local record.
        This will trigger the signal to auto-create User and UserProfile.
        
        Args:
            voucher_code: The booking ID to fetch
            
        Returns:
            tuple: (reservation, True)
            
        Raises:
            ValidationError: If API call fails or data is invalid
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            from .cyber_api import get_reservation
            api_data = get_reservation(voucher_code)
            
            if not api_data:
                raise ValidationError('Voucher not found. Please check your booking ID.')
            
            # Create reservation using existing function
            reservation, response_data = create_reservation(api_data)
            
            if not reservation:
                error_msg = response_data.get('message', 'Failed to create reservation')
                raise ValidationError(error_msg)
            
            logger.info(f"Voucher {voucher_code} created from API")
            
            # Set first_used_at and last_used_at if fields exist in database
            try:
                if hasattr(reservation, 'first_used_at') and hasattr(reservation, 'last_used_at'):
                    from django.utils import timezone
                    reservation.first_used_at = timezone.now()
                    reservation.last_used_at = timezone.now()
                    reservation.save(update_fields=['first_used_at', 'last_used_at'])
            except Exception as e:
                # Fields don't exist in database yet (migrations not run)
                logger.debug(f"Could not update usage timestamps (migrations may not be applied): {str(e)}")
                pass
            
            return reservation, True
            
        except Exception as e:
            logger.error(f"Error creating reservation from API for {voucher_code}: {str(e)}")
            if isinstance(e, ValidationError):
                raise
            raise ValidationError(f'Error retrieving voucher: {str(e)}')
    
    @staticmethod
    def validate_for_booking(reservation, booking_date):
        """
        Validate that a reservation can be used for a booking on a specific date.
        
        Args:
            reservation: Reservation instance
            booking_date: Date object or date string
            
        Returns:
            bool: True if valid
            
        Raises:
            ValidationError: If validation fails
        """
        from datetime import datetime
        
        # Convert string to date if needed
        if isinstance(booking_date, str):
            booking_date = datetime.strptime(booking_date, '%Y-%m-%d').date()
        
        # Check if reservation is active
        if reservation.status != 'active':
            raise ValidationError('This reservation is not active.')
        
        # Check if booking date is within reservation period
        if booking_date < reservation.check_in:
            raise ValidationError(
                f'Booking date ({booking_date}) is before your check-in date ({reservation.check_in}).'
            )
        
        if booking_date > reservation.check_out:
            raise ValidationError(
                f'Booking date ({booking_date}) is after your check-out date ({reservation.check_out}).'
            )
        
        return True
    
    @staticmethod
    def get_voucher_data(reservation):
        """
        Get formatted voucher data for JSON responses.
        
        Args:
            reservation: Reservation instance
            
        Returns:
            dict: Formatted voucher data
        """
        from datetime import date
        
        # Helper function to convert date to ISO format string
        def date_to_iso(date_value):
            if isinstance(date_value, str):
                return date_value  # Already a string
            elif hasattr(date_value, 'isoformat'):
                return date_value.isoformat()  # Date object
            else:
                return str(date_value)  # Fallback
        
        # Helper function to convert date string/object to date for comparison
        def ensure_date(date_value):
            if isinstance(date_value, date):
                return date_value
            elif isinstance(date_value, str):
                from datetime import datetime
                try:
                    return datetime.strptime(date_value, '%Y-%m-%d').date()
                except:
                    return datetime.fromisoformat(date_value).date()
            else:
                return date_value
        
        # Use getattr with defaults for fields that might not exist yet
        data = {
            'client_name': reservation.client_name,
            'client_email': reservation.client_email or '',
            'pickup_group_id': reservation.pickup_group.id if reservation.pickup_group else None,
            'pickup_point_id': reservation.pickup_point.id if reservation.pickup_point else None,
            'pickup_group_name': reservation.pickup_group.name if reservation.pickup_group else '',
            'pickup_point_name': reservation.pickup_point.name if reservation.pickup_point else '',
            'check_in': date_to_iso(reservation.check_in),
            'check_out': date_to_iso(reservation.check_out),
        }
        
        # Check validity using status and check_out fields (always exist)
        from django.utils import timezone
        checkout_date = ensure_date(reservation.check_out)
        data['is_valid'] = (
            reservation.status == 'active' and
            checkout_date >= timezone.now().date()
        )
        
        if hasattr(reservation, 'get_bookings_count'):
            data['total_bookings'] = reservation.get_bookings_count()
        else:
            data['total_bookings'] = reservation.bookings.count() if hasattr(reservation, 'bookings') else 0
        
        return data
    
    @staticmethod
    def clear_voucher_cookies(response=None):
        """
        Clear all voucher-related cookies.
        
        Args:
            response: JsonResponse object (optional)
            
        Returns:
            JsonResponse with cookies deleted
        """
        from django.http import JsonResponse
        
        if response is None:
            response = JsonResponse({
                'success': True,
                'message': 'Voucher cleared successfully.'
            })
        
        response.delete_cookie('voucher_code')
        response.delete_cookie('pickup_group')
        response.delete_cookie('pickup_point')
        
        return response


class TransportGroupService:
    """Service class for handling transportation group operations."""
    
    @staticmethod
    def get_completed_bookings_for_grouping(excursion=None, date=None, exclude_group_id=None):
        """
        Get completed bookings available for grouping.
        
        Args:
            excursion: Excursion instance to filter by
            date: Date to filter by
            exclude_group_id: Group ID to exclude bookings from (for editing)
            
        Returns:
            QuerySet of Booking objects ordered by pickup_group and pickup_point
        """
        from django.db.models import Q
        
        bookings = Booking.objects.filter(
            payment_status='completed'
        ).select_related(
            'pickup_point', 
            'pickup_point__pickup_group',
            'excursion_availability',
            'excursion_availability__excursion'
        ).order_by(
            'pickup_point__pickup_group__name',
            'pickup_point__name'
        )
        
        if excursion:
            bookings = bookings.filter(excursion_availability__excursion=excursion)
        
        if date:
            bookings = bookings.filter(date=date)
        
        # Exclude bookings already in other groups
        if exclude_group_id:
            bookings = bookings.filter(
                Q(transport_groups__isnull=True) | Q(transport_groups__id=exclude_group_id)
            )
        else:
            bookings = bookings.filter(transport_groups__isnull=True)
        
        return bookings
    
    @staticmethod
    def group_bookings_by_pickup(bookings):
        """
        Group bookings by pickup group and pickup point.
        
        Args:
            bookings: QuerySet of Booking objects
            
        Returns:
            dict: Nested structure {pickup_group: {pickup_point: [bookings]}}
        """
        from collections import defaultdict
        
        grouped = defaultdict(lambda: defaultdict(list))
        
        for booking in bookings:
            pickup_group = booking.pickup_point.pickup_group if booking.pickup_point else None
            pickup_point = booking.pickup_point
            
            group_key = pickup_group.name if pickup_group else 'No Pickup Group'
            point_key = pickup_point.name if pickup_point else 'No Pickup Point'
            
            grouped[group_key][point_key].append(booking)
        
        return dict(grouped)
    
    @staticmethod
    def calculate_booking_guests(booking):
        """Calculate total guests for a booking."""
        return (booking.total_adults or 0) + (booking.total_kids or 0) + (booking.total_infants or 0)
    
    @staticmethod
    def calculate_total_guests(booking_ids):
        """Calculate total guests from a list of booking IDs."""
        bookings = Booking.objects.filter(id__in=booking_ids)
        total = 0
        for booking in bookings:
            total += TransportGroupService.calculate_booking_guests(booking)
        return total
    
    @staticmethod
    def get_pickup_group_summary(bookings):
        """
        Get summary of bookings grouped by pickup group with totals.
        
        Returns:
            list: [{
                'pickup_group': PickupGroup instance,
                'pickup_point_summaries': [{
                    'pickup_point': PickupPoint instance,
                    'bookings': [Booking instances],
                    'total_guests': int,
                    'booking_count': int
                }],
                'total_guests': int,
                'booking_count': int
            }]
        """
        grouped = TransportGroupService.group_bookings_by_pickup(bookings)
        summary = []
        
        for group_name, points in grouped.items():
            group_total_guests = 0
            group_booking_count = 0
            point_summaries = []
            
            for point_name, point_bookings in points.items():
                point_total = sum(
                    TransportGroupService.calculate_booking_guests(b) 
                    for b in point_bookings
                )
                
                point_summaries.append({
                    'pickup_point_name': point_name,
                    'pickup_point': point_bookings[0].pickup_point if point_bookings else None,
                    'bookings': point_bookings,
                    'total_guests': point_total,
                    'booking_count': len(point_bookings)
                })
                
                group_total_guests += point_total
                group_booking_count += len(point_bookings)
            
            # Get the actual pickup_group instance from first booking
            first_booking = next(
                (b for points in points.values() for b in points if b.pickup_point), 
                None
            )
            pickup_group = first_booking.pickup_point.pickup_group if first_booking and first_booking.pickup_point else None
            
            summary.append({
                'pickup_group_name': group_name,
                'pickup_group': pickup_group,
                'pickup_point_summaries': point_summaries,
                'total_guests': group_total_guests,
                'booking_count': group_booking_count
            })
        
        return summary


class RevenueAnalyticsService:
    """Service class for handling revenue analytics operations."""
    
    @staticmethod
    def get_revenue_data(start_date, end_date):
        """
        Process revenue analytics data for a date range.
        
        Args:
            start_date: Starting date of the range
            end_date: Ending date of the range
            
        Returns:
            dict: Comprehensive revenue analytics data
        """
        from django.db.models import Sum, Count, Q, Avg
        from decimal import Decimal
        
        # Get all completed bookings in the date range
        bookings = Booking.objects.filter(
            payment_status='completed',
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).select_related(
            'excursion_availability',
            'excursion_availability__excursion',
            'excursion_availability__excursion__provider',
            'excursion_availability__excursion__guide'
        )
        
        # Total revenue metrics
        total_revenue = bookings.aggregate(total=Sum('total_price'))['total'] or Decimal('0')
        total_bookings = bookings.count()
        average_booking_value = bookings.aggregate(avg=Avg('total_price'))['avg'] or Decimal('0')
        
        # Partial payments
        partial_payments = bookings.exclude(
            Q(partial_paid__isnull=True) | Q(partial_paid=0)
        ).aggregate(
            total=Sum('partial_paid'),
            count=Count('id')
        )
        total_partial_payments = partial_payments['total'] or Decimal('0')
        partial_payments_count = partial_payments['count'] or 0
        
        # Payment method breakdown
        cash_revenue = bookings.filter(partial_paid_method='cash').aggregate(
            total=Sum('partial_paid')
        )['total'] or Decimal('0')
        
        card_revenue = bookings.filter(partial_paid_method='card').aggregate(
            total=Sum('partial_paid')
        )['total'] or Decimal('0')
        
        # Revenue by excursion (Top 10)
        revenue_by_excursion = []
        excursion_data = bookings.values(
            'excursion_availability__excursion__id',
            'excursion_availability__excursion__title'
        ).annotate(
            revenue=Sum('total_price'),
            booking_count=Count('id')
        ).order_by('-revenue')[:10]
        
        for item in excursion_data:
            revenue_by_excursion.append({
                'excursion_id': item['excursion_availability__excursion__id'],
                'excursion_title': item['excursion_availability__excursion__title'],
                'revenue': item['revenue'],
                'bookings': item['booking_count']
            })
        
        # Revenue by provider
        revenue_by_provider = []
        provider_data = bookings.exclude(
            excursion_availability__excursion__provider__isnull=True
        ).values(
            'excursion_availability__excursion__provider__id',
            'excursion_availability__excursion__provider__name'
        ).annotate(
            revenue=Sum('total_price'),
            booking_count=Count('id')
        ).order_by('-revenue')[:10]
        
        for item in provider_data:
            revenue_by_provider.append({
                'provider_id': item['excursion_availability__excursion__provider__id'],
                'provider_name': item['excursion_availability__excursion__provider__name'],
                'revenue': item['revenue'],
                'bookings': item['booking_count']
            })
        
        # Revenue by guide
        revenue_by_guide = []
        guide_data = bookings.exclude(
            excursion_availability__excursion__guide__isnull=True
        ).values(
            'excursion_availability__excursion__guide__id',
            'excursion_availability__excursion__guide__name'
        ).annotate(
            revenue=Sum('total_price'),
            booking_count=Count('id')
        ).order_by('-revenue')[:10]
        
        for item in guide_data:
            revenue_by_guide.append({
                'guide_id': item['excursion_availability__excursion__guide__id'],
                'guide_name': item['excursion_availability__excursion__guide__name'],
                'revenue': item['revenue'],
                'bookings': item['booking_count']
            })
        
        # Daily revenue breakdown
        from datetime import timedelta
        daily_revenue = []
        current_date = start_date
        while current_date <= end_date:
            day_bookings = bookings.filter(created_at__date=current_date)
            day_revenue = day_bookings.aggregate(total=Sum('total_price'))['total'] or Decimal('0')
            day_count = day_bookings.count()
            
            daily_revenue.append({
                'date': current_date,
                'revenue': day_revenue,
                'bookings': day_count
            })
            current_date += timedelta(days=1)
        
        return {
            'total_revenue': total_revenue,
            'total_bookings': total_bookings,
            'average_booking_value': average_booking_value,
            'total_partial_payments': total_partial_payments,
            'partial_payments_count': partial_payments_count,
            'cash_revenue': cash_revenue,
            'card_revenue': card_revenue,
            'revenue_by_excursion': revenue_by_excursion,
            'revenue_by_provider': revenue_by_provider,
            'revenue_by_guide': revenue_by_guide,
            'daily_revenue': daily_revenue,
        }


class ExcursionAnalyticsService:
    """Service class for handling excursion analytics operations."""
    
    @staticmethod
    def get_analytics_data(start_date, end_date):
        """
        Process excursion analytics data for a date range.
        
        Args:
            start_date: Starting date of the range
            end_date: Ending date of the range
            
        Returns:
            dict: {
                'date_range': list of all date objects in range,
                'availabilities': list of availability data with bookings per day
            }
        """
        from datetime import timedelta
        from django.db.models import Q
        
        # Generate full list of dates in range (all dates, not just availability days)
        date_range = []
        current_date = start_date
        while current_date <= end_date:
            date_range.append(current_date)
            current_date += timedelta(days=1)
        
        # Get all AvailabilityDays within the date range
        availability_days_in_range = AvailabilityDays.objects.filter(
            date_day__gte=start_date,
            date_day__lte=end_date
        ).select_related('excursion_availability', 'excursion_availability__excursion')
        
        # Get unique availabilities that have days in this range
        availability_ids = set(
            av_day.excursion_availability_id for av_day in availability_days_in_range
        )
        
        availabilities = ExcursionAvailability.objects.filter(
            id__in=availability_ids
        ).select_related('excursion').prefetch_related(
            'availability_days',
            'bookings'
        ).order_by('excursion__title', 'start_time')
        
        analytics_data = []
        
        for availability in availabilities:
            # Create display name for this availability
            time_str = availability.start_time.strftime('%H:%M') if availability.start_time else 'No Time'
            # display_name = f"{availability.pickup_groups.all().first().name} - {time_str}"
            display_name = "("
            for pickup_group in availability.pickup_groups.all():
                display_name += f"{pickup_group.name}, "
            display_name = display_name[:-2]
            display_name += ")"
            
            # Build data for each date in the full date range
            date_data = {}
            for date in date_range:
                # Try to get AvailabilityDays for this specific date and availability
                try:
                    day_availability = availability.availability_days.get(date_day=date)
                    capacity = day_availability.capacity
                    
                    # Count completed bookings for this date
                    bookings_count = availability.bookings.filter(
                        date=date,
                        payment_status='completed'
                    ).count()
                    
                    date_data[date] = {
                        'bookings': bookings_count,
                        'capacity': capacity
                    }
                except AvailabilityDays.DoesNotExist:
                    # This availability doesn't have a day for this date
                    date_data[date] = None
            
            analytics_data.append({
                'availability_id': availability.id,
                'display_name': display_name,
                'excursion': availability.excursion,
                'date_data': date_data
            })
        
        return {
            'date_range': date_range,
            'availabilities': analytics_data
        }


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
            date_to_full = booking_data.get("DateTo")
            
            # Validate required date fields
            if not date_from_full or not date_to_full:
                raise ValidationError('Missing required date information in reservation data.')
            
            date_from = date_from_full.split("T")[0]
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
