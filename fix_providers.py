import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'knossos.settings')
django.setup()

from main.models import Excursion, UserProfile, Reservation, Hotel
from django.contrib.auth import get_user_model
from django.db import connection
from django.contrib.auth.models import User
from datetime import datetime, timedelta

User = get_user_model()

def fix_providers():
    
    
    res = Reservation.objects.all()

    for r in res:
        print('reservation created with id: ', r.hotel.name)





fix_providers() 