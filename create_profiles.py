import os
import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "knossos.settings")
django.setup()

# Import models
from django.contrib.auth.models import User
from main.models import UserProfile, Region, PickupPoint, AvailabilityDays, DayOfWeek, Reservation, PickupGroup, Booking, Excursion
from django.utils.text import slugify
from django.contrib.auth import get_user_model

# book = Booking.objects.all().delete()
# print('bookings deleted')
# excursion = Excursion.objects.all().delete()
# print('excursions deleted')


res = Reservation.objects.all()
print(res)
for r in res:
    print('reservation: ' + str(r.voucher_id))
# print('reservations deleted')

# unique_field = 'name'  # or 'email', or a tuple like ('name', 'email')

# seen = set()
# duplicates = []

# for profile in UserProfile.objects.filter(role='provider').order_by('id'):
#     value = getattr(profile, unique_field)
#     if value in seen:
#         duplicates.append(profile)
#     else:
#         seen.add(value)

# print(f"Found {len(duplicates)} duplicates. Deleting...")

# for dup in duplicates:
#     user = dup.user
#     dup.delete()
#     print('deleted: ' + str(dup.name))
#     if user:
#         user.delete()
#         print('deleted: ' + str(user.username))
        







# for r in res:
#     print('reservation: ' + str(r))
    # r.pickup_group_id = 1
    # r.save()
# regions = [
#     'Larnaca',
#     'Paphos',
#     'Limassol',
#     'Ayia Napa - Protaras',
# ]

# weekdays = [
#     'MON',
#     'TUE',
#     'WED',
#     'THU',
#     'FRI',
#     'SAT',
#     'SUN',
# ]

# # (new loop for DayOfWeek)
# for (code, _) in DayOfWeek.WEEKDAY_CHOICES:
#     DayOfWeek.objects.get_or_create(code=code, defaults={'capacity': 0})

# print("All weekdays (DayOfWeek) created (or updated) (with default capacity 0).")

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

 
