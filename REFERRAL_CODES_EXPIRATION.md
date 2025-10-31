# Referral Codes Expiration System

This document explains how the referral code expiration system works and how to set it up.

## Overview

The system automatically marks referral codes as `inactive` when their expiration date passes. This is done through:

1. **Signal on Save**: Checks expiration whenever a code is saved
2. **Management Command**: Batch checks all codes (for scheduled tasks)

---

## How It Works

### 1. Automatic Check on Save (Signal)

Located in: `knossos/main/signals.py`

```python
@receiver(post_save, sender=ReferralCode)
def check_referral_code_expiration_on_save(sender, instance, created, **kwargs):
    """Check if referral code is expired when saved"""
```

**When it runs:**
- Every time a referral code is saved (create/update)
- Automatically marks code as `inactive` if expired

**Use case:**
- Admin edits a code in the profile
- Code is automatically checked and expired if needed

---

### 2. Management Command (Scheduled Task)

Located in: `knossos/main/management/commands/expire_referral_codes.py`

```bash
# Run the command
python manage.py expire_referral_codes

# Dry run (see what would be expired without changing anything)
python manage.py expire_referral_codes --dry-run
```

**Features:**
- ✅ Checks all active referral codes at once
- ✅ Marks expired codes as `inactive`
- ✅ Logs the action
- ✅ Shows detailed output of expired codes
- ✅ Dry-run mode for testing

**Example Output:**
```
Successfully expired 3 referral code(s).
  - JOHNS-20 (Agent: John Smith)
  - MARIA-15 (Agent: Maria Garcia)
  - ALEX-10 (Agent: Alex Johnson)
```

---

## Setting Up Scheduled Execution

You should run the `expire_referral_codes` command regularly to ensure codes are expired even if they're not being accessed/saved.

### Option 1: Windows Task Scheduler

1. Open **Task Scheduler**
2. Create a new task:
   - **Name**: Expire Referral Codes
   - **Trigger**: Daily at 2:00 AM
   - **Action**: Run program
     - Program: `python.exe`
     - Arguments: `manage.py expire_referral_codes`
     - Start in: `D:\Desktop\Bokis\ForMe\Python\Projects\knossos`

### Option 2: Cron Job (Linux/Mac)

Add to crontab:
```bash
# Run every day at 2:00 AM
0 2 * * * cd /path/to/knossos && python manage.py expire_referral_codes >> /var/log/expire_codes.log 2>&1
```

### Option 3: Django-Crontab (Recommended for Django)

1. Install django-crontab:
```bash
pip install django-crontab
```

2. Add to `settings.py`:
```python
INSTALLED_APPS = [
    # ... other apps
    'django_crontab',
]

CRONJOBS = [
    # Run every day at 2:00 AM
    ('0 2 * * *', 'django.core.management.call_command', ['expire_referral_codes']),
]
```

3. Add the cron job:
```bash
python manage.py crontab add
```

### Option 4: Celery Beat (For Production)

If you're using Celery:

```python
# tasks.py
from celery import shared_task
from django.core.management import call_command

@shared_task
def expire_referral_codes():
    call_command('expire_referral_codes')
```

```python
# celery.py
from celery.schedules import crontab

app.conf.beat_schedule = {
    'expire-referral-codes': {
        'task': 'main.tasks.expire_referral_codes',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
}
```

---

## Manual Execution

### From Command Line
```bash
# Check and expire codes
python manage.py expire_referral_codes

# Dry run (test mode)
python manage.py expire_referral_codes --dry-run
```

### From Django Shell
```python
from main.signals import check_all_expired_referral_codes

# Expire all expired codes
count = check_all_expired_referral_codes()
print(f"Expired {count} codes")
```

### From Django Admin or Views
```python
from main.signals import check_all_expired_referral_codes

def some_view(request):
    # Manually trigger expiration check
    count = check_all_expired_referral_codes()
    messages.info(request, f"Expired {count} referral codes")
    # ...
```

---

## Testing

### Test the Management Command

1. Create a test referral code with past expiration:
```python
from main.models import ReferralCode, UserProfile
from django.utils import timezone
from datetime import timedelta

agent = UserProfile.objects.filter(role='agent').first()
code = ReferralCode.objects.create(
    code='TEST-20',
    agent=agent,
    discount=20,
    expires_at=timezone.now() - timedelta(days=1),  # Yesterday
    status='active'
)
```

2. Run the command:
```bash
python manage.py expire_referral_codes --dry-run
```

3. Verify output shows the test code

4. Run without dry-run:
```bash
python manage.py expire_referral_codes
```

5. Check code is now inactive:
```python
code.refresh_from_db()
print(code.status)  # Should be 'inactive'
```

---

## Monitoring

### Check Logs

The system logs all expiration events to Django's logging system:

```python
# settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'logs/referral_codes.log',
        },
    },
    'loggers': {
        'main.signals': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

### Check Database

Query expired codes:
```sql
SELECT code, agent_id, expires_at, status 
FROM main_referralcode 
WHERE status = 'inactive' 
AND expires_at < NOW();
```

---

## Troubleshooting

### Command not found
```bash
# Make sure you're in the project directory
cd D:\Desktop\Bokis\ForMe\Python\Projects\knossos

# Activate virtual environment if using one
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

### Codes not expiring automatically
1. Check signal is registered (should be in `signals.py`)
2. Verify `apps.py` imports signals:
```python
# main/apps.py
def ready(self):
    import main.signals
```

### Scheduled task not running
- Windows: Check Task Scheduler history
- Linux/Mac: Check cron logs: `grep CRON /var/log/syslog`
- Django-crontab: Run `python manage.py crontab show`

---

## Best Practices

1. **Run daily**: Schedule the command to run once per day
2. **Off-peak hours**: Run during low-traffic times (2-4 AM)
3. **Monitor logs**: Check logs regularly for issues
4. **Test in staging**: Always test scheduling in staging environment first
5. **Dry run first**: Use `--dry-run` to verify what will be expired

---

## Related Files

- **Models**: `knossos/main/models.py` (ReferralCode model)
- **Signals**: `knossos/main/signals.py` (Expiration logic)
- **Management Command**: `knossos/main/management/commands/expire_referral_codes.py`
- **Views**: `knossos/main/views.py` (manage_referral_codes)
- **Template**: `knossos/main/templates/main/accounts/profile.html`

---

## Summary

✅ **Automatic expiration on save** - Codes checked when edited  
✅ **Batch expiration command** - Regular scheduled checks  
✅ **Dry-run mode** - Test before making changes  
✅ **Detailed logging** - Track all expiration events  
✅ **Multiple scheduling options** - Choose what works best for you  

The system ensures referral codes are always up-to-date and expired codes are properly marked as inactive! 🎉

