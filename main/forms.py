from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
import datetime
from django.utils.html import format_html, mark_safe
from django.utils.dateparse import parse_time
from django.contrib.auth.forms import UserCreationForm

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
            # capacity_name = f'{name}_capacity_{weekday.id}'
            # capacity_id = f'id_{capacity_name}'
            
            is_checked = str(weekday.id) in [str(v) for v in value]
            # if self.form_data and capacity_name in self.form_data:
            #     capacity_value = self.form_data.get(capacity_name)
            # else:
            #     capacity_value = weekday.capacity if is_checked else 0
            
            # Each row: checkbox, label, capacity input
            weekday_html = f'''
                <div class="flex items-center gap-3">
                    <input type="checkbox" 
                        name="{checkbox_name}" 
                        id="{checkbox_id}" 
                        value="{weekday.id}" 
                        {"checked" if is_checked else ""} 
                        
                        class="w-4 h-4">
                    <label for="{checkbox_id}" class="min-w-[120px] px-3 py-1 bg-gray-100 rounded text-center font-medium">{weekday.get_code_display()}</label>
                    
                </div>
            '''
            output.append(weekday_html)
        
        output.append('</div>')
        
        script = '''
            <script>
                
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
        pickup_groups = list(PickupGroup.objects.all())
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
                    <div class="flex flex-col items-center mb-2">
                        <div class="flex items-center gap-2 w-full">
                            <input type="checkbox" 
                                name="{checkbox_name}" 
                                id="{checkbox_id}" 
                                value="{group.id}" 
                                {'checked' if is_checked else ''} 
                                class="w-4 h-4">
                            <label for="{checkbox_id}" class="px-3 py-1 bg-gray-100 rounded text-center font-medium flex-1">
                                {group.name} 
                            </label>
                            
                        </div>
                        
                    </div>
                '''
                output.append(group_html)
            output.append('</div>')
        output.append('</div>')
        return mark_safe(''.join(output))

class PickupPointWidget(forms.CheckboxSelectMultiple):
    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            value = []
        if not isinstance(value, (list, tuple)):
            value = [value]
        final_attrs = self.build_attrs(attrs)
        output = []
        pickup_points = list(PickupPoint.objects.all().select_related('pickup_group'))
        points_per_col = 7
        num_cols = (len(pickup_points) + points_per_col - 1) # points_per_col
        output.append('<div class="pickuppoint-grid">')
        for col in range(num_cols):
            output.append('<div class="pickuppoint-col">')
            for i in range(points_per_col):
                idx = col * points_per_col + i
                if idx >= len(pickup_points):
                    break
                point = pickup_points[idx]
                checkbox_name = name
                checkbox_id = f'id_{name}_{point.id}'
                is_checked = str(point.id) in [str(v) for v in value]
                point_html = f'''
                    <div class="flex flex-col items-center mb-2">
                        <div class="flex items-center gap-2 w-full">
                            <input type="checkbox" 
                                name="{checkbox_name}" 
                                id="{checkbox_id}" 
                                value="{point.id}" 
                                {'checked' if is_checked else ''} 
                                class="w-4 h-4">
                            <label for="{checkbox_id}" class="px-3 py-1 bg-gray-100 rounded text-center font-medium flex-1">
                                {point.name}
                            </label>
                        </div>
                    </div>
                '''
                output.append(point_html)
            output.append('</div>')
        output.append('</div>')
        return mark_safe(''.join(output))
class ExcursionAvailabilityForm(forms.ModelForm):
    class Meta:
        model = ExcursionAvailability
        fields = [
            'excursion', 'start_date', 'end_date', 'start_time', 'end_time', 
            'max_guests', 'adult_price', 'child_price', 'infant_price', 
            'weekdays', 'discount', 'status', 'pickup_groups', 'pickup_points'
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
            'pickup_groups': PickupGroupWidget,
            'pickup_points': PickupPointWidget,
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
            'price', 'user', 'voucher_id', 'date', 'pickup_point',
            'payment_status', 'partial_paid_method',
        ]
        widgets = {
            'pickup_point': forms.Select(attrs={'class': 'form-control'}),
            'partial_paid_method': forms.Select(choices=[('', 'Select a payment method')] + list(Booking.PAYMENT_METHOD_CHOICES)),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Always remove group and payment_status
        self.fields.pop('group', None)
        
        # Handle partial_paid_method field for clients (non-staff, non-representative)
        if not user or not (user.is_staff or getattr(user.profile, 'role', None) == 'representative'):
            if 'partial_paid_method' in self.fields:
                # Make the field optional for clients and use hidden widget
                self.fields['partial_paid_method'].required = False
                self.fields['partial_paid_method'].widget = forms.HiddenInput()
                self.fields['partial_paid_method'].initial = ''
            if 'partial_paid' in self.fields:
                self.fields['partial_paid'].required = False
                self.fields['partial_paid'].widget.attrs['disabled'] = True

    def clean(self):
        cleaned_data = super().clean()
        # Handle partial_paid_method field
        if 'partial_paid_method' in self.fields:
            # If the field is a hidden input (for clients), set it to empty string
            if isinstance(self.fields['partial_paid_method'].widget, forms.HiddenInput):
                cleaned_data['partial_paid_method'] = ''
            # If the field is in the form but not in cleaned_data, set it to empty string
            elif 'partial_paid_method' not in cleaned_data:
                cleaned_data['partial_paid_method'] = ''
            # If the field value is None, convert it to empty string
            elif cleaned_data.get('partial_paid_method') is None:
                cleaned_data['partial_paid_method'] = ''
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Handle partial_paid_method field if it's a hidden input
        if 'partial_paid_method' in self.fields and isinstance(self.fields['partial_paid_method'].widget, forms.HiddenInput):
            instance.partial_paid_method = ''
        if commit:
            instance.save()
        return instance

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['payment_method', 'amount']

# ----- User & Staff Forms -----
class SignupForm(UserCreationForm):
    name = forms.CharField(max_length=255, required=True)
    # email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=50, required=False)
    
    class Meta:
        model = User
        fields = ('name', 'username', 'phone', 'password1', 'password2')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set email as username field
        self.fields['username'] = forms.CharField(
            label='Email',
            max_length=254,
            widget=forms.EmailInput(attrs={'autofocus': True})
        )
        # Make email field hidden since we're using it as username
        # self.fields['email'].widget = forms.HiddenInput()
        # self.fields['email'].label = ''
    
    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('username')  # username is actually email
        if email:
            cleaned_data['email'] = email
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['username']  # This is the email
        user.email = self.cleaned_data['username']  # Set email to same as username
        if commit:
            user.save()
        return user

class UserProfileForm(forms.ModelForm):
    password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter new password'}),
        required=False,
        help_text='Leave blank if you don\'t want to change your password.'
    )
    password2 = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm new password'}),
        required=False,
        help_text='Enter the same password as before, for verification.'
    )
    
    class Meta:
        model = UserProfile
        fields = ['name', 'email', 'phone']
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError("The two password fields didn't match.")
            if len(password1) < 8:
                raise forms.ValidationError("Password must be at least 8 characters long.")
        
        return cleaned_data

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
