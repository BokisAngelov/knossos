from django.core.management.base import BaseCommand
from django.utils import timezone
from main.models import ReferralCode
from main.utils import EmailService, EmailBuilder
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
        parser.add_argument(
            '--send-emails',
            action='store_true',
            help='Send email notifications to agents and admins',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        send_emails = options.get('send_emails', False)
        now = timezone.now()
        
        # Find active referral codes that have expired
        expired_codes = ReferralCode.objects.filter(
            status='active',
            expires_at__lt=now
        ).select_related('agent')
        
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
            # Store expired codes list before update
            expired_codes_list = list(expired_codes)
            
            # Actually expire the codes
            expired_codes.update(status='inactive')
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully expired {count} referral code(s).')
            )
            
            # Log the action
            logger.info(f'Expired {count} referral code(s)')
            
            # Show details of expired codes
            for code in expired_codes_list:
                self.stdout.write(
                    f'  - {code.code} (Agent: {code.agent.name if code.agent else "N/A"})'
                )
            
            # Send email notifications
            if send_emails:
                self.send_notifications(expired_codes_list)
    
    def send_notifications(self, expired_codes):
        """Send email notifications to agents and admins."""
        agents_notified = 0
        
        # Group codes by agent
        agent_codes = {}
        codes_without_agent = []
        
        for code in expired_codes:
            if code.agent and code.agent.email:
                if code.agent not in agent_codes:
                    agent_codes[code.agent] = []
                agent_codes[code.agent].append(code)
            else:
                codes_without_agent.append(code)
        
        # Send email to each agent
        for agent, codes in agent_codes.items():
            try:
                builder = EmailBuilder()
                builder.h2(f"Hello {agent.name}!")
                builder.warning(f"{len(codes)} referral code(s) have expired")
                builder.p("The following referral codes associated with your account have expired:")
                
                # Add codes as a card
                code_data = []
                for code in codes:
                    code_data.append((
                        'Code',
                        f"{code.code} (Expired: {code.expires_at.strftime('%B %d, %Y')})"
                    ))
                
                builder.card("Expired Referral Codes", code_data, border_color="#ff6b35")
                builder.p("These codes are no longer active and cannot be used by customers.")
                builder.p(
                    "If you need new referral codes, please contact your administrator "
                    "or request them through the admin panel."
                )
                builder.p("Best regards,<br>The iTrip Knossos Team")
                
                EmailService.send_dynamic_email_async(
                    subject=f'[iTrip Knossos] {len(codes)} Referral Code(s) Expired',
                    recipient_list=[agent.email],
                    email_body=builder.build(),
                    preview_text=f'{len(codes)} of your referral codes have expired',
                    email_kind='referral_codes_expired',
                )
                agents_notified += 1
                logger.info(f'Sent expiration notification to agent {agent.name} ({agent.email})')
                
            except Exception as e:
                logger.error(f'Failed to send notification to agent {agent.name}: {str(e)}')
        
        # Send admin notification
        try:
            builder = EmailBuilder()
            builder.h2("Referral Code Expiration Report")
            builder.warning(f"{len(expired_codes)} referral code(s) expired")
            
            # Group summary
            builder.card("Summary", {
                'Total Expired': len(expired_codes),
                'Agents Notified': agents_notified,
                'Codes Without Agent': len(codes_without_agent)
            })
            
            # Add details for each expired code
            if len(expired_codes) <= 10:
                for code in expired_codes:
                    agent_name = code.agent.name if code.agent else 'No Agent'
                    builder.card(f"Code: {code.code}", {
                        'Agent': agent_name,
                        'Discount': f"{code.discount}%",
                        'Expired': code.expires_at.strftime('%B %d, %Y at %H:%M')
                    }, border_color="#ff6b35")
            else:
                # Show first 5
                for code in expired_codes[:5]:
                    agent_name = code.agent.name if code.agent else 'No Agent'
                    builder.card(f"Code: {code.code}", {
                        'Agent': agent_name,
                        'Discount': f"{code.discount}%",
                        'Expired': code.expires_at.strftime('%B %d, %Y')
                    }, border_color="#ff6b35")
                builder.p(f"... and {len(expired_codes) - 5} more code(s)")
            
            builder.p("Best regards,<br>Automated System")
            
            EmailService.send_dynamic_email(
                subject=f'[iTrip Knossos] {len(expired_codes)} Referral Code(s) Expired',
                recipient_list=['bokis.angelov@innovade.eu'],
                email_body=builder.build(),
                preview_text=f'{len(expired_codes)} referral codes have expired',
                fail_silently=True
            )
            logger.info('Sent expiration notification to admin')
            
        except Exception as e:
            logger.error(f'Failed to send admin notification: {str(e)}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Sent notifications to {agents_notified} agent(s) and admin')
        )

