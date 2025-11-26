from django.core.management.base import BaseCommand
from main.models import Booking
from django.utils import timezone
from main.utils import EmailService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Expire bookings where the excursion date (and time if available) is in the past and payment is pending'

    def handle(self, *args, **options):
        now = timezone.now()
        today = now.date()
        current_time = now.time()

        # Get all pending bookings
        pending_bookings = Booking.objects.filter(payment_status='pending').select_related(
            'excursion_availability', 'excursion_availability__excursion', 'user'
        )
        
        expired_bookings = []
        expired_count = 0
        
        for booking in pending_bookings:
            # Skip if booking has no date
            if not booking.date:
                continue
            
            is_expired = False
            
            # Check if the booking date is in the past
            if booking.date < today:
                is_expired = True
            elif booking.date == today:
                # If date is today, check if excursion time has passed (if available)
                if booking.excursion_availability and booking.excursion_availability.start_time:
                    # If the start time has passed, the booking is expired
                    if booking.excursion_availability.start_time < current_time:
                        is_expired = True
                # If no time is available and date is today, don't expire
                # (since the excursion might be happening later today)
            
            if is_expired:
                booking.payment_status = 'expired'
                booking.save(update_fields=['payment_status'])
                expired_bookings.append(booking)
                expired_count += 1

        # Send email to admin if there are expired bookings
        if expired_count > 0:
            self.send_admin_notification(expired_bookings, expired_count)

        self.stdout.write(self.style.SUCCESS(f'Expired {expired_count} bookings'))

    def send_admin_notification(self, expired_bookings, count):
        """
        Send email notification to admin users about expired bookings.
        """
        try:            
            # Prepare email content
            subject = f'[iTrip Knossos] {count} Booking(s) Expired'
            
            # Build email message with booking details
            message_lines = [
                f'{count} booking(s) have been automatically expired due to past excursion dates.',
                '',
                'Expired Bookings:',
                '-' * 80,
            ]
            
            for booking in expired_bookings:
                excursion_name = booking.excursion_availability.excursion.title if booking.excursion_availability and booking.excursion_availability.excursion else 'N/A'
                guest_name = booking.guest_name or 'N/A'
                guest_email = booking.guest_email or 'N/A'
                booking_date = booking.date.strftime('%Y-%m-%d') if booking.date else 'N/A'
                booking_id = booking.id
                
                message_lines.extend([
                    f'Booking ID: {booking_id}',
                    f'Excursion: {excursion_name}',
                    f'Date: {booking_date}',
                    f'Guest: {guest_name} ({guest_email})',
                    f'Price: €{booking.price or 0}',
                    '-' * 80,
                ])
            
            message_lines.append('')
            message_lines.append('Please review these bookings in the admin panel.')
            
            message = '\n'.join(message_lines)
            
            # Send email using EmailService
            emails_sent = EmailService.send_email(
                subject=subject,
                message=message,
                recipient_list=['bokis.angelov@innovade.eu'],
                fail_silently=True  # Don't fail the command if email fails
            )
            
            if emails_sent > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'Email notification sent to {emails_sent} admin(s)')
                )
                logger.info(f'Expired booking notification sent to {emails_sent} admin(s)')
            else:
                self.stdout.write(
                    self.style.WARNING('Email notification could not be sent. Check email configuration.')
                )
                logger.warning('Failed to send expired booking notification to admins')
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error sending admin notification: {str(e)}')
            )
            logger.error(f'Error sending expired booking notification to admin: {str(e)}', exc_info=True)

