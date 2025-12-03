from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import (
    Excursion, Feedback, Booking, Reservation, 
    AvailabilityDays, ExcursionAvailability, PickupPoint, Hotel, Region, JCCGatewayConfig, EmailSettings
)
from .cyber_api import get_reservation
from datetime import datetime
import requests
import logging

logger = logging.getLogger(__name__)


class AvailabilityValidationService:
    """Service class for handling availability validation logic."""
    
    @staticmethod
    def check_overlap(excursion, start_date, end_date, regions, pickup_points, current_availability_id=None):
        """
        Check if an availability conflicts with existing availabilities.
        
        A conflict occurs when:
        1. Same excursion
        2. Overlapping date ranges
        3. ANY overlapping regions
        4. ANY overlapping pickup points
        
        Args:
            excursion: Excursion instance or ID
            start_date: Start date (date object or string)
            end_date: End date (date object or string)
            regions: List of region IDs
            pickup_points: List of pickup point IDs
            current_availability_id: ID to exclude from check (for updates)
            
        Returns:
            tuple: (has_conflict: bool, error_details: list)
        """
        if not excursion or not start_date or not end_date:
            return False, []
        
        # Convert to date objects if strings
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Convert regions and pickup_points to sets of integers
        region_ids = set(int(r) if not isinstance(r, int) else r for r in regions if r)
        pickup_point_ids = set(int(p) if not isinstance(p, int) else p for p in pickup_points if p)
        
        if not region_ids or not pickup_point_ids:
            return False, []
        
        # Get excursion ID
        excursion_id = excursion.id if hasattr(excursion, 'id') else excursion
        
        # Get all active availabilities for this excursion with overlapping dates
        overlapping_availabilities = ExcursionAvailability.objects.filter(
            excursion_id=excursion_id,
            start_date__lte=end_date,
            end_date__gte=start_date,
            status='active'
        ).prefetch_related('regions', 'pickup_points')
        
        if current_availability_id:
            overlapping_availabilities = overlapping_availabilities.exclude(pk=current_availability_id)
        
        # Check each overlapping availability for conflicts
        error_details = []
        has_conflict = False
        
        for avail in overlapping_availabilities:
            existing_regions = set(avail.regions.values_list('id', flat=True))
            existing_pickup_points = set(avail.pickup_points.values_list('id', flat=True))
            
            # Check for overlapping regions
            overlapping_regions = existing_regions & region_ids
            # Check for overlapping pickup points
            overlapping_pickup_points = existing_pickup_points & pickup_point_ids
            
            # Conflict only if BOTH regions AND pickup points overlap
            if overlapping_regions and overlapping_pickup_points:
                has_conflict = True
                
                # Get region and pickup point names for detailed error message
                region_names = Region.objects.filter(
                    id__in=overlapping_regions
                ).values_list('name', flat=True)
                
                point_names = PickupPoint.objects.filter(
                    id__in=overlapping_pickup_points
                ).values_list('name', flat=True)
                
                error_details.append(
                    f"Conflict with availability #{avail.id} ({avail.start_date} to {avail.end_date}): "
                    f"Regions ({', '.join(region_names)}), "
                    f"Pickup Points ({', '.join(point_names)})"
                )
        
        return has_conflict, error_details
    
    @staticmethod
    def get_conflicting_regions(excursion_id, start_date, end_date, current_availability_id=None):
        """
        Get regions that are already used in overlapping availabilities.
        
        Args:
            excursion_id: Excursion ID
            start_date: Start date
            end_date: End date
            current_availability_id: ID to exclude from check (for updates)
            
        Returns:
            set: Set of region IDs that are conflicting
        """
        if not excursion_id or not start_date or not end_date:
            return set()
        
        # Convert to date objects if strings
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # Get all regions that are already used in overlapping availabilities
        overlapping_availabilities = ExcursionAvailability.objects.filter(
            excursion_id=excursion_id,
            start_date__lte=end_date,
            end_date__gte=start_date,
            status='active'
        )
        
        if current_availability_id:
            overlapping_availabilities = overlapping_availabilities.exclude(pk=current_availability_id)
        
        # Get all region IDs that are used in overlapping availabilities
        used_region_ids = set()
        for avail in overlapping_availabilities:
            used_region_ids.update(avail.regions.values_list('id', flat=True))
        
        return used_region_ids
    
    @staticmethod
    def validate_date_range(start_date, end_date):
        """
        Validate that date range is logical.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Raises:
            ValidationError: If date range is invalid
        """
        if not start_date or not end_date:
            raise ValidationError('Start date and end date are required.')
        
        # Convert to date objects if strings
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        if end_date < start_date:
            raise ValidationError('End date cannot be before start date.')
    
    @staticmethod
    def validate_availability_requirements(regions, pickup_points, weekdays):
        """
        Validate that availability has minimum required data.
        
        Args:
            regions: List of region IDs
            pickup_points: List of pickup point IDs
            weekdays: List of weekday IDs
            
        Raises:
            ValidationError: If required data is missing
        """
        if not regions or len(regions) == 0:
            raise ValidationError('At least one region must be selected.')
        
        if not pickup_points or len(pickup_points) == 0:
            raise ValidationError('At least one pickup point must be selected.')
        
        if not weekdays or len(weekdays) == 0:
            raise ValidationError('At least one weekday must be selected.')


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
    def calculate_referral_discount(base_price, referral_code_obj):
        """
        Calculate referral discount amount.
        
        Args:
            base_price: Original price before any discounts (Decimal)
            referral_code_obj: ReferralCode instance
            
        Returns:
            dict: Contains discount_amount and discounted_price
        """
        from decimal import Decimal
        
        if not referral_code_obj or not referral_code_obj.discount:
            return {
                'discount_amount': Decimal('0'),
                'discounted_price': base_price
            }
        
        # Convert to Decimal for proper calculation
        base_price_decimal = Decimal(str(base_price))
        discount_percentage = Decimal(str(referral_code_obj.discount))
        
        # Calculate discount
        discount_amount = (base_price_decimal * discount_percentage) / Decimal('100')
        discounted_price = base_price_decimal - discount_amount
        
        return {
            'discount_amount': discount_amount.quantize(Decimal('0.01')),
            'discounted_price': discounted_price.quantize(Decimal('0.01'))
        }
    
    @staticmethod
    def calculate_pricing(base_price, referral_discount_amount, partial_price):
        """
        Calculate final pricing with referral discount and partial payment.
        
        Calculation order:
        1. Base Price
        2. Apply Referral Discount
        3. Apply Partial Payment
        
        Args:
            base_price: Original price before any discounts (Decimal)
            referral_discount_amount: Amount discounted from referral code (Decimal)
            partial_price: Amount already paid (int/Decimal)
            
        Returns:
            dict: Contains total_price (final amount to pay) and partial_paid
        """
        from decimal import Decimal
        
        # Ensure everything is Decimal
        base_price_decimal = Decimal(str(base_price))
        discount_amount_decimal = Decimal(str(referral_discount_amount or 0))
        partial_price_decimal = Decimal(str(partial_price or 0))
        
        # Step 1: Apply referral discount
        discounted_price = base_price_decimal - discount_amount_decimal
        
        # Step 2: Apply partial payment
        if partial_price_decimal > 0:
            final_price = discounted_price - partial_price_decimal
            return {
                'total_price': final_price.quantize(Decimal('0.01')),
                'partial_paid': partial_price_decimal.quantize(Decimal('0.01'))
            }
        else:
            return {
                'total_price': discounted_price.quantize(Decimal('0.01')),
                'partial_paid': Decimal('0') if partial_price else None
            }
    
    @staticmethod
    def handle_referral_code(referral_code_str):
        """
        Handle referral code lookup and validation.
        
        Args:
            referral_code_str: Referral code string
            
        Returns:
            ReferralCode instance or None
        """
        if not referral_code_str:
            return None
        
        try:
            from .models import ReferralCode
            code = ReferralCode.objects.get(
                code=referral_code_str.strip().upper(),
                status='active'
            )
            
            # Check if expired
            if code.is_expired:
                code.status = 'inactive'
                code.save()
                return None
            
            return code
        except ReferralCode.DoesNotExist:
            return None
    
    @staticmethod
    @transaction.atomic
    def create_booking(user, excursion_availability, booking_data, guest_data, 
                      voucher_instance, selected_date, availability_id, pickup_point=None):
        """
        Create a booking with all related operations.
        Note: Referral codes are applied later at checkout.
        """
        # Validate remaining seats
        remaining_seats = BookingService.get_remaining_seats(
            excursion_availability, selected_date
        )
        
        if booking_data['total_guests'] > remaining_seats:
            raise ValidationError(
                f'The selected date has not enough seats available. Remaining seats: {remaining_seats}'
            )
        
        # Calculate pricing (without referral discount for now)
        base_price = booking_data['total_price']
        pricing_data = BookingService.calculate_pricing(
            base_price,
            0,  # No referral discount yet
            booking_data['partial_price']
        )
        
        # Generate access token for non-logged-in users
        access_token = None
        if not user or not user.is_authenticated:
            # Generate a unique token
            import secrets
            while True:
                token = secrets.token_urlsafe(32)
                # Check if token already exists (very unlikely, but be safe)
                if not Booking.objects.filter(access_token=token).exists():
                    access_token = token
                    break
        
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
            price=base_price,
            pickup_point=pickup_point,
            access_token=access_token,
            **pricing_data
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
    
    @staticmethod
    @transaction.atomic
    def apply_referral_code_to_booking(booking, referral_code_instance):
        """
        Apply a referral code to an existing booking and recalculate pricing.
        
        Args:
            booking: Booking instance
            referral_code_instance: ReferralCode instance
            
        Returns:
            Updated booking instance
        """
        if not referral_code_instance:
            raise ValidationError('Invalid referral code.')
        
        # Get base price
        base_price = booking.price
        
        # Calculate referral discount
        referral_discount_data = BookingService.calculate_referral_discount(
            base_price,
            referral_code_instance
        )
        
        # Calculate new final pricing
        pricing_data = BookingService.calculate_pricing(
            base_price,
            referral_discount_data['discount_amount'],
            booking.partial_paid or 0
        )
        
        # Update booking
        booking.referral_code = referral_code_instance
        booking.referral_discount_amount = referral_discount_data['discount_amount']
        booking.total_price = pricing_data['total_price']
        booking.save()
        
        return booking


