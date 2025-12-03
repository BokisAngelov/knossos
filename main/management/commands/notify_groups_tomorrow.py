from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from main.models import Group
from main.utils import EmailService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check groups with booking date tomorrow and send email notification to admins'

    def handle(self, *args, **options):
        today = timezone.now().date()
        tomorrow = today + timedelta(days=1)
        
        # Get all groups with date tomorrow
        groups = Group.objects.filter(date=tomorrow).select_related(
            'excursion', 'bus', 'guide', 'provider'
        ).prefetch_related('bookings')
        
        group_count = groups.count()
        
        if group_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'Found {group_count} group(s) with booking date tomorrow ({tomorrow})')
            )
            self.send_admin_notification(groups, group_count, tomorrow)
        else:
            self.stdout.write(
                self.style.SUCCESS(f'No groups found with booking date tomorrow ({tomorrow})')
            )
            logger.info(f'No groups found with booking date tomorrow ({tomorrow})')

    def send_admin_notification(self, groups, count, booking_date):
        """
        Send email notification to admin users about groups with booking date tomorrow.
        """
        try:
            # Prepare email content
            subject = f'[iTrip Knossos] {count} Group(s) Scheduled for Tomorrow ({booking_date})'
            
            # Build email message with group details
            message_lines = [
                f'Reminder: {count} transport group(s) have bookings scheduled for tomorrow ({booking_date.strftime("%Y-%m-%d")}).',
                '',
                'Groups Scheduled for Tomorrow:',
                '-' * 80,
            ]
            
            for group in groups:
                excursion_name = group.excursion.title if group.excursion else 'N/A'
                bus_name = group.bus.name if group.bus else 'No Bus Assigned'
                
                # Get guide name
                if group.guide:
                    guide_name = group.guide.name or (group.guide.user.get_full_name() if group.guide.user else 'N/A')
                else:
                    guide_name = 'No Guide Assigned'
                
                # Get provider name
                if group.provider:
                    provider_name = group.provider.name or (group.provider.user.get_full_name() if group.provider.user else 'N/A')
                else:
                    provider_name = 'No Provider Assigned'
                
                total_guests = group.total_guests
                booking_count = group.bookings.count()
                status = dict(group.STATUS_CHOICES).get(group.status, group.status)
                
                message_lines.extend([
                    f'Group ID: {group.id}',
                    f'Group Name: {group.name}',
                    f'Excursion: {excursion_name}',
                    f'Date: {group.date.strftime("%Y-%m-%d") if group.date else "N/A"}',
                    f'Bus: {bus_name}',
                    f'Guide: {guide_name}',
                    f'Provider: {provider_name}',
                    f'Total Guests: {total_guests}',
                    f'Booking Count: {booking_count}',
                    f'Status: {status}',
                    '-' * 80,
                ])
            
            message_lines.append('')
            message_lines.append('Please ensure all preparations are in place for these groups.')
            
            message = '\n'.join(message_lines)
            
            # Send email using EmailService.send_to_admins
            emails_sent = EmailService.send_to_admins(
                subject=subject,
                message=message,
                fail_silently=True  # Don't fail the command if email fails
            )
            
            if emails_sent > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'Email notification sent to {emails_sent} admin(s)')
                )
                logger.info(f'Group reminder notification sent to {emails_sent} admin(s) for {count} group(s)')
            else:
                self.stdout.write(
                    self.style.WARNING('Email notification could not be sent. Check email configuration.')
                )
                logger.warning('Failed to send group reminder notification to admins')
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error sending admin notification: {str(e)}')
            )
            logger.error(f'Error sending group reminder notification to admin: {str(e)}', exc_info=True)

