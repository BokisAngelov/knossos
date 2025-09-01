# Knossos Django Models Reference

This document provides a comprehensive overview of all Django models in the Knossos project, their relationships, and key functionality.

## Core Models Overview

### User Management
- **UserProfile**: Extended user profiles with roles and contact information
- **Group**: Guide-managed groups for excursions

### Location & Logistics
- **Region**: Geographic regions (currently commented out in relationships)
- **PickupGroup**: Groups of pickup locations
- **PickupPoint**: Specific pickup locations within groups
- **Hotel**: Hotel information with pickup group associations

### Excursion Management
- **Category**: Excursion categories
- **Tag**: Excursion tags for filtering/searching
- **Excursion**: Main excursion entity
- **ExcursionImage**: Multiple images per excursion
- **ExcursionAvailability**: Date ranges and pricing for excursions
- **AvailabilityDays**: Specific day capacity tracking
- **DayOfWeek**: Weekday definitions for availability
- **Feedback**: Customer reviews and ratings

### Booking System
- **Reservation**: Hotel reservations (voucher-based)
- **Booking**: Excursion bookings linked to reservations
- **Transaction**: Payment transactions
- **PaymentMethod**: Available payment methods

---

## Detailed Model Specifications

### UserProfile
```python
Fields:
- user: OneToOneField to AUTH_USER_MODEL
- created_at: DateTimeField (auto)
- name: CharField(255, nullable)
- email: EmailField(nullable)
- phone: CharField(50, nullable)
- role: CharField(15) - provider|representative|client|guide|admin
- status: CharField(8) - active|inactive (default: active)
- address: CharField(255, nullable)
- zipcode: CharField(255, nullable)
- pickup_group: ForeignKey to PickupGroup (nullable)
- password_reset_token: CharField(255, nullable)

Relationships:
- groups (reverse): Groups where user is guide
- excursions_provider (reverse): Excursions where user is provider
- excursions_guide (reverse): Excursions where user is guide
- user_profiles (reverse from PickupGroup)
```

### Excursion
```python
Fields:
- title: CharField(255)
- description: TextField(nullable)
- intro_image: ImageField (custom upload path)
- category: ManyToManyField to Category
- tags: ManyToManyField to Tag
- feedbacks: ManyToManyField to Feedback
- overall_rating: DecimalField(3,2, nullable)
- status: CharField(8) - active|inactive (default: inactive)
- full_day: BooleanField(default: False)
- on_request: BooleanField(default: False)
- provider: ForeignKey to UserProfile (role: provider)
- guide: ForeignKey to UserProfile (role: guide)

Relationships:
- images (reverse): ExcursionImage instances
- availabilities (reverse): ExcursionAvailability instances
- feedback_entries (reverse): Feedback instances
- availability_days (reverse): AvailabilityDays instances
```

### ExcursionAvailability
```python
Fields:
- excursion: ForeignKey to Excursion
- created_at: DateTimeField (auto)
- start_date: DateField
- end_date: DateField
- max_guests: PositiveIntegerField
- booked_guests: PositiveIntegerField(default: 0)
- is_active: BooleanField(default: True)
- weekdays: ManyToManyField to DayOfWeek
- pickup_groups: ManyToManyField to PickupGroup
- pickup_points: ManyToManyField to PickupPoint
- start_time: TimeField(nullable)
- end_time: TimeField(nullable)
- discount: DecimalField(10,2, default: 0)
- adult_price: DecimalField(10,2, nullable)
- child_price: DecimalField(10,2, nullable)
- infant_price: DecimalField(10,2, nullable)
- status: CharField(8) - active|inactive (default: active)

Methods:
- update_status(): Deactivates if end_date is past

Relationships:
- availability_days (reverse): AvailabilityDays instances
- pickup_group_availabilities (reverse): PickupGroupAvailability instances
- bookings (reverse): Booking instances
```

