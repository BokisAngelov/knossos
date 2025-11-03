from django.contrib import admin
from .models import UserProfile, Excursion, ExcursionAvailability, Booking, Transaction, Feedback, Category, Tag, Group, GroupPickupPoint, PaymentMethod, Reservation, Bus

# Register your models here.
admin.site.register(UserProfile)
admin.site.register(Excursion)
admin.site.register(ExcursionAvailability)
admin.site.register(Booking)
admin.site.register(Transaction)
admin.site.register(Feedback)
admin.site.register(Category)
admin.site.register(Tag)
admin.site.register(Group)
admin.site.register(GroupPickupPoint)
admin.site.register(PaymentMethod)
admin.site.register(Reservation)
admin.site.register(Bus)