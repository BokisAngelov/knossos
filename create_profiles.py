import os
import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "knossos.settings")
django.setup()

# Import models
from django.contrib.auth.models import User
from main.models import UserProfile, Region, PickupPoint, AvailabilityDays, DayOfWeek
from django.utils.text import slugify
from django.contrib.auth import get_user_model

# Create regions
regions = [
    'Larnaca',
    'Paphos',
    'Limassol',
    'Ayia Napa - Protaras',
]

weekdays = [
    'MON',
    'TUE',
    'WED',
    'THU',
    'FRI',
    'SAT',
    'SUN',
]

# (new loop for DayOfWeek)
for (code, _) in DayOfWeek.WEEKDAY_CHOICES:
    DayOfWeek.objects.get_or_create(code=code, defaults={'capacity': 0})

print("All weekdays (DayOfWeek) created (or updated) (with default capacity 0).")

# AvailabilityDays.objects.all().delete()

# PickupPoint.objects.all().delete()

# regions = Region.objects.all().delete()

# for region in regions:
#     Region.objects.create(name=region, slug=slugify(region))

# regions = Region.objects.all()

# print(regions)

# print("All regions deleted")

# (new block for superuser)
# from django.contrib.auth import get_user_model
# from django.contrib.auth.models import User

# # Fetch the superuser (assumed to be the one with is_superuser=True)
# superuser = User.objects.filter(is_superuser=True).first()
# if superuser:
#     # Create (or update) a UserProfile for the superuser with role 'admin'
#     UserProfile.objects.get_or_create(user=superuser, defaults={'role': 'admin', 'name': superuser.username, 'email': superuser.email})
#     # Ensure the superuser is also marked as staff
#     superuser.is_staff = True
#     superuser.save()
#     print("Updated superuser ({}): created (or updated) UserProfile (role='admin') and set is_staff=True.".format(superuser.username))
# else:
#     print("No superuser found.")

 
