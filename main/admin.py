from django.contrib import admin
from django.contrib import messages
from .models import UserProfile, Excursion, ExcursionAvailability, Booking, Transaction, Feedback, Category, Tag, Group, GroupPickupPoint, PaymentMethod, Reservation, Bus, JCCGatewayConfig

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


@admin.register(JCCGatewayConfig)
class JCCGatewayConfigAdmin(admin.ModelAdmin):
    """
    Admin interface for JCC Gateway Configuration.
    """
    list_display = ('name', 'environment', 'is_active', 'default_currency', 'default_language', 'created_at')
    list_filter = ('environment', 'is_active', 'created_at')
    search_fields = ('name', 'username')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'environment', 'is_active')
        }),
        ('API Credentials', {
            'fields': ('username', 'password'),
            'description': 'Enter your JCC API credentials. Keep these secure!'
        }),
        ('API Endpoints', {
            'fields': ('register_url', 'status_url'),
            'description': 'JCC API endpoint URLs. For sandbox: https://gateway-test.jcc.com.cy/payment/rest/...'
        }),
        ('Default Settings', {
            'fields': ('default_currency', 'default_language'),
            'description': 'Default currency (ISO 4217 numeric: 978=EUR, 840=USD) and language code (en, el, etc.)'
        }),
    )
    
    def save_model(self, request, obj, form, change):
        """
        Override save to show warning if multiple active configs exist.
        """
        super().save_model(request, obj, form, change)
        
        if obj.is_active:
            active_count = JCCGatewayConfig.objects.filter(is_active=True).count()
            if active_count > 1:
                messages.warning(
                    request,
                    f'Warning: {active_count} active configurations found. '
                    'Only one should be active at a time. Others have been set to inactive.'
                )