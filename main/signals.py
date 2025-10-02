from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete
from django.db import transaction
from .models import Feedback, Excursion


@receiver(post_save, sender=Feedback)
def update_excursion_rating_on_save(sender, instance, created, **kwargs):
    """Update excursion overall rating when feedback is saved."""
    if created:  # Only update when new feedback is created
        update_excursion_rating(instance.excursion)


@receiver(post_delete, sender=Feedback)
def update_excursion_rating_on_delete(sender, instance, **kwargs):
    """Update excursion overall rating when feedback is deleted."""
    update_excursion_rating(instance.excursion)


def update_excursion_rating(excursion):
    """Calculate and update the overall rating for an excursion."""
    with transaction.atomic():
        ratings = excursion.feedback_entries.values_list('rating', flat=True)
        
        if ratings:
            # Calculate average rating
            average_rating = sum(ratings) / len(ratings)
            excursion.overall_rating = round(average_rating, 2)
        else:
            # No ratings, set to None
            excursion.overall_rating = None
        
        excursion.save(update_fields=['overall_rating'])
