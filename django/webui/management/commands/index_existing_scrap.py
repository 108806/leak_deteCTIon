from django.core.management.base import BaseCommand
from webui.models import ScrapFile
from django_q.tasks import async_task

class Command(BaseCommand):
    help = "Indexes all existing ScrapFile records to Elasticsearch."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("Starting indexing of existing ScrapFiles..."))
        scrap_files = ScrapFile.objects.filter(count__gt=0)  # Tylko z credentialami
        total = scrap_files.count()
        self.stdout.write(self.style.NOTICE(f"Found {total} ScrapFiles to index"))

        for sf in scrap_files:
            async_task('webui.tasks.index_breached_credential', sf.id)
            self.stdout.write(self.style.SUCCESS(f"Queued ScrapFile {sf.id} with count {sf.count}"))

        self.stdout.write(self.style.SUCCESS(f"Finished queuing {total} ScrapFiles for indexing"))