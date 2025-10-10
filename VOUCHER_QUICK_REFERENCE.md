# Voucher System - Quick Reference Guide

## 🚀 Quick Start

### Apply Migrations
```bash
cd knossos
python manage.py makemigrations
python manage.py migrate
```

### Test the System
1. Enter a booking ID in the voucher form
2. User should be auto-logged in
3. User should be redirected to profile page

## 📋 Common Tasks

### Check if Voucher is Valid
```python
from main.models import Reservation

reservation = Reservation.objects.get(voucher_id='49941')
if reservation.is_valid:
    print("Voucher is valid!")
```

### Get Voucher Data
```python
from main.utils import VoucherService

reservation, created = VoucherService.authenticate_voucher('49941')
data = VoucherService.get_voucher_data(reservation)
# Returns: client_name, email, pickup info, dates, booking count
```

### Validate Voucher for Booking
```python
from main.utils import VoucherService
from django.core.exceptions import ValidationError

try:
    VoucherService.validate_for_booking(reservation, '2025-01-15')
    print("Can book on this date!")
except ValidationError as e:
    print(f"Cannot book: {e}")
```

### Get Client's Total Bookings
```python
# Via UserProfile
profile = UserProfile.objects.get(id=5)
total = profile.get_total_bookings()
spent = profile.get_total_spent()

# Via Reservation
reservation = Reservation.objects.get(voucher_id='49941')
count = reservation.get_bookings_count()
total = reservation.get_total_spent()
```

## 🔄 Data Flow

### New Voucher Entry:
```
User enters booking ID
    ↓
VoucherService checks DB
    ↓
Not found → Fetch from API
    ↓
Create Reservation
    ↓
Signal creates User + UserProfile
    ↓
Auto-login user
    ↓
Redirect to profile
```

### Existing Voucher:
```
User enters booking ID
    ↓
VoucherService finds in DB
    ↓
Validate is_valid
    ↓
Get linked UserProfile
    ↓
Auto-login user
    ↓
Redirect to profile
```

## 🛠️ Troubleshooting

### User not created?
**Check:**
1. Signal is registered (in `signals.py`)
2. No exceptions in logs
3. Reservation has `client_profile` set

**Debug:**
```python
reservation = Reservation.objects.get(voucher_id='49941')
print(f"Client Profile: {reservation.client_profile}")
print(f"User: {reservation.client_profile.user if reservation.client_profile else 'None'}")
```

### Auto-login not working?
**Check:**
1. User has `is_active=True`
2. Session middleware is enabled
3. Check browser console for errors

**Debug:**
```python
from django.contrib.auth import authenticate, login

user = reservation.client_profile.user
print(f"User active: {user.is_active}")
print(f"Has usable password: {user.has_usable_password()}")
```

### Voucher expired?
**Check:**
```python
reservation = Reservation.objects.get(voucher_id='49941')
print(f"Status: {reservation.status}")
print(f"Check-out: {reservation.check_out}")
print(f"Is valid: {reservation.is_valid}")
print(f"Is expired: {reservation.is_expired}")
```

**Fix:**
```python
# Update checkout date
reservation.check_out = datetime.date(2025, 12, 31)
reservation.save()
```

### Duplicate users created?
**This shouldn't happen** - signal checks for existing email.

**Verify:**
```python
from django.contrib.auth.models import User

# Find duplicates
emails = User.objects.values('email').annotate(count=Count('email')).filter(count__gt=1)
print(emails)
```

## 📊 Useful Queries

### All active vouchers:
```python
active_reservations = Reservation.objects.filter(
    status='active',
    check_out__gte=timezone.now().date()
)
```

### Vouchers with most bookings:
```python
from django.db.models import Count

top_vouchers = Reservation.objects.annotate(
    booking_count=Count('bookings')
).order_by('-booking_count')[:10]
```

### Clients without email:
```python
clients_no_email = UserProfile.objects.filter(
    role='client',
    email__isnull=True
)
# or
clients_no_email = UserProfile.objects.filter(
    role='client',
    needs_email_update=True  # Using the property won't work in queries
)
```

### Vouchers created today:
```python
from datetime import date

today_vouchers = Reservation.objects.filter(
    created_at__date=date.today()
)
```

## 🔐 Security Notes

### Cookies Set:
- `voucher_code` - The booking ID
- `pickup_group` - Pickup group ID
- `pickup_point` - Pickup point ID

All cookies:
- Max age: 86400 seconds (24 hours)
- Secure: True (HTTPS only)
- HttpOnly: False (accessible to JavaScript)
- SameSite: None

### Authentication:
- Voucher-based auth (no password initially)
- User can set password from profile later
- Session-based after login

## 🎨 Frontend Integration

### Check voucher:
```javascript
// From base.html
checkVoucher('49941');
```

### Clear voucher:
```javascript
clearVoucher();
// Clears cookies, logs out user
```

### Access in templates:
```django
{% if voucher_code %}
    Welcome, {{ voucher_data.client_name }}!
    <a href="{% url 'profile' voucher_data.client_profile_id %}">My Profile</a>
{% endif %}
```

## 📝 Admin Tasks

### Manually create client from reservation:
```python
from main.signals import create_or_link_client_profile

reservation = Reservation.objects.get(voucher_id='49941')
create_or_link_client_profile(
    sender=Reservation,
    instance=reservation,
    created=True
)
```

### Reset client password:
```python
user = User.objects.get(email='client@example.com')
user.set_password('new_password_123')
user.save()
```

### Link existing user to reservation:
```python
reservation = Reservation.objects.get(voucher_id='49941')
profile = UserProfile.objects.get(user__email='client@example.com')
reservation.client_profile = profile
reservation.save()
```

## 🔍 Logging

All voucher operations are logged. Check for:
- `Voucher {code} found in database`
- `Voucher {code} not in database, fetching from API`
- `Voucher {code} created from API`
- `Creating new client user for reservation {id}`
- `Linking reservation {id} to existing user {username}`

Enable debug logging in settings:
```python
LOGGING = {
    'loggers': {
        'main': {
            'level': 'DEBUG',
        },
    },
}
```

## 🎯 Key Properties & Methods

### Reservation:
- `reservation.is_valid` → bool
- `reservation.is_expired` → bool
- `reservation.get_bookings_count()` → int
- `reservation.get_total_spent()` → Decimal

### UserProfile:
- `profile.needs_email_update` → bool
- `profile.get_total_bookings()` → int
- `profile.get_total_spent()` → Decimal

### VoucherService:
- `VoucherService.authenticate_voucher(code)` → (Reservation, bool)
- `VoucherService.validate_for_booking(reservation, date)` → bool
- `VoucherService.get_voucher_data(reservation)` → dict
- `VoucherService.clear_voucher_cookies(response)` → JsonResponse

---

**Quick Links:**
- Full documentation: `VOUCHER_IMPLEMENTATION_SUMMARY.md`
- Models: `knossos/main/models.py`
- Service: `knossos/main/utils.py` → VoucherService
- Signals: `knossos/main/signals.py`
- View: `knossos/main/views.py` → retrive_voucher()