class ExcursionService:
    """Service class for handling excursion-related operations."""
    
    @staticmethod
    def get_availability_data(excursion_availabilities):
        """
        Process excursion availabilities and return structured data organized by region.
        
        Returns:
            tuple: (availability_dates_by_region, pickup_points_by_region, region_availability_map)
                - availability_dates_by_region: dict with region_id as key, containing dates and availability_id
                - pickup_points_by_region: dict with region_id as key, containing pickup points from availability
                - region_availability_map: dict mapping region_id to availability details (prices, pickup_points)
        """
        availability_dates_by_region = {}
        pickup_points_by_region = {}
        region_availability_map = {}
        
        for availability in excursion_availabilities:
            # Get all regions for this availability
            regions = availability.regions.all()
            
            # Get all availability days for this availability
            days = availability.availability_days.filter(status='active')
            
            # Get all pickup points for this availability
            pickup_points = availability.pickup_points.all().order_by('name')
            pickup_points_list = list(pickup_points.values('id', 'name'))
            pickup_start_time = availability.pickup_start_time.strftime('%H:%M') if availability.pickup_start_time else None
            pickup_end_time = availability.pickup_end_time.strftime('%H:%M') if availability.pickup_end_time else None
            
            # Prepare availability details
            availability_details = {
                'id': availability.id,
                'adult_price': float(availability.adult_price) if availability.adult_price else 0,
                'child_price': float(availability.child_price) if availability.child_price else 0,
                'infant_price': float(availability.infant_price) if availability.infant_price else 0,
                'pickup_points': pickup_points_list,
                'pickup_start_time': pickup_start_time,
                'pickup_end_time': pickup_end_time,
                'max_guests': availability.max_guests,
                'booked_guests': availability.booked_guests,
            }
            
            # Process each region
            for region in regions:
                region_id = str(region.id)
                
                # Convert queryset to list of dicts with availability_id
                date_entries = [
                    {
                        "date": day.date_day.isoformat(), 
                        "id": day.id,
                        "availability_id": availability.id
                    }
                    for day in days
                ]
                
                # Add dates for this region
                if region_id not in availability_dates_by_region:
                    availability_dates_by_region[region_id] = []
                availability_dates_by_region[region_id].extend(date_entries)
                
                # Add pickup points for this region (flattened - same points for all regions of same availability)
                if region_id not in pickup_points_by_region:
                    pickup_points_by_region[region_id] = pickup_points_list
                
                # Map region to availability details
                if region_id not in region_availability_map:
                    region_availability_map[region_id] = []
                region_availability_map[region_id].append(availability_details)
        
        return availability_dates_by_region, pickup_points_by_region, region_availability_map
    
    @staticmethod
    def get_region_map(availability_dates_by_region):
        """Get region mapping for JavaScript."""
        from .models import Region
        region_ids = [int(rid) for rid in availability_dates_by_region.keys()]
        regions = Region.objects.filter(id__in=region_ids).values('id', 'name')
        return {str(r['id']): r['name'] for r in regions}


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
            'user',
            'user__profile'
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
        
        # Revenue by representative
        revenue_by_representative = []
        representative_data = bookings.exclude(
            Q(user__isnull=True) | Q(user__profile__isnull=True)
        ).filter(
            user__profile__role='representative'
        ).values(
            'user__profile__id',
            'user__profile__name'
        ).annotate(
            revenue=Sum('total_price'),
            booking_count=Count('id')
        ).order_by('-revenue')[:10]
        
        for item in representative_data:
            revenue_by_representative.append({
                'representative_id': item['user__profile__id'],
                'representative_name': item['user__profile__name'],
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
            'revenue_by_representative': revenue_by_representative,
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


class JCCPaymentService:
    """
    Service class for handling JCC Payment Gateway API interactions.
    Handles order registration and status verification.
    """
    
    @staticmethod
    def get_config():
        """
        Get the active JCC gateway configuration.
        
        Returns:
            JCCGatewayConfig instance or None if no active config exists.
        
        Raises:
            ValidationError: If no active configuration is found.
        """
        config = JCCGatewayConfig.get_active_config()
        if not config:
            raise ValidationError(
                "No active JCC gateway configuration found. "
                "Please configure JCC gateway settings in the admin panel."
            )
        return config
    
    @staticmethod
    def register_order(booking, return_url, fail_url=None, description=None, language=None, use_unique_order_number=False):
        """
        Register an order with JCC Payment Gateway.
        
        Args:
            booking: Booking instance
            return_url: URL to redirect after successful payment
            fail_url: URL to redirect after failed payment (optional)
            description: Order description (optional)
            language: Language code (optional, uses config default if not provided)
            use_unique_order_number: If True, use a timestamp-based unique order number to avoid duplicates
        
        Returns:
            dict: Response containing 'orderId' and 'formUrl' on success
        
        Raises:
            ValidationError: If registration fails or config is missing
            Exception: For network or other errors
        """
        config = JCCPaymentService.get_config()
        
        # Calculate amount in minor currency units (e.g., cents for EUR)
        # JCC expects amount in minor units (e.g., 2000 for 20.00 EUR)
        amount = booking.get_final_price
        amount_minor = int(amount * 100)  # Convert to cents/minor units
        
        # Prepare order number
        # If use_unique_order_number is True, append timestamp to avoid duplicate order numbers
        if use_unique_order_number:
            from datetime import datetime
            timestamp = int(datetime.now().timestamp())
            order_number = f"{booking.id}_{timestamp}"
        else:
            order_number = str(booking.id)
        
        # Prepare request data
        data = {
            'amount': amount_minor,
            'currency': config.default_currency,
            'userName': config.username,
            'password': config.password,
            'orderNumber': order_number,
            'returnUrl': return_url,
            'description': description or f"Booking #{booking.id}",
            'language': language or config.default_language,
        }
        
        # Add failUrl if provided
        if fail_url:
            data['failUrl'] = fail_url
        
        try:
            logger.info(f"Registering JCC order for booking #{booking.id}, amount: {amount_minor}")
            
            response = requests.post(
                config.register_url,
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=30
            )
            response.raise_for_status()
            
            # Parse response
            response_data = response.json()
            
            # Log full response for debugging
            logger.info(f"JCC registration response: {response_data}")
            
            # Check for errors in response
            # JCC returns errorCode: 0 (or missing) for success, non-zero for errors
            # errorCode might be integer or string, so we need to handle both
            error_code = response_data.get('errorCode')
            
            # Convert to int if it's a string
            if isinstance(error_code, str):
                try:
                    error_code = int(error_code)
                except (ValueError, TypeError):
                    error_code = None
            
            # Only treat as error if errorCode exists and is non-zero
            # errorCode: 0 or missing means success
            if error_code is not None and error_code != 0:
                error_message = response_data.get('errorMessage', 'Unknown error')
                logger.error(f"JCC registration error: {error_message} (code: {error_code})")
                raise ValidationError(f"JCC payment registration failed: {error_message}")
            
            # Validate required fields in response
            if 'orderId' not in response_data or 'formUrl' not in response_data:
                logger.error(f"Invalid JCC response: {response_data}")
                raise ValidationError("Invalid response from JCC payment gateway")
            
            logger.info(f"JCC order registered successfully: orderId={response_data['orderId']}")
            
            return response_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during JCC registration: {str(e)}")
            raise Exception(f"Failed to connect to JCC payment gateway: {str(e)}")
        except ValueError as e:
            logger.error(f"Invalid JSON response from JCC: {str(e)}")
            raise ValidationError("Invalid response format from JCC payment gateway")
    
    @staticmethod
    def get_order_status(order_id):
        """
        Get the status of an order from JCC Payment Gateway.
        
        Args:
            order_id: JCC order ID (orderId from register.do response)
        
        Returns:
            dict: Order status information including 'orderStatus' and 'actionCode'
        
        Raises:
            ValidationError: If status check fails or config is missing
            Exception: For network or other errors
        """
        config = JCCPaymentService.get_config()
        
        data = {
            'userName': config.username,
            'password': config.password,
            'orderId': order_id,
        }
        
        try:
            logger.info(f"Checking JCC order status for orderId: {order_id}")
            
            response = requests.post(
                config.status_url,
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=30
            )
            response.raise_for_status()
            
            # Parse response
            response_data = response.json()
            
            # Log full response for debugging
            logger.info(f"JCC status check response: {response_data}")
            
            # Check for errors in response
            # JCC returns errorCode: 0 (or missing) for success, non-zero for errors
            # errorCode might be integer or string, so we need to handle both
            error_code = response_data.get('errorCode')
            error_message = response_data.get('errorMessage', '')
            
            # Convert to int if it's a string
            if isinstance(error_code, str):
                try:
                    error_code = int(error_code)
                except (ValueError, TypeError):
                    error_code = None
            
            # Only treat as error if errorCode exists and is non-zero
            # errorCode: 0 or missing means success
            # IMPORTANT: errorMessage: "Success" with errorCode: 0 is a SUCCESS response, not an error!
            # We should NOT raise an error if errorCode is 0, regardless of errorMessage content
            if error_code is not None:
                if error_code == 0:
                    # errorCode: 0 means success, even if errorMessage exists
                    logger.info(f"JCC response indicates success (errorCode: 0, errorMessage: {error_message})")
                elif error_code != 0:
                    # Only raise error if errorCode is non-zero
                    logger.error(f"JCC status check error: {error_message} (code: {error_code})")
                    raise ValidationError(f"JCC payment status check failed: {error_message}")
            
            # If we get here, errorCode is 0 or missing, which means success
            # Check if we have orderStatus in the response (required for status check)
            if 'orderStatus' not in response_data:
                logger.warning(f"JCC status response missing orderStatus field: {response_data}")
                # Don't fail here - maybe the response structure is different
                # Let is_payment_successful handle it
            
            # If errorCode is 0 or missing, it's a successful response
            # Even if errorMessage says "Success", that's fine - it's not an error
            logger.info(
                f"JCC order status retrieved successfully: "
                f"orderStatus={response_data.get('orderStatus')}, "
                f"actionCode={response_data.get('actionCode')}, "
                f"errorCode={error_code}, "
                f"errorMessage={response_data.get('errorMessage', 'N/A')}"
            )
            
            return response_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during JCC status check: {str(e)}")
            raise Exception(f"Failed to connect to JCC payment gateway: {str(e)}")
        except ValueError as e:
            logger.error(f"Invalid JSON response from JCC: {str(e)}")
            raise ValidationError("Invalid response format from JCC payment gateway")
    
    @staticmethod
    def is_payment_successful(order_status):
        """
        Check if payment was successful based on order status.
        
        According to JCC documentation:
        - orderStatus = 2 means successful payment
        - actionCode = 0 means successful transaction
        
        Args:
            order_status: Order status dict from get_order_status()
        
        Returns:
            bool: True if payment was successful
        """
        status = order_status.get('orderStatus')
        action_code = order_status.get('actionCode', -1)
        
        # Handle string or integer status/actionCode
        if isinstance(status, str):
            try:
                status = int(status)
            except (ValueError, TypeError):
                status = None
        
        if isinstance(action_code, str):
            try:
                action_code = int(action_code)
            except (ValueError, TypeError):
                action_code = -1
        
        # Status 2 = successful payment
        # Action code 0 = successful transaction
        is_success = status == 2 and action_code == 0
        
        logger.info(
            f"Payment success check: orderStatus={status}, actionCode={action_code}, "
            f"result={is_success}"
        )
        
        return is_success


class EmailService:
    """
    Service class for sending emails using EmailSettings configuration.
    Provides a centralized way to send emails across the application.
    """
    
    @staticmethod
    def get_email_config():
        """
        Get the active email configuration from EmailSettings model.
        
        Returns:
            EmailSettings instance or None if no configuration exists.
        """
        try:
            # Try to get active config (if is_active field exists)
            if hasattr(EmailSettings, 'is_active'):
                config = EmailSettings.objects.filter(is_active=True).first()
                if config:
                    return config
            
            # Fallback: get the most recent configuration
            config = EmailSettings.objects.order_by('-created_at').first()
            return config
        except Exception as e:
            logger.error(f"Error getting email configuration: {str(e)}")
            return None
    
    @staticmethod
    def get_connection():
        """
        Get email connection using EmailSettings configuration.
        
        Returns:
            Email backend connection instance.
        
        Raises:
            ValidationError: If no email configuration is found.
        """
        from django.core.mail import get_connection as django_get_connection
        from django.core.exceptions import ValidationError
        
        config = EmailService.get_email_config()
        if not config:
            raise ValidationError(
                "No email configuration found. "
                "Please configure email settings in the admin panel."
            )
        
        return django_get_connection(
            host=config.host,
            port=config.port,
            use_tls=config.use_tls,
            use_ssl=config.use_ssl,
            username=config.email,
            password=config.password,
            fail_silently=False,
        )
    
    @staticmethod
    def send_email(subject, message, recipient_list, from_email=None, html_message=None, fail_silently=False):
        """
        Send an email using the configured EmailSettings.
        
        Args:
            subject: Email subject
            message: Plain text email message
            recipient_list: List of recipient email addresses
            from_email: From email address (uses EmailSettings.email if not provided)
            html_message: Optional HTML version of the message
            fail_silently: If True, suppress exceptions (default: False)
        
        Returns:
            int: Number of emails sent (1 if successful, 0 if failed)
        
        Raises:
            ValidationError: If email configuration is missing
            Exception: If email sending fails (unless fail_silently=True)
        """
        from django.core.mail import send_mail
        from django.core.exceptions import ValidationError
        
        config = EmailService.get_email_config()
        if not config:
            if fail_silently:
                logger.warning("No email configuration found. Email not sent.")
                return 0
            raise ValidationError(
                "No email configuration found. "
                "Please configure email settings in the admin panel."
            )
        
        # Use config email as from_email if not provided
        if not from_email:
            from_email = config.email
        
        # Use name_from if available
        if hasattr(config, 'name_from') and config.name_from:
            from_email = f"{config.name_from} <{config.email}>"
        
        try:
            connection = EmailService.get_connection()
            return send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
                fail_silently=fail_silently,
                connection=connection,
                html_message=html_message,
            )
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}", exc_info=True)
            if not fail_silently:
                raise
            return 0
    
    @staticmethod
    def send_to_admins(subject, message, html_message=None, fail_silently=False):
        """
        Send an email to all admin users.
        
        Args:
            subject: Email subject
            message: Plain text email message
            html_message: Optional HTML version of the message
            fail_silently: If True, suppress exceptions (default: False)
        
        Returns:
            int: Number of emails sent
        """
        from .models import UserProfile
        
        try:
            # Get admin email addresses
            admin_profiles = UserProfile.objects.filter(
                role='admin',
                user__is_staff=True,
                status='active'
            ).select_related('user')
            
            admin_emails = []
            for profile in admin_profiles:
                # Use profile email if available, otherwise use user email
                email = profile.email or (profile.user.email if profile.user else None)
                if email:
                    admin_emails.append(email)
            
            if not admin_emails:
                logger.warning('No admin email addresses found.')
                return 0
            
            return EmailService.send_email(
                subject=subject,
                message=message,
                recipient_list=admin_emails,
                html_message=html_message,
                fail_silently=fail_silently,
            )
        except Exception as e:
            logger.error(f"Error sending email to admins: {str(e)}", exc_info=True)
            if not fail_silently:
                raise
            return 0
    
    @staticmethod
    def send_templated_email(template_name, context, subject, recipient_list, fail_silently=False):
        """
        Send an email using Django HTML template.
        
        Args:
            template_name: Path to the email template (e.g., 'emails/booking_confirmation.html')
            context: Dictionary of context variables for the template
            subject: Email subject line
            recipient_list: List of recipient email addresses
            fail_silently: If True, suppress exceptions (default: False)
        
        Returns:
            int: Number of emails sent (1 if successful, 0 if failed)
        
        Example:
            EmailService.send_templated_email(
                template_name='emails/booking_confirmation.html',
                context={
                    'customer_name': 'John Doe',
                    'booking_id': '12345',
                    'excursion_name': 'Troodos Mountains Tour',
                    'excursion_date': '2024-12-15',
                    'total_price': '45.00',
                },
                subject='Booking Confirmed - Troodos Mountains Tour',
                recipient_list=['customer@example.com']
            )
        """
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        
        try:
            # Render the HTML email template
            html_message = render_to_string(template_name, context)
            
            # Create plain text version by stripping HTML tags
            plain_message = strip_tags(html_message)
            
            # Send the email
            return EmailService.send_email(
                subject=subject,
                message=plain_message,
                recipient_list=recipient_list,
                html_message=html_message,
                fail_silently=fail_silently
            )
        except Exception as e:
            logger.error(f"Error sending templated email '{template_name}': {str(e)}", exc_info=True)
            if not fail_silently:
                raise
            return 0
    
    @staticmethod
    def send_dynamic_email(subject, recipient_list, email_body, email_title=None, preview_text=None, 
                          unsubscribe_url=None, fail_silently=False):
        """
        Send an email with dynamically built HTML content using the base template.
        Use EmailBuilder class to easily construct the email_body HTML.
        
        Args:
            subject: Email subject line
            recipient_list: List of recipient email addresses
            email_body: HTML content for the email body (use EmailBuilder to create)
            email_title: Page title (optional, defaults to "iTrip Knossos")
            preview_text: Preview text for inbox (optional)
            unsubscribe_url: URL for unsubscribe link (optional, for marketing emails)
            fail_silently: If True, suppress exceptions (default: False)
        
        Returns:
            int: Number of emails sent (1 if successful, 0 if failed)
        
        Example:
            from main.utils import EmailService, EmailBuilder
            
            builder = EmailBuilder()
            builder.add_greeting("John Doe")
            builder.add_success_message("Your booking is confirmed!")
            builder.add_info_card("Booking Details", {
                'Booking #': 'BK-12345',
                'Excursion': 'Troodos Tour',
                'Total': '€90.00'
            })
            builder.add_button("View Booking", "https://example.com/booking/123")
            builder.add_closing()
            
            EmailService.send_dynamic_email(
                subject='Booking Confirmed',
                recipient_list=['customer@example.com'],
                email_body=builder.build(),
                preview_text='Your booking has been confirmed!'
            )
        """
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        
        try:
            context = {
                'email_title': email_title,
                'preview_text': preview_text,
                'email_body': email_body,
                'unsubscribe_url': unsubscribe_url,
            }
            
            # Render using dynamic template
            html_message = render_to_string('emails/dynamic_email.html', context)
            
            # Create plain text version
            plain_message = strip_tags(html_message)
            
            # Send the email
            return EmailService.send_email(
                subject=subject,
                message=plain_message,
                recipient_list=recipient_list,
                html_message=html_message,
                fail_silently=fail_silently
            )
        except Exception as e:
            logger.error(f"Error sending dynamic email: {str(e)}", exc_info=True)
            if not fail_silently:
                raise
            return 0


