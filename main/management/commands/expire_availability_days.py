from django.core.management.base import BaseCommand
from main.models import AvailabilityDays
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Mark past AvailabilityDays as inactive'

    def handle(self, *args, **options):
        today = timezone.now().date()
        
        # Find AvailabilityDays where date_day is in the past and status is active
        expired_availability_days = AvailabilityDays.objects.filter(
            date_day__lt=today,
            status='active'
        ).select_related('excursion_availability', 'excursion_availability__excursion')
        
        count = expired_availability_days.count()
        
        if count > 0:
            # Get list of expired days for logging (before update)
            expired_days_list = list(expired_availability_days[:10])  # Get first 10 for display
            
            # Update status to inactive
            expired_availability_days.update(status='inactive')
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Expired {count} availability day(s)')
            )
            logger.info(f'Expired {count} availability day(s)')
            
            # Show details (first 5 for reference)
            if count <= 5:
                for day in expired_days_list:
                    excursion_name = day.excursion_availability.excursion.title if day.excursion_availability and day.excursion_availability.excursion else 'N/A'
                    self.stdout.write(
                        f'  - {excursion_name} ({day.date_day})'
                    )
            else:
                # Show first 3 as examples
                for day in expired_days_list[:3]:
                    excursion_name = day.excursion_availability.excursion.title if day.excursion_availability and day.excursion_availability.excursion else 'N/A'
                    self.stdout.write(
                        f'  - {excursion_name} ({day.date_day})'
                    )
                self.stdout.write(f'  ... and {count - 3} more')
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ No availability days to expire')
            )
            logger.info('No availability days to expire')

