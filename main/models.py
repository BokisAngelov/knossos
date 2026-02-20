from django.db import models
from django.conf import settings
from datetime import datetime



def excursion_intro_image_path(instance, filename):
    # If the instance doesn't have an ID yet (new excursion), use a temporary path
    if not instance.pk:
        return f"excursions/temp/{filename}"
    # For existing excursions, use their ID
    return f"excursions/ex-{instance.pk}/{filename}"

def excursion_image_path(instance, filename):
    # If the excursion doesn't have an ID yet, use a temporary path
    if not instance.excursion.pk:
        return f"excursions/temp/{filename}"
    # For existing excursions, use their ID
    return f"excursions/ex-{instance.excursion.pk}/{filename}"

class Category(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']

class Tag(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class Region(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, null=True, blank=True)
    def __str__(self):
        return self.name
    
class PickupGroup(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=255, unique=True, null=True, blank=True)
    priority = models.PositiveIntegerField(default=0)
    # cl_id = models.IntegerField(null=True, blank=True, unique=True)
    # region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, related_name='pickup_groups')
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']

class UserProfile(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    ROLE_CHOICES = [
        ('provider', 'Provider'),
        ('representative', 'Representative'),
        ('client', 'Client'),
        ('guide', 'Guide'),
        ('admin', 'Admin'),
        ('agent', 'Agent'),
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    created_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    role = models.CharField(max_length=15, choices=ROLE_CHOICES)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='active')
    address = models.CharField(max_length=255, null=True, blank=True)
    zipcode = models.CharField(max_length=255, null=True, blank=True)
    # region = models.ForeignKey(Region, on_delete=models.SET_NULL, blank=True, null=True, related_name='user_profiles')
    pickup_group = models.ForeignKey(PickupGroup, on_delete=models.SET_NULL, blank=True, null=True, related_name='user_profiles')
    password_reset_token = models.CharField(max_length=255, null=True, blank=True)
    email_verification_token = models.CharField(max_length=255, null=True, blank=True)
    is_superadmin = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.name
    
    def get_total_bookings(self):
        """Get total number of excursion bookings for this user"""
        if self.user:
            return self.user.bookings.count()
        return 0

    def get_total_bookings_referral(self):
        from django.db.models import Sum
        """Get total number of excursion bookings for this user"""
        total_bookings = 0
        total_spent = 0
        if self.user:
            referral_codes = ReferralCode.objects.filter(agent=self)
            for referral_code in referral_codes:
                bookings = Booking.objects.filter(referral_code=referral_code)
                total_bookings += bookings.count()
                total_spent += bookings.aggregate(total=Sum('total_price'))['total'] or 0
            return total_bookings, total_spent
        return 0, 0
    
    def get_total_spent(self):
        """Calculate total amount spent on bookings"""
        from django.db.models import Sum
        if self.user:
            total = self.user.bookings.aggregate(total=Sum('total_price'))['total']
            return total or 0
        return 0
    
    @property
    def needs_email_update(self):
        """Check if client needs to update their email"""
        return self.role == 'client' and not self.email_verified
    
    def get_latest_active_referral_code(self):
        """Get the latest active referral code for this agent"""
        from django.utils import timezone
        if self.role == 'agent':
            return self.referral_codes.filter(
                status='active',
                expires_at__gt=timezone.now()
            ).order_by('-created_at').first()
        return None
    
    def get_active_referral_codes_count(self):
        """Get count of active referral codes for this agent"""
        from django.utils import timezone
        if self.role == 'agent':
            return self.referral_codes.filter(
                status='active',
                expires_at__gt=timezone.now()
            ).count()
        return 0
   

class ReferralCode(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    code = models.CharField(max_length=255, unique=True)
    agent = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='referral_codes', limit_choices_to={'role': 'agent'})
    discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=255, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code

    class Meta:
        ordering = ['expires_at']
    
    @property
    def is_expired(self):
        """Check if referral code has expired"""
        from django.utils import timezone
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def check_and_update_expiration(self):
        """Check if code is expired and update status accordingly"""
        if self.is_expired and self.status == 'active':
            self.status = 'inactive'
            self.save(update_fields=['status'])
            return True
        return False
    
    @staticmethod
    def generate_unique_code(agent_name, discount):
        """
        Generate a unique referral code based on agent name and discount.
        Format: AGENTNAME-DISCOUNT (up to 10 chars)
        Example: JOHNS-20 or JSMITH15
        """
        import re
        import random
        import string
        
        # Clean agent name - remove special characters and spaces
        clean_name = re.sub(r'[^a-zA-Z]', '', agent_name).upper()
        
        # Format discount as integer if it's a whole number
        if discount == int(discount):
            discount_str = str(int(discount))
        else:
            discount_str = str(discount).replace('.', '')[:3]
        
        # Create base code (try different combinations)
        # Try: FIRSTNAME-DISCOUNT
        name_parts = agent_name.split()
        if len(name_parts) > 0:
            first_name = re.sub(r'[^a-zA-Z]', '', name_parts[0]).upper()
            base_code = f"{first_name[:5]}-{discount_str}"
        else:
            base_code = f"{clean_name[:5]}-{discount_str}"
        
        # Ensure it's max 10 characters
        base_code = base_code[:10]
        
        # Check if code exists, if so add random chars
        code = base_code
        counter = 0
        while ReferralCode.objects.filter(code=code).exists():
            counter += 1
            # Add random characters
            if counter < 100:
                random_suffix = random.choice(string.ascii_uppercase) + random.choice(string.digits)
                # Trim base to make room for random suffix
                trimmed_base = base_code[:8]
                code = f"{trimmed_base}{random_suffix}"
            else:
                # Fallback to completely random code
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        
        return code
    
class DayOfWeek(models.Model):
    MON = 'MON'
    TUE = 'TUE'
    WED = 'WED'
    THU = 'THU'
    FRI = 'FRI'
    SAT = 'SAT'
    SUN = 'SUN'
    WEEKDAY_CHOICES = [
        (MON, 'Monday'),
        (TUE, 'Tuesday'),
        (WED, 'Wednesday'),
        (THU, 'Thursday'),
        (FRI, 'Friday'),
        (SAT, 'Saturday'),
        (SUN, 'Sunday'),
    ]
    code = models.CharField(max_length=3, choices=WEEKDAY_CHOICES, unique=True)
    # capacity = models.PositiveIntegerField(default=0)

    def __str__(self):
        return dict(self.WEEKDAY_CHOICES)[self.code]
         
class PickupPoint(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

    # TYPE_CHOICES = [
    #     ('hotel', 'Hotel'),
    #     ('port', 'Port'),
    #     ('airport', 'Airport'),
    #     ('bus_station', 'Bus Station'),
    #     ('other', 'Other'),
    # ]
    
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True, null=True)
    # status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='active')
    # type = models.CharField(max_length=15, choices=TYPE_CHOICES, default='other')
    pickup_group = models.ForeignKey(PickupGroup, on_delete=models.SET_NULL, null=True, related_name='pickup_points')
    google_maps_link = models.CharField(max_length=255, blank=True, null=True)
    priority = models.PositiveIntegerField(default=0)    

    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']
    
class Excursion(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    intro_image = models.ImageField(upload_to=excursion_intro_image_path, blank=True, null=True)
    category = models.ManyToManyField(Category, related_name='excursions', blank=True, null=True)
    tags = models.ManyToManyField(Tag, related_name='excursions', blank=True, null=True)
    overall_rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='inactive')
    full_day = models.BooleanField(default=False)
    on_request = models.BooleanField(default=False)
    provider = models.ForeignKey(UserProfile, on_delete=models.SET_NULL,blank=True, null=True, related_name='excursions_provider', limit_choices_to={'role': 'provider'})
    # guide = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, blank=True, null=True, related_name='excursions_guide', limit_choices_to={'role': 'guide'})

    def __str__(self):
        return self.title

class ExcursionImage(models.Model):
    excursion = models.ForeignKey(Excursion, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to=excursion_image_path)
    alt_text = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0, help_text="Order of image in gallery")
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"Image for {self.excursion.title}"

class Feedback(models.Model):
    excursion = models.ForeignKey(Excursion, on_delete=models.CASCADE, related_name='feedback_entries')
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='feedbacks')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback by {self.author.username} for {self.excursion.title}"

class ExcursionAvailability(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    excursion = models.ForeignKey(Excursion, on_delete=models.CASCADE, related_name='availabilities')
    created_at = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField()
    end_date = models.DateField()
    pickup_start_time = models.TimeField(null=True, blank=True)
    pickup_end_time = models.TimeField(null=True, blank=True)
    regions = models.ManyToManyField(Region, blank=True, related_name='availabilities')
    max_guests = models.PositiveIntegerField()
    booked_guests = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    weekdays = models.ManyToManyField(DayOfWeek, blank=True)
    pickup_groups = models.ManyToManyField(PickupGroup, blank=True, related_name='availabilities')
    pickup_points = models.ManyToManyField(PickupPoint, blank=True, related_name='availabilities')
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # pickup_time_estimation 

    adult_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    child_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    infant_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='active')
    
    def __str__(self):
        return f"{self.excursion.title} - {self.start_date} to {self.end_date}"

    def clean(self):
        """
        Model-level validation to ensure data integrity.
        This runs before save() and raises ValidationError if invalid.
        """
        from django.core.exceptions import ValidationError
        from .utils import AvailabilityValidationService
        
        # Validate date range
        if self.start_date and self.end_date:
            try:
                AvailabilityValidationService.validate_date_range(
                    self.start_date, 
                    self.end_date
                )
            except ValidationError as e:
                raise ValidationError({'end_date': e.message})
        
        # Note: We can't validate M2M relationships here because they don't exist yet
        # until after save(). M2M validation should be done in the form or after save.

    def validate_overlap(self):
        """
        Validate that this availability doesn't conflict with existing ones.
        This must be called AFTER save() when M2M relationships exist.
        
        Raises:
            ValidationError: If overlap is detected
        """
        from .utils import AvailabilityValidationService
        
        # Get current M2M relationships
        region_ids = list(self.regions.values_list('id', flat=True))
        pickup_point_ids = list(self.pickup_points.values_list('id', flat=True))
        
        # Check for overlap
        has_conflict, error_details = AvailabilityValidationService.check_overlap(
            excursion=self.excursion,
            start_date=self.start_date,
            end_date=self.end_date,
            regions=region_ids,
            pickup_points=pickup_point_ids,
            current_availability_id=self.pk
        )
        
        if has_conflict:
            from django.core.exceptions import ValidationError
            raise ValidationError(' '.join(error_details))

    def update_status(self):
        if self.end_date < datetime.now().date():
            self.is_active = False
            self.save()

class AvailabilityDays(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    created_at = models.DateTimeField(auto_now_add=True)
    # excursion = models.ForeignKey(Excursion, on_delete=models.CASCADE, related_name='availability_days')
    excursion_availability = models.ForeignKey(ExcursionAvailability, on_delete=models.CASCADE, related_name='availability_days', null=True)
    date_day = models.DateField()
    capacity = models.PositiveIntegerField(default=0)
    booked_guests = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=255, choices=STATUS_CHOICES, default='active')

    def __str__(self):
        return f"{self.excursion_availability.excursion.title} - {self.date_day}"

class PickupGroupAvailability(models.Model):
    excursion_availability = models.ForeignKey(ExcursionAvailability, on_delete=models.CASCADE, related_name='pickup_group_availabilities')
    pickup_group = models.ForeignKey(PickupGroup, on_delete=models.SET_NULL, null=True, related_name='pickup_group_availabilities')
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.excursion_availability.excursion.title} - {self.pickup_group.name}"

