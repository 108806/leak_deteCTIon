from django.core.management.base import BaseCommand
from webui.collector import collect_and_upload_files

class Command(BaseCommand):
    help = 'Run collector script to gather files or data.'

    def handle(self, *args, **kwargs):
        self.stdout.write("[*] Starting to collect files/data...")
        collect_and_upload_files()
        self.stdout.write(self.style.SUCCESS("[*] File/Data collection completed."))