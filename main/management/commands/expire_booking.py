from django.core.management.base import BaseCommand
from main.models import Booking
from django.utils import timezone
from main.utils import EmailService
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Expire pending bookings 2 days before excursion date and notify users'

    def handle(self, *args, **options):
        now = timezone.now()
        today = now.date()
        expiration_cutoff_date = today + timedelta(days=2)

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

            # Expire pending bookings when excursion date is within 2 days (or already past).
            if booking.date <= expiration_cutoff_date:
                booking.payment_status = 'expired'
                booking.save(update_fields=['payment_status'])
                expired_bookings.append(booking)
                expired_count += 1
                self.send_customer_cancellation_email(booking)

        # Send email to admin if there are expired bookings
        if expired_count > 0:
            self.send_admin_notification(expired_bookings, expired_count)

        self.stdout.write(self.style.SUCCESS(f'Expired {expired_count} booking(s)'))

    def send_customer_cancellation_email(self, booking):
        """
        Send booking cancellation notice to customer for expired pending booking.
        """
        customer_email = booking.guest_email or (booking.user.email if booking.user else None)
        if not customer_email:
            logger.warning(f'No customer email found for expired booking #{booking.id}')
            return

        try:
            from main.utils import EmailBuilder

            display_excursion = booking.get_display_excursion()
            excursion_name = display_excursion.title if display_excursion else 'N/A'
            guest_name = (
                booking.guest_name
                or (booking.user.profile.name if getattr(booking.user, 'profile', None) and booking.user.profile.name else None)
                or (booking.user.get_full_name() if booking.user else None)
                or (booking.user.username if booking.user else None)
                or 'Guest'
            )
            booking_date = booking.date.strftime('%B %d, %Y') if booking.date else 'N/A'

            builder = EmailBuilder()
            builder.h2(f"Hello {guest_name},")
            builder.warning("Your pending booking has been cancelled")
            builder.p(
                "Your booking was automatically cancelled because payment was not completed at least 2 days before the excursion date."
            )
            builder.card("cancelled Booking Details", {
                'Booking #': f'{booking.id}',
                'Excursion': excursion_name,
                'Date': booking_date,
                'Amount': f"€{booking.total_price or booking.price or 0}"
            }, border_color="#e53935")
            builder.p("If this is a mistake or you still want to attend, please create a new booking or contact our support team.")
            builder.p("Best regards,<br>The iTrip Knossos Team")

            emails_sent = EmailService.send_dynamic_email(
                subject='[iTrip Knossos] Your Pending Booking Was cancelled',
                recipient_list=[customer_email],
                email_body=builder.build(),
                preview_text='Your pending booking was cancelled due to incomplete payment.',
                fail_silently=True
            )

            if emails_sent > 0:
                logger.info(f'Sent cancellation email to customer for booking #{booking.id}')
            else:
                logger.warning(f'Failed to send cancellation email to customer for booking #{booking.id}')

        except Exception as e:
            logger.error(
                f'Error sending cancellation email to customer for booking #{booking.id}: {str(e)}',
                exc_info=True
            )

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
            builder.p("The following bookings were expired due to incomplete payment 2 days before excursion date.")
            
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
                preview_text=f'{count} bookings expired due to incomplete payment',
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

