"""
Create 5 random dummy Excursions, ExcursionAvailabilities (with AvailabilityDays), and Bookings.
Run from project root: python manage.py create_dummy_excursions
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from main.models import (
    Excursion,
    ExcursionAvailability,
    AvailabilityDays,
    Booking,
)


# Dummy data pools
EXCURSION_TITLES = [
    "Sunset Cruise to Spinalonga",
    "Samaria Gorge Hiking Tour",
    "Knossos Palace & Heraklion",
    "Boat Trip to Chrissi Island",
    "Crete Wine & Olive Oil Tasting",
]
EXCURSION_DESCRIPTIONS = [
    "Explore the island fortress and enjoy swimming in crystal waters.",
    "Full-day trek through one of Europe's longest gorges.",
    "Guided visit to the Minoan palace and archaeological museum.",
    "Relax on golden beaches and turquoise sea.",
    "Visit traditional villages and taste local products.",
]
GUEST_FIRST_NAMES = ["Maria", "Nikos", "Anna", "Yannis", "Elena"]
GUEST_LAST_NAMES = ["Papadopoulos", "Kostas", "Georgiou", "Dimitriou", "Vasilaki"]
GUEST_EMAIL_DOMAINS = ["example.com", "test.com", "mail.demo"]


class Command(BaseCommand):
    help = "Create 5 random dummy excursions, availabilities (with availability days), and bookings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete only the dummy items created by this script (by title prefix) before creating new ones.",
        )

    def handle(self, *args, **options):
        if options.get("clear"):
            self._clear_dummy_data()

        created = self._create_dummy_data()
        self.stdout.write(
            self.style.SUCCESS(
                f"Created: {created['excursions']} excursions, "
                f"{created['availabilities']} availabilities, "
                f"{created['availability_days']} availability days, "
                f"{created['bookings']} bookings."
            )
        )

    def _clear_dummy_data(self):
        """Remove dummy excursions (and cascaded availabilities, availability days, bookings)."""
        to_delete = Excursion.objects.filter(title__startswith="[Dummy] ")
        count = to_delete.count()
        to_delete.delete()
        self.stdout.write(self.style.WARNING(f"Cleared {count} dummy excursions (and related data)."))

    @transaction.atomic
    def _create_dummy_data(self):
        today = timezone.now().date()
        created = {"excursions": 0, "availabilities": 0, "availability_days": 0, "bookings": 0}

        for i in range(5):
            title = f"[Dummy] {random.choice(EXCURSION_TITLES)} #{i + 1}"
            description = random.choice(EXCURSION_DESCRIPTIONS)
            excursion = Excursion.objects.create(
                title=title,
                description=description,
                status="active",
                full_day=random.choice([True, False]),
                on_request=random.choice([True, False]),
                overall_rating=Decimal(str(round(random.uniform(3.5, 5.0), 2))) if random.random() > 0.3 else None,
            )
            created["excursions"] += 1

            # One availability per excursion: 2–4 weeks from today, 7–14 days long
            start_offset = random.randint(14, 28)
            length = random.randint(7, 14)
            start_date = today + timedelta(days=start_offset)
            end_date = start_date + timedelta(days=length)
            max_guests = random.choice([12, 16, 20, 24, 30])
            adult_price = Decimal(str(round(random.uniform(25, 85), 2)))
            child_price = adult_price * Decimal("0.5") if random.random() > 0.3 else None
            infant_price = Decimal("0") if random.random() > 0.5 else None

            availability = ExcursionAvailability.objects.create(
                excursion=excursion,
                start_date=start_date,
                end_date=end_date,
                max_guests=max_guests,
                booked_guests=0,
                is_active=True,
                status="active",
                adult_price=adult_price,
                child_price=child_price,
                infant_price=infant_price,
                discount=Decimal("0"),
                pickup_start_time=random.choice([None, timezone.now().time().replace(hour=8, minute=0, second=0)]),
                pickup_end_time=random.choice([None, timezone.now().time().replace(hour=9, minute=30, second=0)]),
                start_time=timezone.now().time().replace(hour=10, minute=0, second=0),
                end_time=timezone.now().time().replace(hour=16, minute=0, second=0),
            )
            created["availabilities"] += 1

            # AvailabilityDays for every day in range (so bookings have capacity)
            current = start_date
            while current <= end_date:
                AvailabilityDays.objects.create(
                    excursion_availability=availability,
                    date_day=current,
                    capacity=max_guests,
                    booked_guests=0,
                    status="active",
                )
                current += timedelta(days=1)
                created["availability_days"] += 1

            # One booking per availability: random date in range, random guests
            booking_date = start_date + timedelta(days=random.randint(0, min(5, (end_date - start_date).days)))
            adults = random.randint(1, 4)
            kids = random.randint(0, 2)
            infants = random.randint(0, 1)
            base_price = (adults * adult_price) + (kids * (child_price or adult_price * Decimal("0.5"))) + (infants * (infant_price or Decimal("0")))
            first = random.choice(GUEST_FIRST_NAMES)
            last = random.choice(GUEST_LAST_NAMES)
            email = f"{first.lower()}.{last.lower()}{i}@{random.choice(GUEST_EMAIL_DOMAINS)}"

            booking = Booking.objects.create(
                excursion_availability=availability,
                excursion=excursion,
                date=booking_date,
                guest_name=f"{first} {last}",
                guest_email=email,
                total_adults=adults,
                total_kids=kids,
                total_infants=infants,
                price=base_price,
                total_price=base_price,
                payment_status=random.choice(["pending", "completed", "completed", "completed"]),
                partial_paid=Decimal("0") if random.random() > 0.3 else (base_price * Decimal("0.3")).quantize(Decimal("0.01")),
            )
            created["bookings"] += 1

            # Keep capacity in sync when payment is completed
            if booking.payment_status == "completed":
                from main.utils import BookingService

                BookingService.increment_booked_guests_for_booking(booking)

        return created
