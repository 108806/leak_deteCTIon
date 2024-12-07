from django.core.management.base import BaseCommand
from webui.processor import process_scrap_files

class Command(BaseCommand):
    help = 'Process scrap files from MinIO and populate the database.'

    def handle(self, *args, **kwargs):
        self.stdout.write("[*] Starting to process scrap files...")
        process_scrap_files()
        self.stdout.write("[*] Scrap file processing completed.")
