"""
Tasks for django-q. Run the cluster with: python manage.py qcluster
"""
from .utils import EmailService


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
