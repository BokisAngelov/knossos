"""
Custom password validators (used in AUTH_PASSWORD_VALIDATORS and when calling validate_password).
"""
import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class DigitPasswordValidator:
    """Validate that the password contains at least one digit (0-9)."""
    def validate(self, password, user=None):
        if not re.search(r'\d', password):
            raise ValidationError(
                _("Password must contain at least one digit (0-9)."),
                code='password_no_digit',
            )

    def get_help_text(self):
        return _("Password must contain at least one digit (0-9).")
