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

    def __str__(self):
        return self.name
    
    def get_total_bookings(self):
        """Get total number of excursion bookings for this user"""
        if self.user:
            return self.user.bookings.count()
        return 0
    
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
        return self.role == 'client' and not self.email
   
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
    # priority = models.PositiveIntegerField(default=0)    

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
    guide = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, blank=True, null=True, related_name='excursions_guide', limit_choices_to={'role': 'guide'})

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
    # region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, related_name='availabilities')
    # pickup_group = models.ForeignKey(PickupGroup, on_delete=models.SET_NULL, null=True, related_name='availabilities')
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

    def update_status(self):
        if self.end_date < datetime.now().date():
            self.is_active = False
            self.save()

class AvailabilityDays(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    # excursion = models.ForeignKey(Excursion, on_delete=models.CASCADE, related_name='availability_days')
    excursion_availability = models.ForeignKey(ExcursionAvailability, on_delete=models.CASCADE, related_name='availability_days', null=True)
    date_day = models.DateField()
    capacity = models.PositiveIntegerField(default=0)
    booked_guests = models.PositiveIntegerField(default=0)

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
    

    def __str__(self):
        return f"Booking #{self.id} by {self.user.username if self.user else 'Guest'}"
    
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
 


