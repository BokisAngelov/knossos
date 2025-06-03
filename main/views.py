from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
import datetime
from django.contrib.auth.models import User
from django.http import JsonResponse, Http404
from django.utils.text import slugify
from .models import (
    Excursion, ExcursionImage, ExcursionAvailability,
    Booking, Feedback, UserProfile, Region, 
    Group, Category, Tag, PickupPoint, AvailabilityDays, DayOfWeek, Hotel, PickupGroup, PickupGroupAvailability
)
from .forms import (
    ExcursionForm, ExcursionImageFormSet,
    ExcursionAvailabilityForm, BookingForm, FeedbackForm, UserProfileForm,
    GroupForm
)
from django.core.validators import validate_email, RegexValidator
from django.core.exceptions import ValidationError
import re
import json
from django.db.models import Q
from django.apps import apps

def is_staff(user):
    return user.is_staff

def homepage(request):
    excursions = Excursion.objects.all().filter(status='active')
    return render(request, 'main/home.html', {
        'excursions': excursions,
    })

# ----- Excursion Views -----
def excursion_list(request):
    excursions = Excursion.objects.filter(availabilities__isnull=False).filter(status='active')
    return render(request, 'main/excursions/excursion_list.html', {
        'excursions': excursions,
    })

def excursion_detail(request, pk):

    excursion = get_object_or_404(Excursion, pk=pk)    
    feedback_form, booking_form = None, None
    excursion_availability = ExcursionAvailability.objects.filter(excursion=excursion)

    if not excursion_availability.exists():
        feedback_form = FeedbackForm()
        booking_form = BookingForm()

        return render(request, 'main/excursions/excursion_detail.html', {
            'excursion': excursion,
            'feedback_form': feedback_form,
            'booking_form': booking_form,
            'excursion_availability': excursion_availability,
        })

    # Handle feedback submission
    if request.method == 'POST' and 'feedback_submit' in request.POST:
        feedback_form = FeedbackForm(request.POST)
        if feedback_form.is_valid() and request.user.is_authenticated:
            feedback = feedback_form.save(commit=False)
            feedback.excursion = excursion
            feedback.author = request.user
            feedback.created_at = timezone.now()
            feedback.save()
            messages.success(request, 'Thank you for your feedback.')
            return redirect('excursion_detail', pk)
        
    # Handle booking submission
    elif request.method == 'POST' and 'booking_submit' in request.POST:
        booking_form = BookingForm(request.POST)

        if booking_form.is_valid():
            booking = booking_form.save(commit=False)
            excursion_availability = ExcursionAvailability.objects.get(excursion=excursion)
            booking.excursion_availability = excursion_availability
            booking.user = request.user
            booking.save()
            messages.success(request, 'Booking created successfully.')
            return redirect('excursion_detail', pk)
        

    return render(request, 'main/excursions/excursion_detail.html', {
        'excursion': excursion,
        'feedback_form': feedback_form,
        'excursion_availability': ExcursionAvailability.objects.get(excursion=excursion),
        'booking_form': booking_form,
    })

@user_passes_test(is_staff)
def excursion_create(request):
    if request.method == 'POST':
        form = ExcursionForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    excursion = form.save()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': 'Excursion created successfully.',
                        'redirect_url': reverse('excursion_detail', kwargs={'pk': excursion.pk})
                    })
                messages.success(request, 'Excursion created successfully.')
                return redirect('excursion_detail', excursion.pk)
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': str(e)
                    })
                messages.error(request, f'Error creating excursion: {str(e)}')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # Format form errors for display
                error_messages = []
                for field, errors in form.errors.items():
                    field_name = form.fields[field].label if field in form.fields else field
                    for error in errors:
                        error_messages.append(f"{field_name}: {error}")
                
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the following errors:',
                    'errors': error_messages
                })
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ExcursionForm()
    
    return render(request, 'main/excursions/excursion_form.html', {
        'form': form,
    })

@user_passes_test(is_staff)
def excursion_update(request, pk):
    excursion = get_object_or_404(Excursion, pk=pk)
    form = ExcursionForm(request.POST, request.FILES, instance=excursion)
    
    if request.method == 'POST':
        if form.is_valid():
            try:
                with transaction.atomic():
                    excursion = form.save()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': 'Excursion updated successfully.',
                        'redirect_url': reverse('excursion_detail', kwargs={'pk': pk})
                    })
                messages.success(request, 'Excursion updated successfully.')
                return redirect('excursion_detail', pk)
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': str(e)
                    })
                messages.error(request, f'Error updating excursion: {str(e)}')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the errors below.',
                    'errors': form.errors
                })
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ExcursionForm(instance=excursion)
    
    return render(request, 'main/excursions/excursion_form.html', {
        'form': form,
        'excursion': excursion,
    })

