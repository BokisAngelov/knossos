from .views import manage_cookies

def voucher_context(request):
    voucher_code = manage_cookies(request, 'voucher_code', None, 'get')
    return_data = {}
    
    if voucher_code:
        try:
            from .models import Reservation
            voucher = Reservation.objects.get(voucher_id=voucher_code)
            if voucher:
                return_data = {
                    'client_name': voucher.client_name,
                    'region_id': voucher.hotel.pickup_group.region.id,
                }
        except Exception:
            voucher_code = None
            return_data = {}
    
    return {
        'voucher_code': voucher_code,
        'voucher_data': return_data
    } 