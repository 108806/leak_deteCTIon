from django.core.management.base import BaseCommand
from webui.processor import process_scrap_files, BreachedCredential, ScrapFile

class Command(BaseCommand):
    help = 'Clear the database of all data from BreachedCredential and ScrapFile models.'
    def handle(self, *args, **kwargs):
        # Clear BreachedCredential records
        breached_count = BreachedCredential.objects.count()
        BreachedCredential.objects.all().delete()
        self.stdout.write(self.style.WARNING(f"✅ Deleted {breached_count} records from BreachedCredential."))

        # Clear ScrapFile records
        scrap_count = ScrapFile.objects.count()
        ScrapFile.objects.all().delete()
        self.stdout.write(self.style.WARNING(f"✅ Deleted {scrap_count} records from ScrapFile."))

        self.stdout.write(self.style.SUCCESS("✅ Database cleared successfully."))
