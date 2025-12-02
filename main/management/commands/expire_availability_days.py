from django.core.management.base import BaseCommand
from main.models import AvailabilityDays
from main.utils import EmailService, EmailBuilder
from django.utils import timezone
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Mark past AvailabilityDays as inactive'

    def add_arguments(self, parser):
        parser.add_argument(
            '--send-emails',
            action='store_true',
            help='Send email notification to admins (only if > 20 days expired)',
        )

    def handle(self, *args, **options):
        send_emails = options.get('send_emails', False)
        today = timezone.now().date()
        
        # Find AvailabilityDays where date_day is in the past and status is active
        expired_availability_days = AvailabilityDays.objects.filter(
            date_day__lt=today,
            status='active'
        ).select_related('excursion_availability', 'excursion_availability__excursion')
        
        count = expired_availability_days.count()
        
        if count > 0:
            # Get list of expired days for logging (before update)
            expired_days_list = list(expired_availability_days[:50])  # Get first 50
            
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
            
            # Send email if many days expired (indicates system may not have run recently)
            if send_emails and count >= 20:
                self.send_admin_notification(count, expired_days_list)
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ No availability days to expire')
            )
            logger.info('No availability days to expire')
    
    def send_admin_notification(self, total_count, expired_days_sample):
        """Send email notification to admins if many days expired."""
        try:
            # Group by excursion for better reporting
            excursion_counts = defaultdict(int)
            for day in expired_days_sample:
                if day.excursion_availability and day.excursion_availability.excursion:
                    excursion_name = day.excursion_availability.excursion.title
                    excursion_counts[excursion_name] += 1
            
            builder = EmailBuilder()
            builder.h2("Availability Days Expiration Report")
            builder.warning(f"{total_count} past availability days were expired")
            builder.p(
                "A large number of availability days were expired, which may indicate "
                "the system hasn't run recently. Please review."
            )
            
            builder.card("Summary", {
                'Total Days Expired': total_count,
                'Unique Excursions': len(excursion_counts),
                'Sample Size': len(expired_days_sample)
            })
            
            # Show breakdown by excursion
            if excursion_counts:
                builder.h3("Breakdown by Excursion")
                excursion_data = []
                for excursion, count in sorted(excursion_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                    excursion_data.append((excursion, f"{count} day(s)"))
                builder.card("Expired Days per Excursion", excursion_data, border_color="#ff6b35")
            
            builder.p("This is an automated maintenance task. No action required unless unexpected.")
            builder.p("Best regards,<br>Automated System")
            
            EmailService.send_dynamic_email(
                subject=f'[iTrip Knossos] ⚠️ {total_count} Availability Days Expired',
                recipient_list=['bokis.angelov@innovade.eu'],
                email_body=builder.build(),
                preview_text=f'{total_count} past availability days were expired',
                fail_silently=True
            )
            logger.info('Sent bulk expiration notification to admin')
            self.stdout.write(self.style.SUCCESS('Email notification sent to admin'))
            
        except Exception as e:
            logger.error(f'Failed to send admin notification: {str(e)}')
            self.stdout.write(self.style.WARNING(f'Failed to send email: {str(e)}'))

