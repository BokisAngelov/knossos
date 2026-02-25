"""
Run daily at 4pm (e.g. via cron): get tomorrow's groups and send admin a list
of bookings that have NOT confirmed their pickup time.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from main.models import Group, GroupPickupPoint
from main.utils import EmailService, EmailBuilder
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Daily 4pm: list tomorrow\'s groups and bookings that have not confirmed pickup time; send to admin'

    def handle(self, *args, **options):
        today = timezone.localtime().date()
        tomorrow = today + timedelta(days=1)

        groups = Group.objects.filter(date=tomorrow).select_related(
            'excursion', 'bus', 'guide', 'provider'
        ).prefetch_related('bookings', 'bookings__pickup_point', 'pickup_times', 'pickup_times__pickup_point')

        group_count = groups.count()
        if group_count == 0:
            self.stdout.write(self.style.SUCCESS(f'No groups found for tomorrow ({tomorrow})'))
            logger.info(f'No groups found for tomorrow ({tomorrow})')
            return

        # Build list: per group, bookings that have NOT confirmed pickup time
        groups_with_unconfirmed = []
        total_unconfirmed = 0

        for group in groups:
            unconfirmed_bookings = []
            pickup_times_map = {gpp.pickup_point_id: gpp.pickup_time for gpp in group.pickup_times.all()}

            for booking in group.bookings.filter(confirmTime=False).select_related('pickup_point'):
                pickup_time = None
                if booking.pickup_point_id:
                    pickup_time = pickup_times_map.get(booking.pickup_point_id)
                guest_name = booking.guest_name or (booking.user.get_full_name() if booking.user else '') or '—'
                guest_email = booking.guest_email or (booking.user.email if booking.user else '') or '—'
                pickup_name = booking.pickup_point.name if booking.pickup_point else '—'
                unconfirmed_bookings.append({
                    'guest_name': guest_name,
                    'guest_email': guest_email,
                    'pickup_point': pickup_name,
                    'pickup_time': pickup_time,
                })
                total_unconfirmed += 1

            groups_with_unconfirmed.append({
                'group': group,
                'unconfirmed': unconfirmed_bookings,
            })

        self._send_admin_email(tomorrow, groups_with_unconfirmed, total_unconfirmed, group_count)

    def _send_admin_email(self, booking_date, groups_with_unconfirmed, total_unconfirmed, group_count):

        if total_unconfirmed > 0:
            try:
                subject = (
                    f'[iTrip Knossos] Tomorrow\'s groups – {total_unconfirmed} booking(s) have not confirmed pickup time'
                )

                builder = EmailBuilder()
                builder.h2('Daily reminder: groups for tomorrow')
                builder.p(
                    f'Booking date: {booking_date.strftime("%A, %d %B %Y")}. '
                    f'Total groups: {group_count}. '
                    f'Bookings not yet confirmed: {total_unconfirmed}.'
                )

                for item in groups_with_unconfirmed:
                    group = item['group']
                    unconfirmed = item['unconfirmed']
                    excursion_name = group.excursion.title if group.excursion else 'N/A'
                    builder.h3(f'{group.name} – {excursion_name}')

                    if not unconfirmed:
                        builder.p('All bookings in this group have confirmed their pickup time.')
                    else:
                        rows = []
                        for i, b in enumerate(unconfirmed, 1):
                            time_str = b['pickup_time'].strftime('%H:%M') if b['pickup_time'] else '—'
                            detail = f"{b['guest_email']} | {b['pickup_point']} | {time_str}"
                            rows.append((f"{i}. {b['guest_name']}", detail))
                        builder.card(
                            'Not confirmed',
                            rows,
                            border_color='#f59e0b',
                        )

                builder.p('Please follow up with guests who have not confirmed.')
                builder.p('Best regards,<br>Knossos')

                html_body = builder.build()
                plain = (
                    f"Groups tomorrow: {booking_date}. "
                    f"Unconfirmed pickup time: {total_unconfirmed} booking(s) across {group_count} group(s)."
                )

                emails_sent = EmailService.send_to_admins(
                    subject=subject,
                    message=plain,
                    html_message=html_body,
                    fail_silently=True,
                )

                if emails_sent > 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Sent to {emails_sent} admin(s): {group_count} group(s), {total_unconfirmed} unconfirmed booking(s)'
                        )
                    )
                    logger.info(
                        f'Notify groups tomorrow: email sent to {emails_sent} admin(s), '
                        f'{group_count} group(s), {total_unconfirmed} unconfirmed'
                    )
                else:
                    self.stdout.write(self.style.WARNING('No admin emails sent. Check email config and admin users.'))
                    logger.warning('Notify groups tomorrow: no admin emails sent')

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error sending admin notification: {str(e)}'))
                logger.error(f'Error in notify_groups_tomorrow: {str(e)}', exc_info=True)
