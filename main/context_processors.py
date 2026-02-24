from .views import manage_cookies
import logging

logger = logging.getLogger(__name__)


def voucher_context(request):
    """
    Add voucher/reservation data to template context.
    Uses VoucherService for consistent data retrieval.
    """
    voucher_code = manage_cookies(request, 'voucher_code', None, 'get')
    return_data = {}
    
    if voucher_code:
        try:
            from .models import Reservation
            from .utils import VoucherService
            from django.utils import timezone
            
            # Get reservation from database (don't fetch from API in context processor)
            # Handle case where client_profile field might not exist
            try:
                voucher = Reservation.objects.select_related(
                    'pickup_group', 'pickup_point', 'hotel', 'client_profile'
                ).prefetch_related('bookings').get(voucher_id=voucher_code)
            except Exception:
                # Fallback without client_profile if field doesn't exist
                voucher = Reservation.objects.select_related(
                    'pickup_group', 'pickup_point', 'hotel'
                ).prefetch_related('bookings').get(voucher_id=voucher_code)
            
            # Check if voucher is still valid using status and check_out fields
            # Handle both date objects and strings
            checkout_date = voucher.check_out
            if isinstance(checkout_date, str):
                from datetime import datetime
                try:
                    checkout_date = datetime.strptime(checkout_date, '%Y-%m-%d').date()
                except:
                    checkout_date = datetime.fromisoformat(checkout_date).date()
            
            is_valid = (
                voucher.status == 'active' 
                # and
                # checkout_date >= timezone.now().date()
            )
            
            if is_valid:
                return_data = VoucherService.get_voucher_data(voucher)
            else:
                # Voucher expired, clear it
                logger.info(f"Voucher {voucher_code} has expired, clearing from context")
                voucher_code = None
                return_data = {}
                
        except Reservation.DoesNotExist:
            logger.warning(f"Voucher {voucher_code} not found in database")
            voucher_code = None
            return_data = {}
        except Exception as e:
            logger.error(f"Error in voucher_context for {voucher_code}: {str(e)}")
            voucher_code = None
            return_data = {}
    
    return {
        'voucher_code': voucher_code,
        'voucher_data': return_data
    } 