class EmailBuilder:
    """
    Simple HTML email builder with flexible methods.
    
    Example:
        builder = EmailBuilder()
        builder.h2("Hello John!")
        builder.p("Thank you for your booking!")
        builder.card("Details", {'Booking #': 'BK-123', 'Total': '€90'})
        builder.button("View Booking", "https://...")
        builder.p("Best regards,<br>The Team")
        
        EmailService.send_dynamic_email(
            subject='Booking Confirmed',
            recipient_list=['customer@example.com'],
            email_body=builder.build()
        )
    """
    
    def __init__(self):
        self.parts = []
    
    def h2(self, text, color="#463229"):
        """Add h2 heading."""
        html = f'<h2 style="color: {color}; margin-top: 0; margin-bottom: 12px; font-size: 24px;">{text}</h2>'
        self.parts.append(html)
        return self
    
    def h3(self, text, color="#463229"):
        """Add h3 heading."""
        html = f'<h3 style="color: {color}; margin-top: 0; margin-bottom: 12px; font-size: 20px;">{text}</h3>'
        self.parts.append(html)
        return self
    
    def p(self, text, color="#4d4d4d", size="16px", bold=False):
        """Add paragraph with customizable style."""
        weight = "600" if bold else "normal"
        html = f'<p style="color: {color}; font-size: {size}; font-weight: {weight}; line-height: 1.6; margin-bottom: 16px;">{text}</p>'
        self.parts.append(html)
        return self
    
    def success(self, text):
        """Add success message (green with ✓)."""
        return self.p(f"✓ {text}", color="#4caf50", size="18px", bold=True)
    
    def warning(self, text):
        """Add warning message (orange with ⚠️)."""
        return self.p(f"⚠️ {text}", color="#ff6b35", size="18px", bold=True)
    
    def error(self, text):
        """Add error message (red with ✗)."""
        return self.p(f"✗ {text}", color="#e53935", size="18px", bold=True)
    
    def card(self, title, data, border_color="#2196f3", bg_color="#f9f9f9"):
        """
        Add card with key-value pairs.
        
        Args:
            title: Card heading
            data: Dict of {label: value} or list of (label, value) tuples
            border_color: Left border color
            bg_color: Background color
        """
        html = f'''
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" 
       style="background-color: {bg_color}; border-radius: 8px; border-left: 4px solid {border_color}; margin-bottom: 24px;">
    <tr>
        <td style="padding: 20px;">
            <h3 style="color: #463229; margin-top: 0; margin-bottom: 16px; font-size: 18px;">{title}</h3>
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">'''
        
        items = data.items() if isinstance(data, dict) else data
        for label, value in items:
            html += f'''
                <tr>
                    <td style="padding: 8px 0; color: #666666; font-size: 14px;">{label}:</td>
                    <td style="padding: 8px 0; color: #463229; font-size: 14px; text-align: right; font-weight: 600;">{value}</td>
                </tr>'''
        
        html += '''
            </table>
        </td>
    </tr>
</table>'''
        self.parts.append(html)
        return self
    
    def button(self, text, url, color="#2196f3"):
        """Add call-to-action button."""
        html = f'''
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin-bottom: 24px;">
    <tr>
        <td style="text-align: center; padding: 20px 0;">
            <a href="{url}" 
               style="display: inline-block; padding: 14px 28px; background-color: {color}; 
                      color: #ffffff !important; text-decoration: none; border-radius: 6px; 
                      font-weight: 600; font-size: 16px;">
                {text}
            </a>
        </td>
    </tr>
</table>'''
        self.parts.append(html)
        return self
    
    def list_box(self, title, items, bg_color="#fff4f0", title_color="#ff6b35"):
        """Add box with bullet list."""
        html = f'''
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" 
       style="background-color: {bg_color}; border-radius: 8px; margin-bottom: 24px;">
    <tr>
        <td style="padding: 20px;">
            <h3 style="color: {title_color}; margin-top: 0; margin-bottom: 12px; font-size: 16px;">{title}</h3>
            <ul style="color: #4d4d4d; font-size: 14px; line-height: 1.6; margin: 0; padding-left: 20px;">'''
        
        for i, item in enumerate(items):
            margin = "0" if i == len(items) - 1 else "8px"
            html += f'<li style="margin-bottom: {margin};">{item}</li>'
        
        html += '''
            </ul>
        </td>
    </tr>
</table>'''
        self.parts.append(html)
        return self
    
    def spacer(self, height="24px"):
        """Add vertical spacing."""
        html = f'<div style="height: {height};"></div>'
        self.parts.append(html)
        return self
    
    def html(self, content):
        """Add custom HTML directly."""
        self.parts.append(content)
        return self
    
    def build(self):
        """Build and return the complete HTML."""
        return '\n'.join(self.parts)