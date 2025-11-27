from django.core.management.base import BaseCommand
from main.models import AvailabilityDays, Booking
import logging
from main.utils import EmailService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Recalculate and sync booked_guests in AvailabilityDays from actual completed bookings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--validate-capacity',
            action='store_true',
            help='Check and warn if booked_guests exceeds capacity',
        )

    def handle(self, *args, **options):
        validate_capacity = options.get('validate_capacity', False)
        
        # Get all active availability days
        availability_days = AvailabilityDays.objects.filter(
            status='active'
        ).select_related('excursion_availability', 'excursion_availability__excursion')
        
        updated_count = 0
        discrepancy_count = 0
        over_capacity_count = 0
        
        for availability_day in availability_days:
            # Skip if no excursion_availability or date_day
            if not availability_day.excursion_availability or not availability_day.date_day:
                continue
            
            # Find all completed bookings for this availability day
            completed_bookings = Booking.objects.filter(
                excursion_availability=availability_day.excursion_availability,
                date=availability_day.date_day,
                payment_status='completed'
            )
            
            # Calculate total guests from completed bookings
            total_guests = 0
            for booking in completed_bookings:
                adults = booking.total_adults or 0
                kids = booking.total_kids or 0
                infants = booking.total_infants or 0
                total_guests += (adults + kids + infants)
            
            # Check for discrepancy
            old_booked_guests = availability_day.booked_guests
            if old_booked_guests != total_guests:
                discrepancy_count += 1
                logger.info(
                    f'Capacity discrepancy found for {availability_day}: '
                    f'old={old_booked_guests}, new={total_guests}'
                )
            
            # Update booked_guests
            availability_day.booked_guests = total_guests
            availability_day.save(update_fields=['booked_guests'])
            updated_count += 1
            
            # Validate capacity if requested
            if validate_capacity and availability_day.capacity > 0:
                if total_guests > availability_day.capacity:
                    over_capacity_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f'⚠️  Over capacity: {availability_day} - '
                            f'{total_guests} guests booked, capacity: {availability_day.capacity}'
                        )
                    )
                    logger.warning(
                        f'Over capacity detected: {availability_day} - '
                        f'{total_guests} guests booked, capacity: {availability_day.capacity}'
                    )

                    # TODO: Send email to admin
                    emails_sent = EmailService.send_email(
                        subject=f'[iTrip Knossos] Over Capacity',
                        message=f"Over capacity detected: {availability_day} - {total_guests} guests booked, capacity: {availability_day.capacity}",
                        recipient_list=['bokis.angelov@innovade.eu'],
                        fail_silently=True
                    )
        
        # Summary output
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Updated {updated_count} availability day(s)'
            )
        )
        
        if discrepancy_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  Found {discrepancy_count} discrepancy/discrepancies that were corrected'
                )
            )
        
        if validate_capacity and over_capacity_count > 0:
            self.stdout.write(
                self.style.ERROR(
                    f'❌ Found {over_capacity_count} availability day(s) over capacity'
                )
            )

        elif validate_capacity:
            self.stdout.write(
                self.style.SUCCESS('✅ All availability days are within capacity limits')
            )
        
        logger.info(
            f'Capacity update completed: {updated_count} updated, '
            f'{discrepancy_count} discrepancies found, '
            f'{over_capacity_count} over capacity'
        )

