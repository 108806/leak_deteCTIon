from django.core.management.base import BaseCommand
from webui.processor import process_scrap_files, BreachedCredential


class Command(BaseCommand):
    help = "Process scrap files from MinIO and populate the database."

    def handle(self, *args, **kwargs):
        initial_count = BreachedCredential.objects.count()
        self.stdout.write(
            f"[*] Initial number of records in the database: {initial_count}"
        )

        self.stdout.write("[*] Starting to process scrap files...")
        process_scrap_files(force_reprocess=False)
        self.stdout.write(self.style.SUCCESS("[*] Scrap file processing completed."))

        # Get the final count of records
        final_count = BreachedCredential.objects.count()
        self.stdout.write(f"[*] Final number of records in the database: {final_count}")

        # Print the difference
        added_records = final_count - initial_count
        self.stdout.write(
            self.style.SUCCESS(f"[*] Number of records added: {added_records}")
        )