@user_passes_test(is_staff)
def excursion_delete(request, pk):

    # item_id = request.POST.get('item_id')
    excursion = get_object_or_404(Excursion, pk=pk)

    if request.method == 'POST':
        excursion.delete()
        messages.success(request, 'Excursion deleted.')
        return redirect('excursion_list')
    else:
        messages.error(request, 'Excursion not deleted.')
        return redirect('excursion_list')
    
# ----- Booking Views -----
def booking_create(request, availability_pk):
    availability = get_object_or_404(ExcursionAvailability, pk=availability_pk)
    if request.method == 'POST':
        form = BookingForm(request.POST, user=request.user if request.user.is_authenticated else None)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.user = request.user if request.user.is_authenticated else None
            booking.excursion_availability = availability
            # Role-based payment status
            if request.user.is_authenticated:
                role = getattr(request.user.profile, 'role', None)
                if request.user.is_staff:
                    booking.payment_status = 'completed'
                elif role == 'representative':
                    booking.payment_status = 'pending'
                else:
                    booking.payment_status = 'pending'
            else:
                booking.payment_status = 'pending'
            booking.save()
            messages.success(request, 'Booking created.')
            # Redirect logic: reps/admin skip checkout
            if request.user.is_authenticated and (request.user.is_staff or getattr(request.user.profile, 'role', None) == 'representative'):
                return redirect('booking_detail', booking.pk)
            # Guests/clients go to checkout
            return redirect('checkout', booking.pk)
    else:
        form = BookingForm(user=request.user if request.user.is_authenticated else None)
    return render(request, 'main/bookings/booking_form.html', {
        'form': form,
        'availability': availability,
    })

