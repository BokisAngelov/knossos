"""
Tasks for django-q. Run the cluster with: python manage.py qcluster
"""
import logging
from django.core.management import call_command
from .utils import EmailService

logger = logging.getLogger(__name__)


def run_management_command(command_name, **kwargs):
    logger.info("Running management command %s kwargs=%s", command_name, kwargs)
    call_command(command_name, **kwargs)
    logger.info("Finished management command %s", command_name)

def send_dynamic_email_task(
    subject,
    recipient_list,
    email_body,
    email_title=None,
    preview_text=None,
    unsubscribe_url=None,
    email_kind='',
):
    """
    Background task: send one dynamic email and log via EmailService.
    Call via EmailService.send_dynamic_email_async() to enqueue.
    """
    return EmailService.send_dynamic_email(
        subject=subject,
        recipient_list=recipient_list,
        email_body=email_body,
        email_title=email_title,
        preview_text=preview_text,
        unsubscribe_url=unsubscribe_url,
        fail_silently=False,
        email_kind=email_kind,
    )
