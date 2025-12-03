from django.core.management.base import BaseCommand
from main.models import ExcursionAvailability, Excursion
from main.utils import EmailService, EmailBuilder
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Expire availability if end_date is in the past'

    def add_arguments(self, parser):
        parser.add_argument(
            '--send-emails',
            action='store_true',
            help='Send email notification to admins',
        )

    def handle(self, *args, **options):
        send_emails = options.get('send_emails', False)
        today = datetime.now().date()
        
        # Find and expire availabilities with end_date in the past
        expired_availabilities = ExcursionAvailability.objects.filter(
            end_date__lt=today, 
            status='active'
        ).select_related('excursion')
        
        # Get the excursions that have expired availabilities before updating
        excursions_with_expired = list(
            Excursion.objects.filter(availabilities__in=expired_availabilities).distinct()
        )
        
        # Store list before update
        expired_list = list(expired_availabilities)
        
        # Update expired availabilities
        count = expired_availabilities.update(is_active=False, status='inactive')
        
        # Check each excursion to see if it has any remaining active availabilities
        excursions_made_inactive = 0
        inactive_excursions = []
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
                inactive_excursions.append(excursion)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Expired {count} availabilities and marked {excursions_made_inactive} excursions as inactive'
            )
        )
        logger.info(f'Expired {count} availabilities, {excursions_made_inactive} excursions became inactive')
        
        # Send email notification
        if send_emails and (count > 0 or excursions_made_inactive > 0):
            self.send_admin_notification(expired_list, inactive_excursions)
    
    def send_admin_notification(self, expired_availabilities, inactive_excursions):
        """Send email notification to admins."""
        try:
            builder = EmailBuilder()
            builder.h2("Availability Expiration Report")
            builder.p(
                f"{len(expired_availabilities)} availability period(s) have expired "
                f"and {len(inactive_excursions)} excursion(s) became inactive."
            )
            
            builder.card("Summary", {
                'Expired Availabilities': len(expired_availabilities),
                'Excursions Now Inactive': len(inactive_excursions)
            })
            
            # Show expired availabilities (limit to 5)
            if expired_availabilities:
                builder.h3("Expired Availabilities")
                for avail in expired_availabilities[:5]:
                    builder.card(avail.excursion.title, {
                        'Period': f"{avail.start_date.strftime('%b %d')} - {avail.end_date.strftime('%b %d, %Y')}",
                        'Max Guests': avail.max_guests,
                        'Booked': avail.booked_guests
                    }, border_color="#ff6b35")
                
                if len(expired_availabilities) > 5:
                    builder.p(f"... and {len(expired_availabilities) - 5} more")
            
            # Show inactive excursions
            if inactive_excursions:
                builder.h3("Excursions Now Inactive")
                builder.list_box("The following excursions have no active availabilities", [
                    excursion.title for excursion in inactive_excursions
                ], bg_color="#fff4f0", title_color="#e53935")
            
            builder.p("Please review and add new availabilities if needed.")
            builder.p("Best regards,<br>Automated System")
            
            EmailService.send_dynamic_email(
                subject=f'[iTrip Knossos] {len(expired_availabilities)} Availability Period(s) Expired',
                recipient_list=['bokis.angelov@innovade.eu'],
                email_body=builder.build(),
                preview_text=f'{len(expired_availabilities)} availabilities expired',
                fail_silently=True
            )
            logger.info('Sent expiration notification to admin')
            self.stdout.write(self.style.SUCCESS('Email notification sent to admin'))
            
        except Exception as e:
            logger.error(f'Failed to send admin notification: {str(e)}')
            self.stdout.write(self.style.WARNING(f'Failed to send email: {str(e)}'))

