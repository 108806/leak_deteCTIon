#!/usr/bin/env python3

import os
import re
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from webui.models import BreachedCredential
import logging

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Command(BaseCommand):
    help = 'Extracts potential admin usernames from BreachedCredential instances.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            default='admin_usernames.txt',
            help='Output file for admin usernames (default: admin_usernames.txt)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=1000,
            help='Limit the number of results (default: 1000)',
        )

    def handle(self, *args, **options):
        output_file = options['output']
        limit = options['limit']

        try:
            # Define patterns for admin usernames
            admin_patterns = [
                r'^admin(?:istrator)?$',  # Exact matches for "admin" or "administrator"
                r'^root$',  # Exact match for "root"
                r'admin@',  # Emails starting with "admin@"
                r'^super(?:user)?$',  # Exact matches for "super" or "superuser"
            ]

            # Query BreachedCredential instances
            credentials = BreachedCredential.objects.filter(
                Q(string__iregex=r'|'.join(admin_patterns)) |  # Match admin patterns
                Q(string__icontains=':admin')  # Match username:password where username is "admin"
            ).distinct()[:limit]  # Limit results and remove duplicates

            if not credentials.exists():
                self.stdout.write(self.style.WARNING("No admin usernames found."))
                return

            # Process and store admin usernames
            admin_usernames = set()
            for cred in credentials:
                try:
                    # Split string into username and password (if applicable)
                    if ':' in cred.string:
                        username = cred.string.split(':', 1)[0].lower()
                    else:
                        # Handle emails or standalone usernames
                        username = cred.string.lower()

                    # Check if username matches admin patterns
                    for pattern in admin_patterns:
                        if re.match(pattern, username) or 'admin' in username:
                            admin_usernames.add(username)
                            break

                    # Optionally, include related ScrapFile for context
                    if cred.file:
                        logger.info(f"Found admin username '{username}' from file: {cred.file.name}")
                    else:
                        logger.info(f"Found admin username '{username}' (no associated file)")

                except Exception as e:
                    logger.error(f"Error processing credential {cred.string}: {e}")
                    continue

            if not admin_usernames:
                self.stdout.write(self.style.WARNING("No admin usernames matched after processing."))
                return

            # Write results to file
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write("\n".join(sorted(admin_usernames)))
                self.stdout.write(self.style.SUCCESS(f"Found {len(admin_usernames)} admin usernames, saved to {output_file}"))
                logger.info(f"Admin usernames saved to {output_file}")
            except Exception as e:
                logger.error(f"Failed to write to {output_file}: {e}")
                raise CommandError(f"Could not write to {output_file}: {e}")

        except Exception as e:
            logger.error(f"Critical error in get_admin_usernames: {e}")
            traceback.print_exc()
            raise CommandError(f"Error retrieving admin usernames: {e}")

if __name__ == '__main__':
    # For running directly (outside Django management command)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    import django
    django.setup()
    Command().handle()