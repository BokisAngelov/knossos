# Email Templates - User Guide

## Overview

This directory contains HTML email templates for the iTrip Knossos application. All templates extend the base template which provides consistent branding, styling, and structure.

---

## 📁 File Structure

```
emails/
├── README.md                    # This file
├── base_email.html             # Base template with header/footer
└── booking_confirmation.html   # Example: Booking confirmation email
```

---

## 🎨 Base Template Features

The `base_email.html` template includes:

- **Header**: Blue gradient banner with logo and "KNOSSOS travel" branding
- **Dynamic Content Area**: Customizable content section
- **Footer**: Contact information, social links, and legal text
- **Responsive Design**: Mobile-friendly layout
- **Email Client Compatibility**: Tested with major email clients
- **Dark Mode Support**: Adapts to user's color scheme preference

### Color Scheme
- Primary Blue: `#2196f3`
- Navigation Blue: `#1976d2`
- Brown/Header: `#463229`
- Text Gray: `#4d4d4d`
- Background: `#fcfcfc`

---

## 🚀 How to Use

### Method 1: Using EmailService (Recommended)

```python
from main.utils import EmailService

# Send email using template
EmailService.send_templated_email(
    template_name='emails/booking_confirmation.html',
    context={
        'customer_name': 'John Doe',
        'booking_id': 'BK-12345',
        'excursion_name': 'Troodos Mountains Tour',
        'excursion_date': 'December 15, 2024',
        'pickup_point': 'Limassol Marina',
        'total_guests': 4,
        'adults': 2,
        'children': 2,
        'total_price': '90.00',
        'booking_url': 'https://www.itripknossos.com/bookings/12345',
    },
    subject='[iTrip Knossos] Booking Confirmed - Troodos Mountains Tour',
    recipient_list=['john.doe@example.com'],
    fail_silently=False
)
```

### Method 2: Manual Template Rendering

```python
from django.template.loader import render_to_string
from django.core.mail import send_mail
from main.utils import EmailService

# Render template
html_message = render_to_string('emails/booking_confirmation.html', {
    'customer_name': 'Jane Smith',
    'booking_id': 'BK-67890',
    # ... other context variables
})

# Send email
EmailService.send_email(
    subject='Booking Confirmed',
    message='Your booking has been confirmed',  # Plain text fallback
    recipient_list=['jane.smith@example.com'],
    html_message=html_message
)
```

---

## 📝 Creating New Email Templates

### Step 1: Create Template File

Create a new file in `knossos/main/templates/emails/` (e.g., `payment_failed.html`)

### Step 2: Extend Base Template

```django
{% extends 'emails/base_email.html' %}

{% block email_title %}Payment Failed - iTrip Knossos{% endblock %}

{% block preview_text %}Payment failed for your booking{% endblock %}

{% block email_content %}
<!-- Your email content here -->
<h2 style="color: #463229; margin-top: 0;">
    Hello {{ customer_name }}!
</h2>

<p style="color: #e53935; font-size: 18px; font-weight: 600;">
    ⚠️ Payment Failed
</p>

<p style="color: #4d4d4d; font-size: 16px; line-height: 1.6;">
    We were unable to process your payment for booking #{{ booking_id }}.
</p>

<!-- Add your custom content -->

{% endblock %}
```

### Step 3: Use the Template

```python
EmailService.send_templated_email(
    template_name='emails/payment_failed.html',
    context={'customer_name': 'John', 'booking_id': '12345'},
    subject='Payment Failed',
    recipient_list=['customer@email.com']
)
```

---

## 🎯 Template Blocks Reference

### Required Blocks

| Block Name | Description | Example |
|------------|-------------|---------|
| `email_title` | Page title (for email client) | `Booking Confirmed` |
| `preview_text` | Preview text shown in inbox | `Your booking for...` |
| `email_content` | Main email content | Full email body HTML |

### Optional Blocks

| Block Name | Description | Default |
|------------|-------------|---------|
| `unsubscribe_link` | Unsubscribe link (marketing emails) | Empty |

---

## 📦 Reusable Components

### 1. Information Card

```html
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" 
       style="background-color: #f9f9f9; border-radius: 8px; border-left: 4px solid #2196f3; margin-bottom: 24px;">
    <tr>
        <td style="padding: 20px;">
            <h3 style="color: #463229; margin-top: 0;">Card Title</h3>
            <p style="color: #4d4d4d; font-size: 14px;">Card content here...</p>
        </td>
    </tr>
</table>
```

### 2. Call-to-Action Button

```html
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
    <tr>
        <td style="text-align: center; padding: 20px 0;">
            <a href="{{ url }}" class="btn" 
               style="display: inline-block; padding: 14px 28px; background-color: #2196f3; 
                      color: #ffffff !important; text-decoration: none; border-radius: 6px; 
                      font-weight: 600; font-size: 16px;">
                Button Text
            </a>
        </td>
    </tr>
</table>
```

