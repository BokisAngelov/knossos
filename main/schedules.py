from django.utils import timezone
from django_q.models import Schedule

FUNC = "main.tasks.run_management_command"

SCHEDULES = [
    {
        "name": "expire_reservation",
        "command": "expire_reservation",
        "cron": "0 2 * * *",
        "command_kwargs": {"send_emails": True},
    },
    {
        "name": "expire_booking",
        "command": "expire_booking",
        "cron": "5 2 * * *",
        "command_kwargs": {},
    },
    {
        "name": "expire_referral_codes",
        "command": "expire_referral_codes",
        "cron": "10 2 * * *",
        "command_kwargs": {},
    },
    {
        "name": "expire_availability",
        "command": "expire_availability",
        "cron": "15 2 * * *",
        "command_kwargs": {},
    },
    {
        "name": "expire_availability_days",
        "command": "expire_availability_days",
        "cron": "20 2 * * *",
        "command_kwargs": {},
    },
    {
        "name": "notify_groups_tomorrow",
        "command": "notify_groups_tomorrow",
        "cron": "0 16 * * *",
        "command_kwargs": {},
    },
    {
        "name": "warn_pending_bookings",
        "command": "warn_pending_bookings",
        "cron": "0 10 * * *",
        "command_kwargs": {"send_emails": True},
    },
]

def setup_schedules():
    created = 0
    updated = 0

    for cfg in SCHEDULES:
        name = cfg["name"]
        command = cfg["command"]
        cron = cfg["cron"]
        command_kwargs = cfg.get("command_kwargs") or {}

        obj, was_created = Schedule.objects.get_or_create(name=name)

        obj.func = FUNC
        obj.args = repr((command,))
        obj.kwargs = repr(command_kwargs)
        obj.schedule_type = Schedule.CRON
        obj.cron = cron
        obj.repeats = -1

        if not obj.next_run:
            obj.next_run = timezone.now()

        obj.save()

        if was_created:
            created += 1
        else:
            updated += 1

    return created, updated