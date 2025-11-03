from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete, pre_save
from django.db import transaction
from django.conf import settings
from django.contrib.auth import get_user_model
from .models import Feedback, Excursion, ExcursionImage, ExcursionAvailability, Reservation, UserProfile, Group, AvailabilityDays, ReferralCode
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

@receiver(pre_save, sender=Reservation)
def detect_departure_time_change(sender, instance, **kwargs):
    """
    Detect if departure time has changed and set notification flag.
    """
    if not instance.pk:
        # New reservation, skip
        return
    
    try:
        old_instance = Reservation.objects.get(pk=instance.pk)
        
        # Check if departure_time has changed
        if old_instance.departure_time != instance.departure_time:
            logger.info(f"Departure time changed for reservation {instance.voucher_id}: {old_instance.departure_time} -> {instance.departure_time}")
            instance.departure_time_updated = True
            # TODO: send email notification and maybe sms
        
    except Reservation.DoesNotExist:
        # New reservation
        pass


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


@receiver(pre_save, sender=Group)
def track_group_status_change(sender, instance, **kwargs):
    """Track the old status before save to detect changes."""
    if instance.pk:
        try:
            old_instance = Group.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Group.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Group)
def handle_group_status_change(sender, instance, created, **kwargs):
    """
    When a Group's status changes to 'sent', mark the corresponding AvailabilityDays as inactive.
    This ensures that the specific date becomes unavailable for new bookings.
    """
    if not instance.excursion or not instance.date:
        logger.warning(f"Group {instance.name} has no excursion or date set. Skipping availability update.")
        return
    
    # Only proceed if status changed to 'sent'
    if instance.status != 'sent':
        return
    
    # Check if this is actually a status change (not already sent)
    old_status = getattr(instance, '_old_status', None)
    if not created and old_status == 'sent':
        # Status was already 'sent', no need to update
        return
    
    try:
        # Find all AvailabilityDays for this excursion and date
        availability_days = AvailabilityDays.objects.filter(
            excursion_availability__excursion=instance.excursion,
            date_day=instance.date,
            status='active'
        )
        
        logger.info(f"Signal triggered: Marking AvailabilityDays as inactive for Group '{instance.name}'")
        logger.info(f"  - Excursion: {instance.excursion.title} (ID: {instance.excursion.id})")
        logger.info(f"  - Date: {instance.date}")
        logger.info(f"  - Found {availability_days.count()} active AvailabilityDays")
        
        updated_count = availability_days.update(status='inactive')
        
        if updated_count > 0:
            logger.info(
                f"✓ Group '{instance.name}' marked as sent. "
                f"Disabled {updated_count} AvailabilityDays for {instance.excursion.title} on {instance.date}"
            )
        else:
            logger.warning(
                f"✗ Group '{instance.name}' marked as sent but no active AvailabilityDays found "
                f"for {instance.excursion.title} on {instance.date}"
            )
    except Exception as e:
        logger.error(f"Error updating AvailabilityDays for group {instance.name}: {str(e)}")


@receiver(post_delete, sender=Group)
def handle_group_deletion(sender, instance, **kwargs):
    """
    When a Group is deleted, reactivate the corresponding AvailabilityDays
    (but only if there are no other 'sent' groups for the same excursion and date).
    """
    if not instance.excursion or not instance.date:
        return
    
    # Only reactivate if the deleted group was 'sent'
    if instance.status != 'sent':
        return
    
    try:
        # Check if there are other 'sent' groups for the same excursion and date
        other_sent_groups = Group.objects.filter(
            excursion=instance.excursion,
            date=instance.date,
            status='sent'
        ).exists()
        
        if not other_sent_groups:
            # No other sent groups for this date, so reactivate
            availability_days = AvailabilityDays.objects.filter(
                excursion_availability__excursion=instance.excursion,
                date_day=instance.date,
                status='inactive'
            )
            
            reactivated_count = availability_days.update(status='active')
            
            if reactivated_count > 0:
                logger.info(
                    f"Group '{instance.name}' deleted. "
                    f"Reactivated {reactivated_count} AvailabilityDays for {instance.excursion.title} on {instance.date}"
                )
        else:
            logger.info(
                f"Group '{instance.name}' deleted but other sent groups exist for "
                f"{instance.excursion.title} on {instance.date}. Not reactivating dates."
            )
    except Exception as e:
        logger.error(f"Error reactivating AvailabilityDays after deleting group {instance.name}: {str(e)}")


