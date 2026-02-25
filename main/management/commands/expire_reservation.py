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
            help='Also send thank-you emails to clients (admin report is always sent)',
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
        
        self.send_admin_notification(expired_list)
        self.send_client_notifications(expired_list)
    
    def send_client_notifications(self, expired_reservations):
        """Send thank-you / expiration emails to each client. Returns number notified."""
        clients_notified = 0
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
                    builder.p(
                        f"You can still use your email address and password to login."
                    )
                    builder.card("Reservation Details", {
                        'Check-in Date': reservation.check_in.strftime('%B %d, %Y'),
                        'Check-out Date': reservation.check_out.strftime('%B %d, %Y'),
                        'Total Bookings': reservation.get_bookings_count(),
                        'Total Spent': f"€{reservation.get_total_spent():.2f}"
                    })
                    builder.p(
                        "We hope you enjoyed your excursions with us! "
                        "For future bookings, please visit our website or contact us directly."
                    )
                    builder.p("Best regards,<br>The iTrip Knossos Team")
                    
                    EmailService.send_dynamic_email_async(
                        subject='[iTrip Knossos] Thank You for Choosing Us!',
                        recipient_list=[reservation.client_email],
                        email_body=builder.build(),
                        preview_text='Your reservation code has expired - Thank you!',
                        email_kind='reservation_expired',
                    )
                    clients_notified += 1
                    logger.info(f'Sent expiration notification to {reservation.client_email}')
                    
                except Exception as e:
                    logger.error(f'Failed to send notification for voucher {reservation.voucher_id}: {str(e)}')
        return clients_notified

    def send_admin_notification(self, expired_reservations):
        """Send email report to admin when reservations are expired."""
        try:
            builder = EmailBuilder()
            builder.h2("Reservation Expiration Report")
            builder.p(f"{len(expired_reservations)} reservation(s) have been automatically expired.")
            
            builder.card("Summary", {
                'Total Expired': len(expired_reservations),
            })
            
            # Add details for each reservation
            for reservation in expired_reservations[:10]:  # Limit to 10
                builder.card(f"Voucher: {reservation.voucher_id}", {
                    'Client': reservation.client_name or 'N/A',
                    'Email': reservation.client_email or 'N/A',
                    'Bookings': reservation.get_bookings_count(),
                    'Total Spent': f"€{reservation.get_total_spent():.2f}"
                }, border_color="#ff6b35")
            
            if len(expired_reservations) > 10:
                builder.p(f"... and {len(expired_reservations) - 10} more reservation(s)")
            
            builder.p("Best regards,<br>Automated System")
            
            emails_sent = EmailService.send_dynamic_email(
                subject=f'[iTrip Knossos] {len(expired_reservations)} Reservation(s) Expired',
                recipient_list=['bokis.angelov@innovade.eu'],
                email_body=builder.build(),
                preview_text=f'{len(expired_reservations)} reservations expired',
                fail_silently=True
            )
            if emails_sent > 0:
                logger.info('Sent expiration notification to admin')
                self.stdout.write(self.style.SUCCESS('Admin notification email sent.'))
            else:
                self.stdout.write(
                    self.style.WARNING('Admin email could not be sent. Check email configuration.')
                )
        except Exception as e:
            logger.error(f'Failed to send admin notification: {str(e)}')
            self.stdout.write(self.style.ERROR(f'Error sending admin notification: {str(e)}'))