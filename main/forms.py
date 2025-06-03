from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
import datetime
from django.utils.html import format_html, mark_safe
from django.utils.dateparse import parse_time

from .models import (
    Category, Tag, Excursion, ExcursionImage, Feedback,
    ExcursionAvailability, UserProfile, Group,
    PaymentMethod, Booking, Transaction, DayOfWeek, PickupPoint, PickupGroup
)

User = get_user_model()

# ----- Excursion Forms -----
class ExcursionForm(forms.ModelForm):
    class Meta:
        model = Excursion
        fields = [
            'title', 'description', 'intro_image',
            'category', 'tags',
            'full_day', 'on_request', 'status', 'provider', 'guide'
        ]
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 4,
                'class': 'editor',
                'style': 'width: 100%;'
            }),
            'category': forms.CheckboxSelectMultiple,
            'tags': forms.CheckboxSelectMultiple,
            'full_day': forms.Select(choices=[(True, 'Yes'), (False, 'No')]),
            'on_request': forms.Select(choices=[(True, 'Yes'), (False, 'No')]),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set default provider to ID 10 (Knossos)
        if not self.instance.pk:  # Only set default for new excursions
            self.initial['provider'] = 10

# Inline formset to manage gallery images alongside ExcursionForm
ExcursionImageFormSet = inlineformset_factory(
    Excursion, ExcursionImage,
    fields=['image', 'alt_text'], extra=3, can_delete=True
)

# ----- Feedback Form -----
class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.NumberInput(attrs={'min': 1, 'max': 5}),
            'comment': forms.Textarea(attrs={'rows': 3}),
        }