### 3. Warning/Alert Box

```html
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" 
       style="background-color: #fff4f0; border-radius: 8px; margin-bottom: 24px;">
    <tr>
        <td style="padding: 20px;">
            <h3 style="color: #ff6b35; margin-top: 0; font-size: 16px;">
                ⚠️ Important
            </h3>
            <p style="color: #4d4d4d; font-size: 14px;">
                Alert message here...
            </p>
        </td>
    </tr>
</table>
```

### 4. Success Message

```html
<p style="color: #4caf50; font-size: 18px; font-weight: 600; margin: 0 0 24px;">
    ✓ Success message here
</p>
```

### 5. Key-Value List

```html
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
    <tr>
        <td style="padding: 8px 0; color: #666666; font-size: 14px;">
            Label:
        </td>
        <td style="padding: 8px 0; color: #463229; font-size: 14px; text-align: right; font-weight: 600;">
            Value
        </td>
    </tr>
</table>
```

---

## 🎨 Styling Guidelines

### Colors for Different Message Types

| Type | Background | Text Color | Border |
|------|-----------|------------|--------|
| Info | `#f9f9f9` | `#2196f3` | `#2196f3` |
| Success | `#fbfff3` | `#4caf50` | `#4caf50` |
| Warning | `#fff4f0` | `#ff6b35` | `#ff6b35` |
| Error | `#fff5f5` | `#e53935` | `#e53935` |

### Typography

```css
/* Headings */
h1: 28px, #463229, weight: 600
h2: 24px, #463229, weight: 600
h3: 20px, #463229, weight: 600

/* Body text */
p: 16px, #4d4d4d, line-height: 1.6

/* Small text */
small: 14px, #666666
```

### Spacing

- **Section padding**: `40px` (desktop), `20px` (mobile)
- **Card padding**: `20px`
- **Button padding**: `14px 28px`
- **Element margin**: `16px` (paragraphs), `24px` (sections)

---

## ✅ Best Practices

### 1. Always Include Plain Text
The `send_templated_email()` method automatically generates a plain text version, but you can customize it by stripping specific elements.

### 2. Use Inline Styles
Email clients have limited CSS support. Always use inline styles for critical elements.

### 3. Test Across Email Clients
Test your emails in:
- Gmail (Web & Mobile)
- Outlook (Desktop & Web)
- Apple Mail
- Mobile devices (iOS & Android)

### 4. Keep Images Small
- Optimize images before using
- Use alt text for all images
- Consider that some clients block images by default

### 5. Personalization
Always use the customer's name and relevant booking details to make emails feel personal.

### 6. Clear Call-to-Action
Every email should have a clear, prominent CTA button.

---

## 🧪 Testing

### Test Email Locally

```python
# In Django shell or view
from main.utils import EmailService

EmailService.send_templated_email(
    template_name='emails/booking_confirmation.html',
    context={
        'customer_name': 'Test User',
        'booking_id': 'TEST-123',
        'excursion_name': 'Test Excursion',
        'excursion_date': 'Tomorrow',
        'pickup_point': 'Test Location',
        'total_guests': 2,
        'adults': 2,
        'children': 0,
        'total_price': '50.00',
        'booking_url': 'http://localhost:8000/bookings/123',
    },
    subject='[TEST] Booking Confirmation',
    recipient_list=['your-test-email@example.com']
)
```

### Preview in Browser

You can render the template in a view to preview in browser:

```python
from django.shortcuts import render

def preview_email(request):
    context = {
        'customer_name': 'John Doe',
        'booking_id': 'BK-12345',
        # ... add all context variables
    }
    return render(request, 'emails/booking_confirmation.html', context)
```

---

## 📧 Update Contact Information

Edit the footer in `base_email.html` to update:
- Support email
- Phone number
- Website URL
- Physical address
- Social media links

---

## 🌍 Multi-Language Support

To add multi-language support:

1. Use Django's `{% trans %}` tags
2. Create language-specific template files
3. Pass language preference in context

Example:
```django
{% load i18n %}
<p>{% trans "Hello" %} {{ customer_name }}!</p>
```

---

## 📱 Mobile Responsiveness

The base template includes mobile-responsive styles:
- Stacks columns on small screens
- Adjusts font sizes
- Increases touch target sizes
- Reduces padding for better fit

Test on actual mobile devices before sending!

---

## 🔒 Security Notes

- Never include sensitive data in plain text
- Use HTTPS for all links
- Validate all user input before including in emails
- Use access tokens for authentication links (already implemented)

---

## 📚 Additional Resources

- [Email Client CSS Support](https://www.campaignmonitor.com/css/)
- [Email Accessibility Best Practices](https://www.litmus.com/blog/email-accessibility/)
- [Django Email Documentation](https://docs.djangoproject.com/en/stable/topics/email/)

---

**Last Updated:** December 2, 2025  
**Maintained by:** iTrip Knossos Development Team