# Booking detail: only authenticated users (clients/reps/admins)
@login_required
def booking_detail(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    return render(request, 'main/bookings/booking_detail.html', {
        'booking': booking,
    })

# ----- Checkout View -----
# Guests and clients go through checkout; reps/admins redirected to detail
def checkout(request, booking_pk):
    booking = get_object_or_404(Booking, pk=booking_pk)
    # Redirect reps/admins immediately to detail
    if request.user.is_authenticated:
        role = getattr(request.user.profile, 'role', None)
        if request.user.is_staff or role == 'representative':
            return redirect('booking_detail', booking_pk)
    # Process payment (placeholder for Stripe integration)
    if request.method == 'POST':
        # TODO: integrate Stripe payment here
        booking.payment_status = 'completed'
        booking.save()
        messages.success(request, 'Payment successful.')
        return redirect('booking_detail', booking_pk)
    return render(request, 'main/bookings/checkout.html', {
        'booking': booking,
    })

# ----- Auth Views -----
def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Create associated profile with default client role
            UserProfile.objects.create(user=user, role='client')
            login(request, user)
            messages.success(request, 'Account created successfully. Please verify your email to continue.')
            return redirect('excursion_list')
    else:
        form = UserCreationForm()
    return render(request, 'main/accounts/signup.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('excursion_list')
    else:
        form = AuthenticationForm()
    return render(request, 'main/accounts/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('excursion_list')

@login_required
def profile(request, pk):
    user_profile = get_object_or_404(User, pk=pk)
    bookings = Booking.objects.filter(user=user_profile)
    
    # Only allow users to view their own profile unless they're staff
    if request.user.id != user_profile.id and not request.user.is_staff:
        messages.error(request, "You don't have permission to view this profile.")
        return redirect('profile', pk=request.user.profile.id)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=user_profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('profile', pk=pk)
    else:
        form = UserProfileForm(instance=user_profile)
    
    return render(request, 'main/accounts/profile.html', {
        'form': form,
        'bookings': bookings,
        'user_profile': user_profile,
    }
    )    

def profile_edit(request, pk):
    profile = get_object_or_404(UserProfile, pk=pk)
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('profile', pk=pk)
    else:
        form = UserProfileForm(instance=profile)
    return render(request, 'main/accounts/profile_edit.html', {
        'form': form,
    })

# @login_required
@user_passes_test(is_staff)
def admin_dashboard(request, pk):
    """Admin dashboard view with overview and quick access to all admin functions"""
    from django.db.models import Sum, Count
    
    # Get admin stats
    active_excursions_count = Excursion.objects.filter(status='active').count()
    total_excursions_count = Excursion.objects.all().count()
    reps_count = User.objects.filter(profile__role='representative').exclude(is_staff=True).count()
    clients_count = User.objects.filter(profile__role='client').exclude(is_staff=True).count()
    total_revenue = Booking.objects.filter(payment_status='completed').aggregate(
        total=Sum('total_price')
    )['total'] or 0
    
    # Recent bookings
    recent_bookings = Booking.objects.all().order_by('-created_at')[:5]
    
    context = {
        'active_excursions_count': active_excursions_count,
        'reps_count': reps_count,
        'clients_count': clients_count,
        'total_revenue': total_revenue,
        'recent_bookings': recent_bookings,
        'booking_count': Booking.objects.count(),
        'user': User.objects.get(profile__id=pk),
        'total_excursions_count': total_excursions_count,
    }
    
    return render(request, 'main/admin/dashboard.html', context)

# ----- Group Views -----
# Only admins can manage groups
@user_passes_test(is_staff)
def group_list(request):
    groups = Group.objects.all()

        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        groups = groups.filter(
            Q(name__icontains=search_query)
        )


    return render(request, 'main/groups/group_list.html', {
        'groups': groups,
    })

@user_passes_test(is_staff)
def group_create(request):
    if request.method == 'POST':
        form = GroupForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Group created successfully.')
            return redirect('group_list')
    else:
        form = GroupForm()
    return render(request, 'main/groups/group_form.html', {
        'form': form,
    })

@user_passes_test(is_staff)
def group_detail(request, pk):
    group = get_object_or_404(Group, pk=pk)
    return render(request, 'main/groups/group_detail.html', {
        'group': group,
    })

@user_passes_test(is_staff)
def group_update(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        form = GroupForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            messages.success(request, 'Group updated successfully.')
            return redirect('group_detail', pk) 
    else:
        form = GroupForm(instance=group)
    return render(request, 'main/groups/group_form.html', {
        'form': form,
        'group': group,
    })

@user_passes_test(is_staff)
def group_delete(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        group.delete()
        messages.success(request, 'Group deleted successfully.')
        return redirect('group_list')
    return render(request, 'main/groups/group_confirm_delete.html', {
        'group': group,
    })

# ----- Category and Tag Management -----
@user_passes_test(is_staff)
def manage_categories_tags(request):
    """Combined view for managing both categories and tags with inline editing"""
    categories = Category.objects.all()
    tags = Tag.objects.all()

    # print('request.POST', request)
    
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')
      
        if action_type == 'add_category':
            name = request.POST.get('name', '').strip()
            if name:
                Category.objects.create(name=name)
                messages.success(request, 'Category added successfully.')
                return redirect('manage_categories_tags')
                
        elif action_type == 'edit_category':
            category = get_object_or_404(Category, pk=item_id)
            name = request.POST.get('name', '').strip()
            if name:
                category.name = name
                category.save()
                messages.success(request, 'Category updated successfully.')
                return redirect('manage_categories_tags')
                
        elif action_type == 'delete_category':
            category = get_object_or_404(Category, pk=item_id)
            category.delete()
            messages.success(request, 'Category deleted successfully.')
            return redirect('manage_categories_tags')
            
        elif action_type == 'add_tag':
            name = request.POST.get('name', '').strip()
            if name:
                Tag.objects.create(name=name)
                messages.success(request, 'Tag added successfully.')
                return redirect('manage_categories_tags')
                
        elif action_type == 'edit_tag':
            tag = get_object_or_404(Tag, pk=item_id)
            name = request.POST.get('name', '').strip()
            if name:
                tag.name = name
                tag.save()
                messages.success(request, 'Tag updated successfully.')
                return redirect('manage_categories_tags')
                
        elif action_type == 'delete_tag':
            tag = get_object_or_404(Tag, pk=item_id)
            tag.delete()
            messages.success(request, 'Tag deleted successfully.')
            return redirect('manage_categories_tags')
    
    return render(request, 'main/admin/categories_tags_management.html', {
        'categories': categories,
        'tags': tags,
    })

# ----- Providers and Representatives Views -----
@user_passes_test(is_staff)
def providers_list(request):
    providers = UserProfile.objects.filter(role='provider')

    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        providers = providers.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
        
    return render(request, 'main/admin/providers.html', {
        'providers': providers,
    })

@user_passes_test(is_staff)
def manage_providers(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')
        
        if action_type == 'add_provider':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            vat = request.POST.get('vat', '').strip()
            
            if name and email:
                # Create User first
                user = User.objects.create_user(
                    username=email,
                    email=email,
                )
                # Create UserProfile
                UserProfile.objects.create(
                    user=user,
                    name=name,
                    email=email,
                    phone=phone,
                    vat=vat,
                    role='provider'
                )
                messages.success(request, 'Provider created successfully.')
                return redirect('manage_providers')

        elif action_type == 'edit_provider':
            provider = get_object_or_404(UserProfile, pk=item_id)
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            vat = request.POST.get('vat', '').strip()

            if name:
                provider.name = name
                provider.email = email
                provider.phone = phone
                provider.vat = vat
                provider.save()
                messages.success(request, 'Provider updated successfully.')

        elif action_type == 'delete_provider':
            provider = get_object_or_404(UserProfile, pk=item_id)
            # Delete the associated user as well
            provider.user.delete()
            messages.success(request, 'Provider deleted successfully.')
            return redirect('manage_providers')

    return render(request, 'main/admin/providers.html', {
        'providers': UserProfile.objects.filter(role='provider'),
    })

@user_passes_test(is_staff)
def reps_list(request):
    reps = UserProfile.objects.filter(role='representative')
        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        reps = reps.filter(
            Q(name__icontains=search_query)
        )

    return render(request, 'main/admin/reps.html', {
        'reps': reps,
    })

@user_passes_test(is_staff)
def manage_reps(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')
        
        if action_type == 'add_rep':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            
            if name and email:
                # Create User first
                user = User.objects.create_user(
                    username=email,
                    email=email,
                )
                rep = UserProfile.objects.create(
                    user=user,
                    name=name,
                    email=email,
                    phone=phone,
                    role='representative'
                )
                messages.success(request, 'Representative created successfully.')
                return redirect('manage_reps')
            
        elif action_type == 'edit_rep':
            rep = get_object_or_404(UserProfile, pk=item_id)
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            
            if name:
                rep.name = name
                rep.email = email
                rep.phone = phone
                rep.save()
                messages.success(request, 'Representative updated successfully.')

        elif action_type == 'delete_rep':
            rep = get_object_or_404(User, pk=item_id)    

            messages.success(request, 'Representative deleted successfully.')
            return redirect('manage_reps')

    return render(request, 'main/admin/reps.html', {
        'reps': UserProfile.objects.filter(role='representative'),
    })

@user_passes_test(is_staff)
def clients_list(request):
    clients = UserProfile.objects.filter(role='client')
        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        clients = clients.filter(
            Q(name__icontains=search_query)
        )

    return render(request, 'main/admin/clients.html', {
        'clients': clients,
    })

@user_passes_test(is_staff)
def manage_clients(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')
        
        if action_type == 'add_client':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            
            if name and email:
                # Create User first
                user = User.objects.create_user(
                    username=email,
                    email=email,
                )
                # Create UserProfile
                UserProfile.objects.create(
                    user=user,
                    name=name,
                    email=email,
                    phone=phone,
                    role='client'
                )
                messages.success(request, 'Client created successfully.')
                return redirect('manage_clients')
            
        elif action_type == 'edit_client':
            client = get_object_or_404(UserProfile, pk=item_id)
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()   
            
            if name:
                client.name = name
                client.email = email
                client.phone = phone
                client.save()
                messages.success(request, 'Client updated successfully.')
    
        elif action_type == 'delete_client':
            client = get_object_or_404(UserProfile, pk=item_id)
            client.delete()
            messages.success(request, 'Client deleted successfully.')
            return redirect('manage_clients')

    return render(request, 'main/admin/clients.html', {
        'clients': UserProfile.objects.filter(role='client'),
    })
    
@user_passes_test(is_staff)
def guides_list(request):
    guides = UserProfile.objects.filter(role='guide')

        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        guides = guides.filter(
            Q(name__icontains=search_query)
        )

    return render(request, 'main/admin/guides.html', {
        'guides': guides,
    })

@user_passes_test(is_staff)
def manage_guides(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')
        
        if action_type == 'add_guide':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            
            if name and email:
                # Create User first
                user = User.objects.create_user(
                    username=email,
                    email=email,
                )
                # Create UserProfile    
                UserProfile.objects.create(
                    user=user,
                    name=name,
                    email=email,
                    phone=phone,
                    role='guide'
                )
                messages.success(request, 'Guide created successfully.')
                return redirect('guides_list')
            
        elif action_type == 'edit_guide':
            guide = get_object_or_404(UserProfile, pk=item_id)
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()

            if name:
                guide.name = name
                guide.email = email
                guide.phone = phone
                guide.save()
                messages.success(request, 'Guide updated successfully.')

        elif action_type == 'delete_guide':
            guide = get_object_or_404(UserProfile, pk=item_id)
            guide.delete()
            messages.success(request, 'Guide deleted successfully.')
            return redirect('guides_list')

    return render(request, 'main/admin/guides.html', {
        'guides': UserProfile.objects.filter(role='guide'),
    })

# ----- Availability Views -----
@user_passes_test(is_staff)
def availability_list(request):
    availabilities = ExcursionAvailability.objects.all().order_by('status', 'excursion__title')
    excursions = Excursion.objects.all().order_by('title')

        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        availabilities = availabilities.filter(
            Q(excursion__title__icontains=search_query)
        )

    return render(request, 'main/availabilities/availabilities_list.html', {
        'availabilities': availabilities,
        'excursions': excursions,
    })

@user_passes_test(is_staff)
def availability_form(request, pk=None):
    """
    Unified view for creating and updating availability.
    If pk is provided, it's an update operation. Otherwise, it's a create operation.
    """
    availability = None
    if pk:
        availability = get_object_or_404(ExcursionAvailability, pk=pk)
    
    if request.method == 'POST':
        form = ExcursionAvailabilityForm(request.POST, instance=availability)
        
        excursion = request.POST.get('excursion')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        region = request.POST.get('region')

        
        
        overlapping_query = ExcursionAvailability.objects.filter(
            excursion=excursion,
            start_date__lte=end_date,
            end_date__gte=start_date,
            region=region,
            status='active'
        ).values('region')

        if pk:
            overlapping_query = overlapping_query.exclude(pk=pk)
        
        if overlapping_query.exists():
            error_message = 'Availability already exists for this excursion during the selected dates.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': [error_message]
                })
            form.add_error(None, error_message)
        elif form.is_valid():
            try:
                # First validate weekday capacities from form data
                max_guests = int(request.POST.get('max_guests', 0))
                selected_weekday_ids = request.POST.getlist('weekdays')
                pickup_group_ids = request.POST.getlist('pickup_groups')

                # Validate capacities before saving
                for weekday_id in selected_weekday_ids:
                    capacity_name = f'weekdays_capacity_{weekday_id}'
                    capacity = request.POST.get(capacity_name)
                    if capacity:
                        try:
                            capacity = int(capacity)
                            if capacity > max_guests:
                                raise ValueError(f"Capacity for {DayOfWeek.objects.get(id=weekday_id).get_code_display()} cannot be greater than the maximum number of guests.")
                        except ValueError as e:
                            if str(e).startswith("Capacity for"):
                                raise e
                            raise ValueError(f"Invalid capacity value for {DayOfWeek.objects.get(id=weekday_id).get_code_display()}")

                # Now save the availability
                availability = form.save(commit=False)
                excursion_pk = request.POST.get('excursion')

                if not excursion_pk:
                    raise ValueError("Excursion ID is required")
                    
                excursion = get_object_or_404(Excursion, pk=excursion_pk)
                availability.excursion = excursion
                
                # Save the availability to get an ID
                availability.save()
                
                # Manually set the weekdays and pickup groups relationships
                availability.weekdays.set(selected_weekday_ids)
                availability.pickup_groups.set(pickup_group_ids)
                
                # Update weekday capacities
                for weekday_id in selected_weekday_ids:
                    capacity_name = f'weekdays_capacity_{weekday_id}'
                    capacity = request.POST.get(capacity_name)
                    if capacity:
                        try:
                            capacity = int(capacity)
                            if capacity == 0:
                                capacity = max_guests
                            DayOfWeek.objects.filter(id=weekday_id).update(capacity=capacity)
                        except ValueError:
                            pass  # We already validated above
                
                # Set excursion status to active
                if excursion.status != 'active':
                    excursion.status = 'active'
                    excursion.save()

                # Delete existing AvailabilityDays entries (for both create and update)
                AvailabilityDays.objects.filter(excursion_availability=availability).delete()

                # Delete existing PickupGroupAvailability entries (for both create and update)
                PickupGroupAvailability.objects.filter(excursion_availability=availability).delete()
                
                # Get the selected weekdays after saving
                selected_weekdays = availability.weekdays.all()
                
                # Convert selected weekdays to Python's weekday numbers (0=Monday, 6=Sunday)
                weekday_numbers = []
                weekday_mapping = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}
                
                for weekday in selected_weekdays:
                    if weekday.code in weekday_mapping:
                        weekday_numbers.append(weekday_mapping[weekday.code])
                
                # Create an entry for each day in the range that matches selected weekdays
                current_date = availability.start_date
                while current_date <= availability.end_date:
                    if current_date.weekday() in weekday_numbers:
                        AvailabilityDays.objects.create(
                            excursion_availability=availability,
                            date_day=current_date
                        )
                    current_date += datetime.timedelta(days=1)

                # Create entries for each pickup group
                region_id = availability.region_id
                for pickup_group in PickupGroup.objects.filter(region_id=region_id, id__in=pickup_group_ids):
                    PickupGroupAvailability.objects.create(
                        excursion_availability=availability,
                        pickup_group=pickup_group
                    )

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': f'Availability {"updated" if pk else "created"} successfully.',
                        'redirect_url': reverse('availability_detail', kwargs={'pk': availability.pk})
                    })
                
                messages.success(request, f'Availability {"updated" if pk else "created"} successfully.')
                return redirect('availability_detail', pk=availability.pk)

            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': str(e)
                    })
                messages.error(request, f'Error {"updating" if pk else "creating"} availability: {str(e)}')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # Format form errors for display
                error_messages = []
                for field, errors in form.errors.items():
                    field_name = form.fields[field].label if field in form.fields else field
                    for error in errors:
                        error_messages.append(f"{field_name}: {error}")
                
                return JsonResponse({
                    'success': False,
                    'message': 'Please correct the following errors:',
                    'errors': error_messages
                })
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ExcursionAvailabilityForm(instance=availability)
    
    return render(request, 'main/availabilities/availability_form.html', {
        'form': form,
        'availability': availability,
        'is_update': bool(pk),
    })

@user_passes_test(is_staff)
def availability_detail(request, pk):
    availability = get_object_or_404(ExcursionAvailability, pk=pk)
    return render(request, 'main/availabilities/availability_detail.html', {
        'availability': availability,
    })

@user_passes_test(is_staff)
def availability_delete(request, pk):
    availability = get_object_or_404(ExcursionAvailability, pk=pk)
    if request.method == 'POST':
        excursion = availability.excursion

        # Delete all AvailabilityDays entries for this availability
        # AvailabilityDays.objects.filter(excursion=excursion).delete()
        availability.delete()
        
        # Check if there are any remaining availabilities for this excursion
        remaining_availabilities = ExcursionAvailability.objects.filter(excursion=excursion).exists()
        if not remaining_availabilities:
            excursion.status = 'inactive'
            excursion.save()
            
        messages.success(request, 'Availability deleted successfully.')
        return redirect('availability_list')
    else:
        return redirect('availability_list')
    
@user_passes_test(is_staff)
def pickup_points_list(request):
    pickup_points = PickupPoint.objects.all().select_related('pickup_group')
    pickup_groups = PickupGroup.objects.all()
    
    # Convert pickup groups to JSON-serializable format
    pickup_groups_json = json.dumps([{'id': group.id, 'name': group.name} for group in pickup_groups])
    
    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        pickup_points = pickup_points.filter(
            Q(name__icontains=search_query) |
            Q(address__icontains=search_query) |
            Q(pickup_group__name__icontains=search_query)
        )
    
    context = {
        'pickup_points': pickup_points,
        'pickup_groups': pickup_groups,
        'pickup_groups_json': pickup_groups_json,
    }
    return render(request, 'main/admin/pickup_points_list.html', context)

@user_passes_test(is_staff)
def manage_pickup_points(request):
    if request.method != 'POST':
        return redirect('pickup_points_list')
    
    action_type = request.POST.get('action_type')
    
    try:
        if action_type == 'add_point':
            name = request.POST.get('name', '').strip()
            address = request.POST.get('address', '').strip()
            type = request.POST.get('type', '').strip()
            pickup_group_id = request.POST.get('pickup_group')
            google_maps_link = request.POST.get('google_maps_link', '').strip()
            
            if not all([name, address, type, pickup_group_id]):
                messages.error(request, 'Please fill in all required fields')
                return redirect('pickup_points_list')
            
            try:
                pickup_group = PickupGroup.objects.get(id=pickup_group_id)
            except PickupGroup.DoesNotExist:
                messages.error(request, 'Invalid pickup group selected')
                return redirect('pickup_points_list')
            
            PickupPoint.objects.create(
                name=name,
                address=address,
                type=type,
                pickup_group=pickup_group,
                google_maps_link=google_maps_link if google_maps_link else None
            )
            messages.success(request, 'Pickup point added successfully')
            
        elif action_type == 'edit_point':
            item_id = request.POST.get('item_id')
            name = request.POST.get('name', '').strip()
            address = request.POST.get('address', '').strip()
            type = request.POST.get('type', '').strip()
            pickup_group_id = request.POST.get('pickup_group')
            google_maps_link = request.POST.get('google_maps_link', '').strip()
            
            if not all([item_id, name, address, type, pickup_group_id]):
                messages.error(request, 'Please fill in all required fields')
                return redirect('pickup_points_list')
            
            try:
                point = PickupPoint.objects.get(id=item_id)
                pickup_group = PickupGroup.objects.get(id=pickup_group_id)
            except (PickupPoint.DoesNotExist, PickupGroup.DoesNotExist):
                messages.error(request, 'Invalid pickup point or group selected')
                return redirect('pickup_points_list')
            
            point.name = name
            point.address = address
            point.type = type
            point.pickup_group = pickup_group
            point.google_maps_link = google_maps_link if google_maps_link else None
            point.save()
            messages.success(request, 'Pickup point updated successfully')
            
        elif action_type == 'delete_point':
            item_id = request.POST.get('item_id')
            if not item_id:
                messages.error(request, 'Invalid pickup point selected')
                return redirect('pickup_points_list')
            
            try:
                point = PickupPoint.objects.get(id=item_id)
                point.delete()
                messages.success(request, 'Pickup point deleted successfully')
            except PickupPoint.DoesNotExist:
                messages.error(request, 'Pickup point not found')
                return redirect('pickup_points_list')
            
        else:
            messages.error(request, 'Invalid action type')
            
    except Exception as e:
        messages.error(request, f'Error managing pickup point: {str(e)}')
    
    return redirect('pickup_points_list')

@user_passes_test(is_staff)
def staff_list(request):
    staff = UserProfile.objects.filter(role='admin') 
        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        staff = staff.filter(
            Q(name__icontains=search_query)
        )

    return render(request, 'main/admin/staff.html', {
        'staffs': staff,
    })

@user_passes_test(is_staff) 
def manage_staff(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')

        if action_type == 'add_staff':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            password = request.POST.get('password', '').strip()

            if name and email:
                username = email.split('@')[0] 
                base_username = username
                counter = 1

                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                # Create User first
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    is_staff=True,
                )   
                # Create UserProfile
                UserProfile.objects.create(
                    user=user,
                    name=name,
                    email=email,
                    phone=phone,
                    role='admin',
                )   
                messages.success(request, 'Staff member created successfully.')
                return redirect('staff_list')
            
        elif action_type == 'edit_staff':
            staff = get_object_or_404(UserProfile, pk=item_id)
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            role = request.POST.get('role', '').strip()
            # password = request.POST.get('password', '').strip()

            if name:
                staff.name = name
                staff.email = email
                staff.phone = phone
                staff.role = role
                staff.save()
                messages.success(request, 'Staff member updated successfully.')
                return redirect('staff_list')

        elif action_type == 'delete_staff':
            staff = get_object_or_404(User, pk=item_id)
            staff.delete()
            messages.success(request, 'Staff member deleted successfully.')
            return redirect('staff_list')
        

    return render(request, 'main/admin/staff.html', {
        'staffs': User.objects.filter(is_staff=True),
    })

@user_passes_test(is_staff)
def admin_excursions(request):
    excursions = Excursion.objects.all().order_by('status', 'title')

        # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        excursions = excursions.filter(
            Q(title__icontains=search_query)
        )


    return render(request, 'main/admin/admin_excursions.html', {
        'excursions': excursions,
    })

@user_passes_test(is_staff)
def hotel_list(request):
    hotels = Hotel.objects.all()
    pickup_groups = PickupGroup.objects.all()
    pickup_groups_json = json.dumps([{'id': pickup_group.id, 'name': pickup_group.name} for pickup_group in pickup_groups])

    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        hotels = hotels.filter(
            Q(name__icontains=search_query) |
            Q(address__icontains=search_query) 
        )

    return render(request, 'main/admin/hotel_list.html', {
        'hotels': hotels,
        'pickup_groups': pickup_groups,
        'pickup_groups_json': pickup_groups_json,
    })

@user_passes_test(is_staff)
def manage_hotels(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')

        try:
            if action_type == 'add_hotel':
                name = request.POST.get('name', '').strip()
                address = request.POST.get('address', '').strip()
                phone = request.POST.get('phone', '').strip()
                email = request.POST.get('email', '').strip()
                pickup_group_id = request.POST.get('pickup_group', '').strip()

                # Validate phone number
                phone_regex = re.compile(r'^[+]?[0-9\s\-()]{8,20}$')
                if not phone_regex.match(phone):
                    messages.error(request, 'Please enter a valid phone number (8-20 digits, may include +, spaces, hyphens, and parentheses)')
                    return redirect('hotel_list')

                # Validate email
                try:
                    validate_email(email)
                except ValidationError:
                    messages.error(request, 'Please enter a valid email address')
                    return redirect('hotel_list')

                if name and address and pickup_group_id:
                    try:
                        pickup_group = get_object_or_404(PickupGroup, id=pickup_group_id)
                        Hotel.objects.create(
                            name=name,
                            address=address,
                            phone_number=phone,
                            email=email,
                            pickup_group=pickup_group,
                        )
                        messages.success(request, 'Hotel created successfully.')
                        return redirect('hotel_list')
                    except Exception as e:
                        messages.error(request, f'Error creating hotel: {str(e)}')
                        return redirect('hotel_list')
            
            elif action_type == 'edit_hotel':
                hotel = get_object_or_404(Hotel, pk=item_id)
                name = request.POST.get('name', '').strip()
                address = request.POST.get('address', '').strip()
                phone = request.POST.get('phone', '').strip()
                email = request.POST.get('email', '').strip()
                pickup_group_id = request.POST.get('pickup_group', '').strip()

                # Validate phone number
                phone_regex = re.compile(r'^[+]?[0-9\s\-()]{8,20}$')
                if not phone_regex.match(phone):
                    messages.error(request, 'Please enter a valid phone number (8-20 digits, may include +, spaces, hyphens, and parentheses)')
                    return redirect('hotel_list')

                # Validate email
                try:
                    validate_email(email)
                except ValidationError:
                    messages.error(request, 'Please enter a valid email address')
                    return redirect('hotel_list')

                if name:    
                    hotel.name = name
                    hotel.address = address
                    hotel.phone_number = phone
                    hotel.email = email
                    if pickup_group_id:
                        pickup_group = get_object_or_404(PickupGroup, id=pickup_group_id)
                        hotel.pickup_group = pickup_group
                    hotel.save()
                    messages.success(request, 'Hotel updated successfully.')
                    return redirect('hotel_list')
                
            elif action_type == 'delete_hotel':
                hotel = get_object_or_404(Hotel, pk=item_id)
                hotel.delete()
                messages.success(request, 'Hotel deleted successfully.')
                return redirect('hotel_list')
            
        except Exception as e:
            messages.error(request, f'Error {"updating" if item_id else "creating"} hotel: {str(e)}')
            return redirect('hotel_list')
        
    return render(request, 'main/admin/hotel_list.html', {
        'hotels': Hotel.objects.all(),
    })

def region_list(request):
    regions = Region.objects.all()
    return render(request, 'main/admin/region_list.html', {
        'regions': regions,
    })

@user_passes_test(is_staff)
def manage_regions(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')

        print(action_type, item_id)

        if action_type == 'add_region':
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip()

            if name and code:
                Region.objects.create(name=name, slug=code)
                messages.success(request, 'Region created successfully.')
                return redirect('region_list')
            
        elif action_type == 'edit_region':
            region = get_object_or_404(Region, pk=item_id)
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip()

            if name and code:
                region.name = name
                region.slug = code
                region.save()
                messages.success(request, 'Region updated successfully.')
                return redirect('region_list')
            
        elif action_type == 'delete_region':
            region = get_object_or_404(Region, pk=item_id)
            region.delete()
            messages.success(request, 'Region deleted successfully.')
            return redirect('region_list')
        
    return render(request, 'main/admin/region_list.html', {
        'regions': Region.objects.all(),
    })
                     
@user_passes_test(is_staff)
def pickup_groups_list(request):
    pickup_groups = PickupGroup.objects.all()
    regions = Region.objects.all()
    # Convert regions to JSON-serializable format
    regions_json = json.dumps([{'id': region.id, 'name': region.name} for region in regions])

    # Handle search
    search_query = request.GET.get('search', '').strip()
    if search_query:
        pickup_groups = pickup_groups.filter(
            Q(name__icontains=search_query) |
            Q(region__name__icontains=search_query)
        )


    return render(request, 'main/admin/pickup_groups_list.html', {
        'pickup_groups': pickup_groups,
        'regions': regions,
        'regions_json': regions_json,
    })

@user_passes_test(is_staff)
def manage_pickup_groups(request):
    if request.method == 'POST':
        action_type = request.POST.get('action_type')
        item_id = request.POST.get('item_id')

        try:
            if action_type == 'add_group':
                name = request.POST.get('name', '').strip()
                region_id = request.POST.get('region', '').strip()

                if name and region_id:
                    try:
                        region = get_object_or_404(Region, id=region_id)
                        PickupGroup.objects.create(
                            name=name,
                            region=region,
                        )
                        messages.success(request, 'Pickup group created successfully.')
                        return redirect('pickup_groups_list')
                    except Exception as e:
                        messages.error(request, f'Error creating pickup group: {str(e)}')
                        return redirect('pickup_groups_list')
            
            elif action_type == 'edit_group':
                group = get_object_or_404(PickupGroup, pk=item_id)
                name = request.POST.get('name', '').strip()
                region_id = request.POST.get('region', '').strip()

                if name:    
                    group.name = name
                    if region_id:
                        region = get_object_or_404(Region, id=region_id)
                        group.region = region
                    group.save()
                    messages.success(request, 'Pickup group updated successfully.')
                    return redirect('pickup_groups_list')
                
            elif action_type == 'delete_group':
                group = get_object_or_404(PickupGroup, pk=item_id)
                group.delete()
                messages.success(request, 'Pickup group deleted successfully.')
                return redirect('pickup_groups_list')
            
        except Exception as e:
            messages.error(request, f'Error {"updating" if item_id else "creating"} pickup group: {str(e)}')
            return redirect('pickup_groups_list')
        
    return render(request, 'main/admin/pickup_groups_list.html', {
        'pickup_groups': PickupGroup.objects.all(),
    })
