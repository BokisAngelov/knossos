from django.core.management.base import BaseCommand
from main.models import Booking
from django.utils import timezone
from django.urls import reverse
from main.utils import EmailService, EmailBuilder
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Send warnings for pending bookings with excursions happening in 1 day'

    def add_arguments(self, parser):
        parser.add_argument(
            '--send-emails',
            action='store_true',
            help='Send email notifications to customers and admins',
        )

    def handle(self, *args, **options):
        send_emails = options.get('send_emails', False)
        now = timezone.now()
        today = now.date()
        tomorrow = today + timedelta(days=1)
        
        # Find pending bookings where excursion date is exactly 1 day ahead (tomorrow)
        pending_bookings = Booking.objects.filter(
            payment_status='pending',
            date=tomorrow
        ).select_related(
            'excursion_availability',
            'excursion_availability__excursion',
            'user',
            'pickup_point'
        )
        
        count = pending_bookings.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS('✅ No pending bookings found for tomorrow')
            )
            logger.info('No pending bookings found for tomorrow')
            return
        
        self.stdout.write(
            self.style.WARNING(f'⚠️  Found {count} pending booking(s) for tomorrow')
        )
        
        # Group bookings for reporting
        warned_customers = 0
        warned_admins = 0
        failed_emails = 0
        
        if send_emails:
            # Prepare admin notification with all bookings
            admin_bookings_list = []
            
            for booking in pending_bookings:
                # Get customer email
                customer_email = booking.guest_email or (booking.user.email if booking.user else None)
                excursion_name = booking.excursion_availability.excursion.title if booking.excursion_availability and booking.excursion_availability.excursion else 'N/A'
                booking_date = booking.date.strftime('%Y-%m-%d') if booking.date else 'N/A'
                guest_name = booking.guest_name or (booking.user.get_full_name() if booking.user else 'Guest')
                total_price = booking.total_price or booking.price or 0
                
                # Add to admin list
                admin_bookings_list.append({
                    'id': booking.id,
                    'excursion': excursion_name,
                    'date': booking_date,
                    'guest': guest_name,
                    'email': customer_email or 'N/A',
                    'price': total_price
                })
                
                # Send email to customer if email available
                if customer_email:
                    try:
                        # Build checkout URL
                        checkout_path = reverse('checkout', kwargs={'booking_pk': booking.id})
                        # Add token if exists
                        if booking.access_token:
                            checkout_path += f'?token={booking.access_token}'
                        # Note: In production, prepend your site URL
                        checkout_url = f"http://localhost:8000{checkout_path}"  # Update with your domain
                        
                        # Build email content
                        builder = EmailBuilder()
                        builder.h2(f"Hello {guest_name}!")
                        builder.warning("Payment Reminder - Excursion Tomorrow!")
                        builder.p(
                            "This is a friendly reminder that you have a pending booking for an excursion tomorrow. "
                            "Please complete your payment to confirm your spot."
                        )
                        builder.card("Booking Details", {
                            'Booking #': f'{booking.id}',
                            'Excursion': excursion_name,
                            'Date': booking_date,
                            'Amount Due': f'€{total_price}'
                        })
                        builder.button("Complete Payment Now", checkout_url, color="#ff6b35")
                        builder.p(
                            "If you have already made the payment, please ignore this email. "
                            "If you need to cancel, please contact us as soon as possible."
                        )
                        builder.p("Best regards,<br>The iTrip Knossos Team")
                        
                        # Send email
                        EmailService.send_dynamic_email(
                            subject='[iTrip Knossos] ⚠️ Payment Reminder - Excursion Tomorrow',
                            recipient_list=[customer_email],
                            email_body=builder.build(),
                            preview_text='Please complete your payment for tomorrow\'s excursion',
                            fail_silently=True
                        )
                        warned_customers += 1
                        logger.info(f'Sent warning email to customer for booking #{booking.id}')
                        
                    except Exception as e:
                        failed_emails += 1
                        logger.error(f'Failed to send warning email to {customer_email} for booking #{booking.id}: {str(e)}')
                else:
                    logger.warning(f'No email found for booking #{booking.id} - customer: {guest_name}')
            
            # Send summary email to admins
            if admin_bookings_list:
                try:
                    admin_message_lines = [
                        f'⚠️  URGENT: {count} pending booking(s) require payment for excursions happening tomorrow.',
                        '',
                        'Pending Bookings:',
                        '-' * 80,
                    ]
                    
                    for booking_info in admin_bookings_list:
                        admin_message_lines.extend([
                            f'Booking ID: {booking_info["id"]}',
                            f'Excursion: {booking_info["excursion"]}',
                            f'Date: {booking_info["date"]}',
                            f'Guest: {booking_info["guest"]} ({booking_info["email"]})',
                            f'Amount Due: €{booking_info["price"]}',
                            '-' * 80,
                        ])
                    
                    admin_message_lines.append('')
                    admin_message_lines.append('Please follow up with these customers to ensure payment is completed.')
                    
                    admin_message = '\n'.join(admin_message_lines)
                    
                    emails_sent = EmailService.send_email(
                        subject=f'[iTrip Knossos] ⚠️  {count} Pending Booking(s) for Tomorrow',
                        message=admin_message,
                        recipient_list=['bokis.angelov@innovade.eu'],
                        fail_silently=True
                    )
                    
                    if emails_sent > 0:
                        warned_admins = emails_sent
                        logger.info(f'Sent warning notification to {emails_sent} admin(s)')
                    else:
                        logger.warning('Failed to send admin notification')
                        
                except Exception as e:
                    logger.error(f'Error sending admin notification: {str(e)}', exc_info=True)
            
            # Summary output
            self.stdout.write(
                self.style.SUCCESS(f'✅ Sent {warned_customers} customer warning email(s)')
            )
            if warned_admins > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Sent admin notification to {warned_admins} admin(s)')
                )
            if failed_emails > 0:
                self.stdout.write(
                    self.style.ERROR(f'❌ Failed to send {failed_emails} email(s)')
                )
        else:
            # Just show what would be warned (dry-run mode)
            self.stdout.write(
                self.style.WARNING('⚠️  DRY RUN - No emails sent. Use --send-emails to send notifications.')
            )
            self.stdout.write('')
            self.stdout.write('Bookings that would be warned:')
            for booking in pending_bookings[:10]:  # Show first 10
                excursion_name = booking.excursion_availability.excursion.title if booking.excursion_availability and booking.excursion_availability.excursion else 'N/A'
                guest_email = booking.guest_email or (booking.user.email if booking.user else 'No email')
                self.stdout.write(
                    f'  - Booking #{booking.id}: {excursion_name} - {guest_email}'
                )
            if count > 10:
                self.stdout.write(f'  ... and {count - 10} more')
        
        logger.info(
            f'Pending bookings warning completed: {count} bookings found, '
            f'{warned_customers} customer emails sent, {warned_admins} admin notifications sent'
        )

