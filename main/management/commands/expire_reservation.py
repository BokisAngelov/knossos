from django.core.management.base import BaseCommand
from main.models import Reservation
from datetime import datetime

class Command(BaseCommand):

    def handle(self, *args, **options):
        today = datetime.now().date()

        expired_reservations = Reservation.objects.filter(check_out__lt=today, status='active')

        expired_reservations.update(status='inactive')

        self.stdout.write(self.style.SUCCESS(f'Expired {expired_reservations.count()} reservations'))