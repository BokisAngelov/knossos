import os
import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "knossos.settings")
django.setup()

# Import models
from django.contrib.auth.models import User
from main.models import UserProfile, Region, PickupPoint, AvailabilityDays
from django.utils.text import slugify

# Create regions
regions = [
    'Larnaca',
    'Paphos',
    'Limassol',
    'Ayia Napa - Protaras',
]

AvailabilityDays.objects.all().delete()

# PickupPoint.objects.all().delete()

# regions = Region.objects.all().delete()

# for region in regions:
#     Region.objects.create(name=region, slug=slugify(region))

# regions = Region.objects.all()

# print(regions)

print("All regions deleted")


 
