from django.core.management.base import BaseCommand
from django.utils import timezone
from main.models import ReferralCode
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Check and expire referral codes that have passed their expiration date'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be expired without actually updating the database',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        now = timezone.now()
        
        # Find active referral codes that have expired
        expired_codes = ReferralCode.objects.filter(
            status='active',
            expires_at__lt=now
        )
        
        count = expired_codes.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS('No expired referral codes found.')
            )
            return
        
        # Show which codes will be expired
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'[DRY RUN] Would expire {count} referral code(s):')
            )
            for code in expired_codes:
                self.stdout.write(
                    f'  - {code.code} (Agent: {code.agent.name if code.agent else "N/A"}, '
                    f'Expired: {code.expires_at.strftime("%Y-%m-%d %H:%M")})'
                )
        else:
            # Actually expire the codes
            expired_codes.update(status='inactive')
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully expired {count} referral code(s).')
            )
            
            # Log the action
            logger.info(f'Expired {count} referral code(s)')
            
            # Show details of expired codes
            for code in expired_codes:
                self.stdout.write(
                    f'  - {code.code} (Agent: {code.agent.name if code.agent else "N/A"})'
                )