class PaymentMethod(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class JCCGatewayConfig(models.Model):
    """
    Configuration model for JCC Payment Gateway.
    Stores credentials and URLs for JCC integration.
    Only one active configuration should exist at a time.
    """
    ENVIRONMENT_CHOICES = [
        ('sandbox', 'Sandbox/Test'),
        ('production', 'Production'),
    ]
    
    name = models.CharField(
        max_length=255,
        help_text="Configuration name (e.g., 'JCC Sandbox Config' or 'JCC Production Config')"
    )
    environment = models.CharField(
        max_length=20,
        choices=ENVIRONMENT_CHOICES,
        default='sandbox',
        help_text="Environment type"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only one active configuration should exist. Set others to inactive."
    )
    
    # API Credentials
    username = models.CharField(
        max_length=255,
        help_text="JCC API username"
    )
    password = models.CharField(
        max_length=255,
        help_text="JCC API password"
    )
    
    # API Endpoints
    register_url = models.URLField(
        max_length=500,
        help_text="URL for register.do endpoint (e.g., https://gateway-test.jcc.com.cy/payment/rest/register.do)"
    )
    status_url = models.URLField(
        max_length=500,
        help_text="URL for getOrderStatusExtended.do endpoint (e.g., https://gateway-test.jcc.com.cy/payment/rest/getOrderStatusExtended.do)"
    )
    
    # Default settings
    default_currency = models.CharField(
        max_length=3,
        default='978',
        help_text="Currency code (ISO 4217 numeric, e.g., 978 for EUR, 840 for USD)"
    )
    default_language = models.CharField(
        max_length=10,
        default='en',
        help_text="Default language code (e.g., 'en', 'el')"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "JCC Gateway Configuration"
        verbose_name_plural = "JCC Gateway Configurations"
        ordering = ['-is_active', '-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.environment})"
    
    def save(self, *args, **kwargs):
        """
        Ensure only one active configuration exists at a time.
        """
        if self.is_active:
            # Set all other configs to inactive
            JCCGatewayConfig.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active_config(cls):
        """
        Get the currently active JCC configuration.
        Returns None if no active configuration exists.
        """
        return cls.objects.filter(is_active=True).first()

class Hotel(models.Model):
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, null=True, blank=True)
    zipcode = models.CharField(max_length=255, null=True, blank=True)
    pickup_group = models.ForeignKey(PickupGroup, on_delete=models.SET_NULL,blank=True, null=True, related_name='hotels')
    # region = models.ForeignKey(Region, on_delete=models.SET_NULL, blank=True, null=True, related_name='hotels')
    phone_number = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']

class Reservation(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    voucher_id = models.CharField(max_length=255, unique=True)
    hotel = models.ForeignKey(Hotel, on_delete=models.SET_NULL, null=True, related_name='reservations')
    client_name = models.CharField(max_length=255, blank=True)
    client_email = models.EmailField(blank=True, null=True)
    client_phone = models.CharField(max_length=255, blank=True, null=True)
    total_adults = models.PositiveIntegerField(null=True, blank=True)
    total_kids = models.PositiveIntegerField(null=True, blank=True)

    check_in = models.DateField()
    check_out = models.DateField()
    flight_number = models.CharField(max_length=255, blank=True)
    pickup_group = models.ForeignKey(PickupGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='reservations')
    pickup_point = models.ForeignKey(PickupPoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='reservations')
    departure_time = models.TimeField(null=True, blank=True)
    departure_time_updated = models.BooleanField(default=False)
    
    status = models.CharField(max_length=255, choices=STATUS_CHOICES, default='active')
    
    # Link to client UserProfile
    client_profile = models.ForeignKey(
        UserProfile, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reservations',
        limit_choices_to={'role': 'client'}
    )
    
    # Tracking fields
    first_used_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return self.voucher_id
    
    @property
    def is_valid(self):
        """Check if reservation/voucher is currently valid"""
        from django.utils import timezone
        return (
            self.status == 'active' and
            self.check_out >= timezone.now().date()
        )
    
    @property
    def is_expired(self):
        """Check if voucher has expired"""
        from django.utils import timezone
        return self.check_out < timezone.now().date()
    
    def update_status(self):
        """Update status based on checkout date"""
        if self.check_out < datetime.now().date():
            self.status = 'inactive'
            self.save()
        return True
    
    def get_bookings_count(self):
        """Get total number of bookings made with this voucher"""
        return self.bookings.count()
    
    def get_total_spent(self):
        """Calculate total amount spent across all bookings"""
        from django.db.models import Sum
        total = self.bookings.aggregate(total=Sum('total_price'))['total']
        return total or 0

class Booking(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    voucher_id = models.ForeignKey(Reservation, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    excursion_availability = models.ForeignKey(ExcursionAvailability, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    date = models.DateField(null=True, blank=True)
    pickup_point = models.ForeignKey(PickupPoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    regions = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    guest_name = models.CharField(max_length=255, null=True, blank=True)
    guest_email = models.EmailField(null=True, blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    partial_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    partial_paid_method = models.CharField(blank=True, choices=PAYMENT_METHOD_CHOICES, default='', max_length=255, null=True)
    total_adults = models.PositiveIntegerField(null=True, blank=True)
    total_kids = models.PositiveIntegerField(null=True, blank=True)
    total_infants = models.PositiveIntegerField(null=True, blank=True)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, null=True, blank=True, default='pending')
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleteByUser = models.BooleanField(default=False)
    confirmTime = models.BooleanField(default=False)
    confirm_time_at = models.DateTimeField(null=True, blank=True, help_text="When the user confirmed the pickup time")
    referral_code = models.ForeignKey(ReferralCode, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    referral_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=0)
    jcc_order_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        help_text="JCC Payment Gateway order ID (orderId from register.do response)"
    )
    access_token = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="Secure token for non-logged-in users to access their booking"
    )

    def __str__(self):
        return f"Booking #{self.id} by {self.user.username if self.user else 'Guest'}"
    
    def generate_access_token(self):
        """Generate a secure access token for non-logged-in users."""
        import secrets
        import hashlib
        # Generate a secure random token
        token = secrets.token_urlsafe(32)
        # Hash it for storage (optional, but we'll store the raw token for simplicity)
        # In production, you might want to hash it
        return token
    
    @property
    def get_base_price(self):
        """Get the original price before any discounts or payments"""
        return self.price or 0
    
    @property
    def get_discounted_price(self):
        """Get price after referral discount but before partial payment"""
        base_price = self.get_base_price
        discount = self.referral_discount_amount or 0
        return base_price - discount
    
    @property
    def get_final_price(self):
        """Get final price after all discounts and partial payments"""
        discounted_price = self.get_discounted_price
        partial_paid = self.partial_paid or 0
        return discounted_price - partial_paid
    
    @property
    def get_referral_discount_percentage(self):
        """Get the referral discount percentage if code exists"""
        if self.referral_code:
            return self.referral_code.discount
        return 0
    
    class Meta:
        ordering = ['created_at']

class Transaction(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='transactions')
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transaction #{self.id} for Booking #{self.booking.id}"
    
    class Meta:
        ordering = ['created_at']

class Bus(models.Model):
    name = models.CharField(max_length=255)
    capacity = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return self.name + " - " + str(self.capacity)
    
    class Meta:
        verbose_name = 'Bus'
        verbose_name_plural = 'Buses'
        ordering = ['name']

class Group(models.Model):
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('not_sent', 'Not Sent'),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    excursion = models.ForeignKey(Excursion, on_delete=models.CASCADE, related_name='groups', null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    bookings = models.ManyToManyField('Booking', related_name='transport_groups', blank=True)
    bus = models.ForeignKey(Bus, on_delete=models.SET_NULL, null=True, blank=True, related_name='groups')
    guide = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='groups_guide', limit_choices_to={'role': 'guide'})
    provider = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='groups_provider', limit_choices_to={'role': 'provider'})
    status = models.CharField(max_length=255, choices=STATUS_CHOICES, default='not_sent')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.excursion.title} ({self.date})"
    
    @property
    def total_guests(self):
        """Calculate total number of guests from all bookings in this group"""
        total = 0
        for booking in self.bookings.all():
            total += (booking.total_adults or 0) + (booking.total_kids or 0) + (booking.total_infants or 0)
        return total
    
    @property
    def is_at_capacity(self):
        """Check if group has reached or exceeded bus capacity"""
        if not self.bus:
            return False
        return self.total_guests >= self.bus.capacity

    @property
    def capacity_warning(self):
        """Check if group is approaching bus capacity"""
        if not self.bus:
            return False
        return self.total_guests >= (self.bus.capacity - 5)
    
    @property
    def remaining_capacity(self):
        """Get remaining capacity before hitting bus capacity"""
        if not self.bus:
            return 0
        return max(0, self.bus.capacity - self.total_guests)
    
    class Meta:
        verbose_name = 'Transport Group'
        verbose_name_plural = 'Transport Groups'
        ordering = ['-date', 'status']  

class GroupPickupPoint(models.Model):
    """Store pickup times for each pickup point in a transport group"""
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='pickup_times')
    pickup_point = models.ForeignKey(PickupPoint, on_delete=models.CASCADE, related_name='group_pickup_times')
    pickup_time = models.TimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['group', 'pickup_point']
        ordering = ['pickup_point__pickup_group__priority', 'pickup_point__priority', 'pickup_point__name']

    def __str__(self):
        return f"{self.group.name} - {self.pickup_point.name} @ {self.pickup_time or 'Not Set'}"


class BookingPickupTimeNotification(models.Model):
    """Tracks the last pickup time we emailed to a booking for a group. Used to send only when time has changed."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='pickup_time_notifications')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='pickup_time_notifications')
    pickup_time_sent = models.TimeField(null=True, blank=True)
    sent_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['booking', 'group']
        ordering = ['-sent_at']

    def __str__(self):
        return f"Booking #{self.booking_id} @ {self.pickup_time_sent or 'N/A'} for {self.group.name}"


class EmailSettings(models.Model):
    email = models.EmailField(max_length=255)
    name_from = models.CharField(max_length=255, default='iTrip Knossos')
    password = models.CharField(max_length=255)
    host = models.CharField(max_length=255, default='smtp.gmail.com')
    port = models.IntegerField(default=587)
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email
    
    class Meta:
        verbose_name = 'Email Settings'
        verbose_name_plural = 'Email Settings'
        ordering = ['created_at']