# ----- Availability Form -----
class WeekdayCapacityWidget(forms.CheckboxSelectMultiple):
    def __init__(self, form_data=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.form_data = form_data

    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            value = []
        if not isinstance(value, (list, tuple)):
            value = [value]
        
        final_attrs = self.build_attrs(attrs)
        output = []
        
        # Get all weekdays
        weekdays = DayOfWeek.objects.all()
        
        # Start with a simple vertical stack
        output.append('<div class="space-y-2">')
        
        for weekday in weekdays:
            checkbox_name = name
            checkbox_id = f'id_{name}_{weekday.id}'
            capacity_name = f'{name}_capacity_{weekday.id}'
            capacity_id = f'id_{capacity_name}'
            
            is_checked = str(weekday.id) in [str(v) for v in value]
            if self.form_data and capacity_name in self.form_data:
                capacity_value = self.form_data.get(capacity_name)
            else:
                capacity_value = weekday.capacity if is_checked else 0
            
            # Each row: checkbox, label, capacity input
            weekday_html = f'''
                <div class="flex items-center gap-3">
                    <input type="checkbox" 
                        name="{checkbox_name}" 
                        id="{checkbox_id}" 
                        value="{weekday.id}" 
                        {"checked" if is_checked else ""} 
                        onchange="updateWeekdayCapacity(this, '{capacity_id}')" 
                        class="w-4 h-4">
                    <label for="{checkbox_id}" class="min-w-[120px] px-3 py-1 bg-gray-100 rounded text-center font-medium">{weekday.get_code_display()}</label>
                    <input type="number" 
                        name="{capacity_name}" 
                        id="{capacity_id}" 
                        value="{capacity_value}" 
                        min="0" 
                        class="w-16 px-2 py-1 border rounded text-center {"bg-gray-50" if not is_checked else ""}" 
                        {"disabled" if not is_checked else ""} 
                        data-weekday-id="{weekday.id}"
                        placeholder="0">
                </div>
            '''
            output.append(weekday_html)
        
        output.append('</div>')
        
        script = '''
            <script>
                function updateWeekdayCapacity(checkbox, capacityId) {
                    const capacityInput = document.getElementById(capacityId);
                    if (checkbox.checked) {
                        capacityInput.disabled = false;
                        capacityInput.classList.remove('bg-gray-50');
                    } else {
                        capacityInput.disabled = true;
                        capacityInput.value = "0";
                        capacityInput.classList.add('bg-gray-50');
                    }
                }
            </script>
        '''
        
        return mark_safe(f'{"".join(output)}{script}')

class PickupGroupWidget(forms.CheckboxSelectMultiple):
    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            value = []
        if not isinstance(value, (list, tuple)):
            value = [value]
        final_attrs = self.build_attrs(attrs)
        output = []
        pickup_groups = list(PickupGroup.objects.all().select_related('region'))
        groups_per_col = 7
        num_cols = (len(pickup_groups) + groups_per_col - 1) // groups_per_col
        output.append('<div class="pickupgroup-grid">')
        for col in range(num_cols):
            output.append('<div class="pickupgroup-col">')
            for i in range(groups_per_col):
                idx = col * groups_per_col + i
                if idx >= len(pickup_groups):
                    break
                group = pickup_groups[idx]
                checkbox_name = name
                checkbox_id = f'id_{name}_{group.id}'
                is_checked = str(group.id) in [str(v) for v in value]
                group_html = f'''
                    <div class="flex flex-col items-center mb-2" data-region-id="{group.region.id if group.region else ''}">
                        <div class="flex items-center gap-2 w-full">
                            <input type="checkbox" 
                                name="{checkbox_name}" 
                                id="{checkbox_id}" 
                                value="{group.id}" 
                                {'checked' if is_checked else ''} 
                                class="w-4 h-4">
                            <label for="{checkbox_id}" class="px-3 py-1 bg-gray-100 rounded text-center font-medium flex-1">
                                {group.name} 
                                <span class="text-xs text-gray-500 mt-1">{group.region.name if group.region else ''}</span>
                            </label>
                            
                        </div>
                        
                    </div>
                '''
                output.append(group_html)
            output.append('</div>')
        output.append('</div>')
        return mark_safe(''.join(output))

class ExcursionAvailabilityForm(forms.ModelForm):
    class Meta:
        model = ExcursionAvailability
        fields = [
            'excursion', 'start_date', 'end_date', 'start_time', 'end_time', 
            'max_guests', 'region', 'adult_price', 'child_price', 'infant_price', 
            'weekdays', 'discount', 'status', 'pickup_groups'
        ]
        widgets = {
            'excursion': forms.Select(attrs={'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'form-control',
                'inputmode': 'numeric',
                'pattern': '[0-9]{2}:[0-9]{2}'
            }),
            'end_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'form-control',
                'inputmode': 'numeric',
                'pattern': '[0-9]{2}:[0-9]{2}'
            }),
            'region': forms.Select(attrs={'class': 'form-control'}),
            'pickup_groups': PickupGroupWidget,
            'weekdays': WeekdayCapacityWidget,
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'adult_price': forms.NumberInput(attrs={'class': 'price-field'}),
            'child_price': forms.NumberInput(attrs={'class': 'price-field'}),
            'infant_price': forms.NumberInput(attrs={'class': 'price-field'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pass form data to the weekdays widget
        self.fields['weekdays'].widget = WeekdayCapacityWidget(
            form_data=self.data if self.is_bound else None
        )
        
    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            raise ValidationError({'end_date': 'End date cannot be before start date.'})
        
        # Handle weekday capacities
        weekdays = cleaned.get('weekdays', [])
        for weekday_id in weekdays:
            capacity_name = f'weekdays_capacity_{weekday_id}'
            capacity = self.data.get(capacity_name)
            if capacity:
                try:
                    capacity = int(capacity)
                    if capacity < 0:
                        raise ValidationError(f'Capacity for {DayOfWeek.objects.get(id=weekday_id).get_code_display()} cannot be negative')
                    # Update the DayOfWeek instance
                    DayOfWeek.objects.filter(id=weekday_id).update(capacity=capacity)
                except ValueError:
                    raise ValidationError(f'Invalid capacity value for {DayOfWeek.objects.get(id=weekday_id).get_code_display()}')
        
        return cleaned

# ----- Booking & Pricing Forms -----
class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = [
            'guest_name', 'guest_email',
            'total_price', 'partial_paid',
            'total_adults', 'total_kids', 'total_infants',
            'price'
        ]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Always remove group and payment_status
        self.fields.pop('group', None)
        self.fields.pop('payment_status', None)
        # partial_paid visible for representatives and admins only
        if not user or not (user.is_staff or getattr(user.profile, 'role', None) == 'representative'):
            self.fields.pop('partial_paid', None)

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['payment_method', 'amount']

# ----- User & Staff Forms -----
class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['name', 'email', 'phone',]

# ----- Lookup Forms -----
class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name']

class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ['name']

class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'guide']

class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ['name']
