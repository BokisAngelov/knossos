from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete, pre_save
from django.db import transaction
from django.conf import settings
from django.contrib.auth import get_user_model
from .models import Feedback, Excursion, ExcursionImage, ExcursionAvailability, Reservation, UserProfile
import os
import shutil
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

@receiver(post_save, sender=ExcursionAvailability)
def update_excursion_status_on_availability_save(sender, instance, created, **kwargs):
    """Update excursion status when availability is saved."""
    if instance.excursion.status != 'active' and instance.is_active:
        instance.excursion.status = 'active'
        instance.excursion.save()

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


@receiver(post_save, sender=Reservation)
def create_or_link_client_profile(sender, instance, created, **kwargs):
    """
    Auto-create or link User and UserProfile when a Reservation is created.
    This runs after a reservation is saved (either from DB or API).
    """
    # Check if client_profile field exists (migrations may not be run)
    if not hasattr(instance, 'client_profile'):
        logger.warning("Reservation model doesn't have client_profile field. Skipping client creation. Please run migrations.")
        return
    
    # Skip if client_profile is already set
    if instance.client_profile:
        logger.debug(f"Reservation {instance.voucher_id} already has a client_profile. Skipping.")
        return
    
    # Only process on creation
    if not created:
        logger.debug(f"Reservation {instance.voucher_id} is being updated without client_profile. Skipping signal.")
        return
    
    try:
        # Determine username (email or voucher-based)
        if instance.client_email:
            username = instance.client_email
            email = instance.client_email
        else:
            username = f'client_{instance.voucher_id}'
            email = ''
        
        # Check if user already exists by email or username
        existing_user = None
        if instance.client_email:
            # Check by email first
            existing_user = User.objects.filter(email=instance.client_email).first()
        
        if not existing_user:
            # Also check by username (for voucher-based usernames)
            existing_user = User.objects.filter(username=username).first()
        
        if existing_user:
            # Link to existing user's profile
            logger.info(f"Linking reservation {instance.voucher_id} to existing user {existing_user.username}")
            
            # Get or update the UserProfile
            profile, profile_created = UserProfile.objects.get_or_create(
                user=existing_user,
                defaults={
                    'name': instance.client_name or '',
                    'email': instance.client_email or '',
                    'phone': instance.client_phone or '',
                    'role': 'client',
                    'pickup_group': instance.pickup_group,
                    'status': 'active'
                }
            )
            
            if not profile_created:
                # Update profile fields from reservation (only if not empty)
                updated = False
                if instance.client_name and not profile.name:
                    profile.name = instance.client_name
                    updated = True
                if instance.client_phone and not profile.phone:
                    profile.phone = instance.client_phone
                    updated = True
                if instance.pickup_group and not profile.pickup_group:
                    profile.pickup_group = instance.pickup_group
                    updated = True
                
                if updated:
                    profile.save()
            
            # Link reservation to profile
            instance.client_profile = profile
            instance.save(update_fields=['client_profile'])
            
        else:
            # Create new user and profile
            logger.info(f"Creating new client user for reservation {instance.voucher_id}")
            
            try:
                # Create User (without password - voucher-only auth)
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=instance.client_name.split()[0] if instance.client_name and ' ' in instance.client_name else instance.client_name or '',
                    last_name=' '.join(instance.client_name.split()[1:]) if instance.client_name and ' ' in instance.client_name else ''
                )
                
                # User has no usable password initially (can set one later from profile)
                user.set_unusable_password()
                user.save()
                
            except Exception as user_error:
                # User might already exist due to race condition, try to get it
                logger.warning(f"Error creating user {username}: {str(user_error)}. Attempting to retrieve existing user.")
                user = User.objects.filter(username=username).first()
                if not user:
                    # Really can't create or find user, re-raise
                    raise
            
            # Create or get UserProfile
            profile, profile_created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'name': instance.client_name or '',
                    'email': instance.client_email or '',
                    'phone': instance.client_phone or '',
                    'role': 'client',
                    'pickup_group': instance.pickup_group,
                    'status': 'active'
                }
            )
            
            # Link reservation to profile
            instance.client_profile = profile
            instance.save(update_fields=['client_profile'])
            
            if profile_created:
                logger.info(f"Created client profile {profile.id} for user {user.username}")
            else:
                logger.info(f"Linked reservation {instance.voucher_id} to existing profile {profile.id}")
    
    except Exception as e:
        logger.error(f"Error creating/linking client profile for reservation {instance.voucher_id}: {str(e)}")
        # Don't raise - we don't want to break the reservation creation


@receiver(pre_save, sender=Reservation)
def update_client_profile_on_reservation_change(sender, instance, **kwargs):
    """
    Update linked UserProfile when reservation data changes.
    Only updates fields that are related to the user profile.
    """
    # Check if client_profile field exists (migrations may not be run)
    if not hasattr(instance, 'client_profile'):
        return
    
    if not instance.pk or not instance.client_profile:
        return
    
    try:
        # Get the old instance
        old_instance = Reservation.objects.get(pk=instance.pk)
        
        # Check if relevant fields changed
        profile = instance.client_profile
        updated = False
        
        # Update name if changed and profile name is empty or matches old value
        if instance.client_name != old_instance.client_name:
            if not profile.name or profile.name == old_instance.client_name:
                profile.name = instance.client_name
                updated = True
        
        # Update email if changed
        if instance.client_email != old_instance.client_email:
            if not profile.email or profile.email == old_instance.client_email:
                profile.email = instance.client_email
                updated = True
                # Also update User email
                if instance.client_email and profile.user:
                    profile.user.email = instance.client_email
                    profile.user.username = instance.client_email
                    profile.user.save()
        
        # Update phone if changed
        if instance.client_phone != old_instance.client_phone:
            if not profile.phone or profile.phone == old_instance.client_phone:
                profile.phone = instance.client_phone
                updated = True
        
        # Update pickup_group if changed
        if instance.pickup_group != old_instance.pickup_group:
            if not profile.pickup_group or profile.pickup_group == old_instance.pickup_group:
                profile.pickup_group = instance.pickup_group
                updated = True
        
        if updated:
            profile.save()
            logger.info(f"Updated client profile {profile.id} from reservation {instance.voucher_id}")
    
    except Reservation.DoesNotExist:
        # New reservation, will be handled by post_save
        pass
    except Exception as e:
        logger.error(f"Error updating client profile from reservation {instance.voucher_id}: {str(e)}")

@receiver(post_save, sender=UserProfile)
def update_reservation_on_user_profile_save(sender, instance, created, **kwargs):
    """
    Update reservation when UserProfile is saved.
    """
    if instance.role == 'client' and not created:
        try:
            # Get all reservations linked to this profile
            reservations = instance.reservations.all()
            
            # Update all reservations with the new profile data
            count = reservations.update(
                client_email=instance.email, 
                client_phone=instance.phone, 
                client_name=instance.name
            )
            
            if count > 0:
                voucher_ids = list(reservations.values_list('voucher_id', flat=True))
                logger.info(f"Updated {count} reservation(s) {voucher_ids} from user profile {instance.id}")
            
        except Exception as e:
            logger.error(f"Error updating reservation from user profile {instance.id}: {str(e)}")


