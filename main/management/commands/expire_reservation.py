from django.core.management.base import BaseCommand
from main.models import Reservation
from main.utils import EmailService, EmailBuilder
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Expire reservations that have passed their checkout date'

    def add_arguments(self, parser):
        parser.add_argument(
            '--send-emails',
            action='store_true',
            help='Send email notifications to clients and admins',
        )

    def handle(self, *args, **options):
        send_emails = options.get('send_emails', False)
        today = datetime.now().date()

        expired_reservations = Reservation.objects.filter(
            check_out__lt=today, 
            status='active'
        ).select_related('client_profile')
        
        count = expired_reservations.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No reservations to expire'))
            return
        
        # Store list before update
        expired_list = list(expired_reservations)
        
        # Update status
        expired_reservations.update(status='inactive')

        self.stdout.write(
            self.style.SUCCESS(f'Expired {count} reservation(s)')
        )
        logger.info(f'Expired {count} reservation(s)')
        
        # Send emails if requested
        if send_emails:
            self.send_notifications(expired_list)
    
    def send_notifications(self, expired_reservations):
        """Send email notifications to clients and admins."""
        clients_notified = 0
        
        # Notify each client
        for reservation in expired_reservations:
            if reservation.client_email:
                try:
                    builder = EmailBuilder()
                    builder.h2(f"Hello {reservation.client_name or 'Guest'}!")
                    builder.p("Thank you for staying with us!")
                    builder.p(
                        f"Your reservation (Voucher: {reservation.voucher_id}) has now expired "
                        f"as your checkout date has passed."
                    )
                    builder.card("Reservation Details", {
                        'Voucher ID': reservation.voucher_id,
                        'Check-out Date': reservation.check_out.strftime('%B %d, %Y'),
                        'Total Bookings': reservation.get_bookings_count(),
                        'Total Spent': f"€{reservation.get_total_spent():.2f}"
                    })
                    builder.p(
                        "We hope you enjoyed your excursions with us! "
                        "For future bookings, please visit our website or contact us directly."
                    )
                    builder.p("Best regards,<br>The iTrip Knossos Team")
                    
                    EmailService.send_dynamic_email(
                        subject='[iTrip Knossos] Thank You for Choosing Us!',
                        recipient_list=[reservation.client_email],
                        email_body=builder.build(),
                        preview_text='Your reservation has expired - Thank you!',
                        fail_silently=True
                    )
                    clients_notified += 1
                    logger.info(f'Sent expiration notification to {reservation.client_email}')
                    
                except Exception as e:
                    logger.error(f'Failed to send notification for voucher {reservation.voucher_id}: {str(e)}')
        
        # Send admin notification
        try:
            builder = EmailBuilder()
            builder.h2("Reservation Expiration Report")
            builder.p(f"{len(expired_reservations)} reservation(s) have been automatically expired.")
            
            builder.card("Summary", {
                'Total Expired': len(expired_reservations),
                'Clients Notified': clients_notified
            })
            
            # Add details for each reservation
            for reservation in expired_reservations[:10]:  # Limit to 10
                builder.card(f"Voucher: {reservation.voucher_id}", {
                    'Client': reservation.client_name or 'N/A',
                    'Email': reservation.client_email or 'N/A',
                    'Check-out': reservation.check_out.strftime('%B %d, %Y'),
                    'Bookings': reservation.get_bookings_count(),
                    'Total Spent': f"€{reservation.get_total_spent():.2f}"
                }, border_color="#ff6b35")
            
            if len(expired_reservations) > 10:
                builder.p(f"... and {len(expired_reservations) - 10} more reservation(s)")
            
            builder.p("Best regards,<br>Automated System")
            
            EmailService.send_dynamic_email(
                subject=f'[iTrip Knossos] {len(expired_reservations)} Reservation(s) Expired',
                recipient_list=['bokis.angelov@innovade.eu'],
                email_body=builder.build(),
                preview_text=f'{len(expired_reservations)} reservations expired',
                fail_silently=True
            )
            logger.info('Sent expiration notification to admin')
            
        except Exception as e:
            logger.error(f'Failed to send admin notification: {str(e)}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Sent notifications to {clients_notified} client(s) and admin')
        )