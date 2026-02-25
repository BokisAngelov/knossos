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
            'excursion_availability', 'excursion_availability__excursion', 'excursion', 'user', 'user__profile'
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
            from main.utils import EmailBuilder
            
            # Build email content
            builder = EmailBuilder()
            builder.h2("Booking Expiration Report")
            builder.warning(f"{count} booking(s) have been automatically expired")
            builder.p("The following bookings were expired due to past excursion dates.")
            
            # Add each booking as a card
            for booking in expired_bookings[:10]:  # Limit to first 10 for email size
                display_excursion = booking.get_display_excursion()
                excursion_name = display_excursion.title if display_excursion else 'N/A'
                # Prefer guest fields, then user profile name/email, then User name/email
                guest_name = (
                    booking.guest_name
                    or (booking.user.profile.name if getattr(booking.user, 'profile', None) and booking.user.profile.name else None)
                    or (booking.user.get_full_name() if booking.user else None)
                    or (booking.user.username if booking.user else None)
                ) or 'N/A'
                guest_email = (
                    booking.guest_email
                    or (booking.user.email if booking.user else None)
                    or (booking.user.profile.email if getattr(booking.user, 'profile', None) and booking.user.profile.email else None)
                ) or 'N/A'
                booking_date = booking.date.strftime('%B %d, %Y') if booking.date else 'N/A'
                
                builder.card(f"Booking #{booking.id}", {
                    'Excursion': excursion_name,
                    'Date': booking_date,
                    'Guest': guest_name,
                    'Email': guest_email,
                    'Price': f"€{booking.price or 0}"
                }, border_color="#e53935")
            
            if count > 10:
                builder.p(f"... and {count - 10} more booking(s)")
            
            builder.p("Please review these bookings in the admin panel.")
            builder.p("Best regards,<br>Automated System")
            
            # Send email
            emails_sent = EmailService.send_dynamic_email(
                subject=f'[iTrip Knossos] {count} Booking(s) Expired',
                recipient_list=['bokis.angelov@innovade.eu'],
                email_body=builder.build(),
                preview_text=f'{count} bookings expired due to past dates',
                fail_silently=True
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

