import os
import logging
import hashlib
from django.core.management.base import BaseCommand
from webui.collector import collect_and_upload_files, load_hash_cache, save_hash_cache
from core.settings import AWS_STORAGE_BUCKET_NAME

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Scans Telegram download directories and pushes new files to MinIO'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', 
            action='store_true', 
            help='Force re-upload of all files, ignoring the hash cache'
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        
        TARGET_PATHS = ["/usr/share/Telegram-Files/", "/usr/share/combos"]
        HASH_CACHE_FILE = "/usr/src/app/file_hashes.json"
        
        if force:
            logger.info("Force mode enabled - clearing hash cache")
            save_hash_cache({})
        
        # Get current hash cache
        hash_cache = load_hash_cache()
        initial_cache_size = len(hash_cache)
        
        logger.info(f"Starting Telegram file sync. Hash cache contains {initial_cache_size} files.")
        
        # Use the collector function to upload new files
        collect_and_upload_files(source_paths=TARGET_PATHS, bucket_name=AWS_STORAGE_BUCKET_NAME)
        
        # Report on what happened
        current_cache = load_hash_cache()
        new_files_count = len(current_cache) - initial_cache_size
        
        if new_files_count > 0:
            logger.info(f"Sync completed. {new_files_count} new files uploaded to MinIO.")
            self.stdout.write(
                self.style.SUCCESS(f"Successfully synced {new_files_count} new files to MinIO")
            )
        else:
            logger.info("Sync completed. No new files found to upload.")
            self.stdout.write(
                self.style.SUCCESS("Sync completed. No new files needed to be uploaded.")
            )