### Booking
```python
Fields:
- user: ForeignKey to AUTH_USER_MODEL (nullable)
- voucher_id: ForeignKey to Reservation (nullable)
- excursion_availability: ForeignKey to ExcursionAvailability (nullable)
- date: DateField(nullable)
- pickup_point: ForeignKey to PickupPoint (nullable)
- guest_name: CharField(255, nullable)
- guest_email: EmailField(nullable)
- total_price: DecimalField(10,2, nullable)
- partial_paid: DecimalField(10,2, nullable)
- partial_paid_method: CharField - cash|card (nullable)
- total_adults: PositiveIntegerField(nullable)
- total_kids: PositiveIntegerField(nullable)
- total_infants: PositiveIntegerField(nullable)
- payment_status: CharField(10) - pending|completed|cancelled (default: pending)
- price: DecimalField(10,2, nullable) [Note: Duplicate of total_price?]
- created_at: DateTimeField (auto)
- deleteByUser: BooleanField(default: False)

Relationships:
- transactions (reverse): Transaction instances
```

### Reservation
```python
Fields:
- voucher_id: CharField(255, unique)
- hotel: ForeignKey to Hotel (nullable)
- client_name: CharField(255)
- client_email: EmailField(nullable)
- client_phone: CharField(255, nullable)
- total_adults: PositiveIntegerField(nullable)
- total_kids: PositiveIntegerField(nullable)
- check_in: DateField
- check_out: DateField
- flight_number: CharField(255)
- pickup_group: ForeignKey to PickupGroup (nullable)
- pickup_point: ForeignKey to PickupPoint (nullable)
- departure_time: TimeField(nullable)
- status: CharField(255) - active|inactive (default: active)

Methods:
- update_status(): Deactivates if check_out is past

Relationships:
- bookings (reverse): Booking instances
```

### PickupGroup
```python
Fields:
- name: CharField(255)
- code: CharField(255, unique, nullable)

Relationships:
- pickup_points (reverse): PickupPoint instances
- user_profiles (reverse): UserProfile instances
- hotels (reverse): Hotel instances
- reservations (reverse): Reservation instances
- availabilities (reverse from ExcursionAvailability)
- pickup_group_availabilities (reverse): PickupGroupAvailability instances
```

### PickupPoint
```python
Fields:
- name: CharField(255)
- address: CharField(255, nullable)
- pickup_group: ForeignKey to PickupGroup (nullable)
- google_maps_link: CharField(255, nullable)

Meta:
- ordering: ['name']

Relationships:
- reservations (reverse): Reservation instances
- bookings (reverse): Booking instances
- availabilities (reverse from ExcursionAvailability)
```

---

## Key Relationships & Business Logic

### Booking Flow
1. **Reservation** created with voucher_id (hotel booking)
2. **Booking** links reservation to excursion availability
3. **Transaction** records payment details
4. **AvailabilityDays** tracks daily capacity vs bookings

### User Roles
- **Provider**: Owns excursions
- **Guide**: Leads excursions and groups
- **Representative**: Hotel/agency representative
- **Client**: End customer
- **Admin**: System administrator

### Pricing Structure
- Adult/Child/Infant pricing in ExcursionAvailability
- Discount field for promotional pricing
- Partial payment support in Booking

### File Upload Paths
- **Excursion intro images**: `media/excursions/ex-{id}/` or `media/excursions/temp/`
- **Excursion gallery images**: `excursions/ex-{id}/` or `excursions/temp/`

---

## Notable Features & Considerations

### Commented Out Fields
Several region-related fields are commented out, suggesting a simplified location model:
- UserProfile.region
- PickupGroup.region  
- ExcursionAvailability.region

### Data Integrity Notes
- **Booking** has both `total_price` and `price` fields (potential redundancy)
- **PaymentMethod** model exists but only used in Transaction
- **DayOfWeek** capacity field is commented out
- **PickupPoint** priority and status fields are commented out

### Status Management
- Automatic status updates based on dates (ExcursionAvailability, Reservation)
- Soft delete pattern with `deleteByUser` flag in Booking
- Multiple status fields across different models

### Image Handling
- Custom upload paths based on excursion IDs
- Temporary paths for new excursions without IDs yet
- Support for multiple images per excursion

This reference should help us navigate the codebase and understand the data relationships throughout our conversations.
