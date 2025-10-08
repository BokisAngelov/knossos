from django.core.management.base import BaseCommand
from main.models import Booking
from datetime import datetime

class Command(BaseCommand):

    def handle(self, *args, **options):
        today = datetime.now().date()

        expired_bookings = Booking.objects.filter(date__lt=today, payment_status='pending')

        expired_bookings.update(payment_status='expired')

        # TODO: Send email to user and admin
            

        self.stdout.write(self.style.SUCCESS(f'Expired {expired_bookings.count()} bookings'))

