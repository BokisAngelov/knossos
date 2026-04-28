from django.core.management.base import BaseCommand

from main.models import DayOfWeek


class Command(BaseCommand):
    help = "Create DayOfWeek rows if they do not already exist."

    def handle(self, *args, **options):
        created_codes = []
        existing_codes = []

        for code, _label in DayOfWeek.WEEKDAY_CHOICES:
            _obj, created = DayOfWeek.objects.get_or_create(code=code)
            if created:
                created_codes.append(code)
            else:
                existing_codes.append(code)

        self.stdout.write(
            self.style.SUCCESS(
                f"DayOfWeek sync complete. Created: {len(created_codes)}, Existing: {len(existing_codes)}."
            )
        )