@receiver(post_save, sender=ReferralCode)
def check_referral_code_expiration_on_save(sender, instance, created, **kwargs):
    """
    Check if referral code is expired and update status accordingly.
    This runs every time a referral code is saved.
    
    Args:
        sender: The ReferralCode model class
        instance: The actual ReferralCode instance being saved
        created: Boolean indicating if this is a new instance
        **kwargs: Additional keyword arguments
    """
    # Only check expiration for existing codes that are active
    # Skip for newly created codes to avoid recursion
    if not created and instance.status == 'active':
        was_expired = instance.check_and_update_expiration()
        if was_expired:
            logger.info(f"Referral code '{instance.code}' automatically marked as inactive (expired)")


@receiver(pre_save, sender=UserProfile)
def track_agent_status_change(sender, instance, **kwargs):
    """Track the old status before save to detect changes for agents."""
    if instance.pk and instance.role == 'agent':
        try:
            old_instance = UserProfile.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except UserProfile.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=UserProfile)
def handle_agent_status_change(sender, instance, created, **kwargs):
    """
    When an agent's status changes, update their referral codes accordingly:
    - If agent becomes inactive: deactivate all active referral codes
    - If agent becomes active: reactivate non-expired referral codes
    """
    # Only process for agents, not new profiles
    if created or instance.role != 'agent':
        return
    
    # Check if status changed
    old_status = getattr(instance, '_old_status', None)
    if old_status is None or old_status == instance.status:
        return
    
    try:
        from django.utils import timezone
        
        if instance.status == 'inactive' and old_status == 'active':
            # Agent became inactive - deactivate all active referral codes
            updated_count = ReferralCode.objects.filter(
                agent=instance,
                status='active'
            ).update(status='inactive')
            
            if updated_count > 0:
                logger.info(
                    f"Agent '{instance.name}' (ID: {instance.id}) became inactive. "
                    f"Deactivated {updated_count} referral code(s)."
                )
        
        elif instance.status == 'active' and old_status == 'inactive':
            # Agent became active - reactivate non-expired referral codes
            now = timezone.now()
            updated_count = ReferralCode.objects.filter(
                agent=instance,
                status='inactive',
                expires_at__gt=now
            ).update(status='active')
            
            if updated_count > 0:
                logger.info(
                    f"Agent '{instance.name}' (ID: {instance.id}) became active. "
                    f"Reactivated {updated_count} non-expired referral code(s)."
                )
    
    except Exception as e:
        logger.error(f"Error updating referral codes for agent {instance.name} (ID: {instance.id}): {str(e)}")


def check_all_expired_referral_codes():
    """
    Utility function to check all active referral codes and expire them if needed.
    This should be called from a management command or scheduled task.
    
    Usage:
        From Django shell:
        >>> from main.signals import check_all_expired_referral_codes
        >>> count = check_all_expired_referral_codes()
        
        From management command:
        python manage.py expire_referral_codes
    
    Returns:
        int: Number of codes that were expired
    """
    from django.utils import timezone
    
    expired_codes = ReferralCode.objects.filter(
        status='active',
        expires_at__lt=timezone.now()
    )
    
    count = expired_codes.update(status='inactive')
    
    if count > 0:
        logger.info(f"Expired {count} referral code(s) via batch check")
    
    return count


