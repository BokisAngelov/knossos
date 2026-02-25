"""
Create or update all django-q schedules from main.schedules.
Run once after deploy or when you change schedule times.
Requires qcluster to be running for the schedules to execute.
"""
from django.core.management.base import BaseCommand
from main.schedules import setup_schedules


class Command(BaseCommand):
    help = "Create or update all django-q schedules (from main.schedules). Run once after deploy."

    def handle(self, *args, **options):
        created, updated = setup_schedules()
        self.stdout.write(self.style.SUCCESS(f"Schedules ready: {created} created, {updated} updated."))

