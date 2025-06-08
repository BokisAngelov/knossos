import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'knossos.settings')
django.setup()

from main.models import Excursion, UserProfile
from django.contrib.auth import get_user_model
from django.db import connection
from django.contrib.auth.models import User


User = get_user_model()

def fix_providers():
    Excursion.objects.filter(provider_id=2).update(provider=None)


fix_providers() 