#!/usr/bin/env python3

import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User  # Use your custom user model if different
from django.db.models import Q  # Add this import
import logging
import traceback 


# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Command(BaseCommand):
    help = 'Lists all Django admin users (superusers or staff users) in the application.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            default='django_admins.txt',
            help='Output file for admin usernames (default: django_admins.txt)',
        )

    def handle(self, *args, **options):
        output_file = options['output']

        try:
            # Query all users who are either superusers or staff
            admin_users = User.objects.filter(
                Q(is_superuser=True) | Q(is_staff=True)
            ).distinct().order_by('username')

            if not admin_users.exists():
                self.stdout.write(self.style.WARNING("No admin users found in the Django application."))
                return

            # Process and store admin usernames
            admin_usernames = []
            for user in admin_users:
                username = user.username
                email = user.email if user.email else "No email"
                is_superuser = user.is_superuser
                is_staff = user.is_staff
                admin_usernames.append(username)
                logger.info(
                    f"Admin user: {username} (Email: {email}, Superuser: {is_superuser}, Staff: {is_staff})"
                )

            # Write results to file
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write("\n".join(sorted(admin_usernames)))
                self.stdout.write(self.style.SUCCESS(f"Found {len(admin_usernames)} admin users, saved to {output_file}"))
                logger.info(f"Admin usernames saved to {output_file}")
            except Exception as e:
                logger.error(f"Failed to write to {output_file}: {e}")
                raise CommandError(f"Could not write to {output_file}: {e}")

        except Exception as e:
            logger.error(f"Critical error in list_django_admins: {e}")
            traceback.print_exc()
            raise CommandError(f"Error retrieving Django admin users: {e}")

if __name__ == '__main__':
    # For running directly (outside Django management command)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    import django
    django.setup()
    Command().handle()