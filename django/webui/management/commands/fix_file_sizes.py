from django.core.management.base import BaseCommand
from django.db import transaction
from webui.models import ScrapFile
from minio import Minio
from django.conf import settings
import logging

class Command(BaseCommand):
    help = 'Fix file sizes in the database by getting actual sizes from MinIO'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true', help='Process all files, not just those with likely incorrect sizes')

    def handle(self, *args, **options):
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger('fix_file_sizes')
        
        # Connect to MinIO
        client = Minio(
            'minio:9000',
            access_key=settings.AWS_ACCESS_KEY_ID,
            secret_key=settings.AWS_SECRET_ACCESS_KEY,
            secure=False
        )
        
        # Count total files to process - only process likely incorrect files by default
        process_all = options.get('all', False)
        if process_all:
            files = ScrapFile.objects.all()
            self.stdout.write(f"Processing ALL files (including those with likely correct sizes)")
        else:
            # Files with sizes > 1GB (1024MB) are likely incorrect
            # Files with sizes > 1000MB are likely incorrect
            # Use a disjunction of criteria to catch various incorrect sizes
            files = (ScrapFile.objects.filter(size__gt=1024) | 
                     ScrapFile.objects.filter(size__gt=1000))
            self.stdout.write(f"Processing ONLY files with likely incorrect sizes (>1000MB or >1024MB)")
        
        total = files.count()
        self.stdout.write(f"Found {total} files to process")
        
        # Track largest files to report
        largest_files = []
        
        # Process each file
        updated_count = 0
        error_count = 0
        
        for i, scrap_file in enumerate(files, 1):
            try:
                # Get stats from MinIO
                stats = client.stat_object('breached-credentials', scrap_file.name)
                
                # Calculate size in MB (correctly)
                size_in_mb = stats.size / (1024 * 1024)
                
                # Check if size is different from current value (by a significant amount)
                if abs(float(scrap_file.size) - size_in_mb) > 0.01:  # Allow small floating point differences
                    old_size = float(scrap_file.size)
                    self.stdout.write(f'Fixing size for {scrap_file.name}: {old_size:.2f} MB → {size_in_mb:.2f} MB')
                    
                    # Update the size
                    with transaction.atomic():
                        scrap_file.size = size_in_mb
                        scrap_file.save(update_fields=['size'])
                    
                    updated_count += 1
                    
                    # Track largest files
                    largest_files.append((scrap_file.name, size_in_mb, old_size))
                    largest_files.sort(key=lambda x: x[1], reverse=True)
                    if len(largest_files) > 5:
                        largest_files.pop()
                
                # Print progress every 50 files
                if i % 50 == 0 or i == 1 or i == total:
                    self.stdout.write(f"Progress: {i}/{total} files processed ({updated_count} updated, {error_count} errors)")
            
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f'Error processing {scrap_file.name}: {e}'))
                continue
        
        # Report results
        self.stdout.write(self.style.SUCCESS(f"Completed: {updated_count} file sizes updated, {error_count} errors"))
        
        if largest_files:
            self.stdout.write("\nLargest files:")
            for name, new_size, old_size in largest_files:
                self.stdout.write(f"  {name}: {new_size:.2f} MB (was {old_size:.2f} MB)")

