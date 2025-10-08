from django.core.management.base import BaseCommand
from main.models import ExcursionAvailability, Excursion
from datetime import datetime

class Command(BaseCommand):
    help = 'Expire availability if end_date is in the past'

    def handle(self, *args, **options):
        today = datetime.now().date()
        
        # Find and expire availabilities with end_date in the past
        expired_availabilities = ExcursionAvailability.objects.filter(
            end_date__lt=today, 
            status='active'
        )
        
        # Get the excursions that have expired availabilities before updating
        excursions_with_expired = list(
            Excursion.objects.filter(availabilities__in=expired_availabilities).distinct()
        )
        
        # Update expired availabilities
        count = expired_availabilities.update(is_active=False, status='inactive')
        
        # Check each excursion to see if it has any remaining active availabilities
        excursions_made_inactive = 0
        for excursion in excursions_with_expired:
            # Check if this excursion has any active availabilities left
            has_active_availability = excursion.availabilities.filter(
                status='active', 
                is_active=True
            ).exists()
            
            # If no active availabilities remain, mark excursion as inactive
            if not has_active_availability:
                excursion.status = 'inactive'
                excursion.save()
                excursions_made_inactive += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Expired {count} availabilities and marked {excursions_made_inactive} excursions as inactive'
            )
        )

