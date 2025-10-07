from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete
from django.db import transaction
from django.conf import settings
from .models import Feedback, Excursion, ExcursionImage
import os
import shutil


@receiver(post_save, sender=Feedback)
def update_excursion_rating_on_save(sender, instance, created, **kwargs):
    """Update excursion overall rating when feedback is saved."""
    if created:  # Only update when new feedback is created
        update_excursion_rating(instance.excursion)


@receiver(post_delete, sender=Feedback)
def update_excursion_rating_on_delete(sender, instance, **kwargs):
    """Update excursion overall rating when feedback is deleted."""
    update_excursion_rating(instance.excursion)


@receiver(post_save, sender=Excursion)
def move_temp_images_on_excursion_save(sender, instance, created, **kwargs):
    """Move images from temp folder to permanent location when excursion is saved with an ID."""
    if instance.pk and instance.intro_image:
        move_image_from_temp(instance.intro_image, f"excursions/ex-{instance.pk}/")


@receiver(post_save, sender=ExcursionImage)
def move_temp_images_on_excursion_image_save(sender, instance, created, **kwargs):
    """Move images from temp folder to permanent location when excursion image is saved."""
    if instance.excursion.pk and instance.image:
        move_image_from_temp(instance.image, f"excursions/ex-{instance.excursion.pk}/")


def move_image_from_temp(image_field, target_folder):
    """Move an image from temp folder to target folder if it's currently in temp."""
    if not image_field or not image_field.name:
        return
    
    current_path = image_field.name
    if '/temp/' not in current_path:
        return  # Not in temp folder, nothing to do
    
    # Extract filename from current path
    filename = os.path.basename(current_path)
    new_path = os.path.join(target_folder, filename)
    
    # Full file system paths
    old_full_path = os.path.join(settings.MEDIA_ROOT, current_path)
    new_full_path = os.path.join(settings.MEDIA_ROOT, new_path)
    
    # Create target directory if it doesn't exist
    os.makedirs(os.path.dirname(new_full_path), exist_ok=True)
    
    # Move the file if it exists
    if os.path.exists(old_full_path):
        try:
            shutil.move(old_full_path, new_full_path)
            # Update the field with new path
            image_field.name = new_path
            # Save without triggering signals again
            image_field.instance.save(update_fields=[image_field.field.name])
        except (OSError, IOError) as e:
            # Log error but don't fail the save operation
            print(f"Error moving image from {old_full_path} to {new_full_path}: {e}")


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
