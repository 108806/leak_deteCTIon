from django.core.management.base import BaseCommand
from minio import Minio
from django.conf import settings
from webui.models import ScrapFile
from webui.tasks import index_breached_credential
import logging
import time

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Index data from MinIO directories'

    def add_arguments(self, parser):
        parser.add_argument('--directory', type=str, help='Specific directory to process')
        parser.add_argument('--batch-size', type=int, default=1000, help='Number of files to process in one batch')

    def handle(self, *args, **options):
        # Initialize MinIO client
        client = Minio(
            'minio:9000',
            access_key=settings.AWS_ACCESS_KEY_ID,
            secret_key=settings.AWS_SECRET_ACCESS_KEY,
            secure=False
        )

        # Get list of directories
        directories = [obj.object_name for obj in client.list_objects('breached-credentials')]
        
        # If specific directory is provided, only process that one
        if options['directory']:
            if options['directory'] not in directories:
                logger.error(f"Directory {options['directory']} not found in MinIO")
                return
            directories = [options['directory']]

        # Process each directory
        for directory in directories:
            logger.info(f"Processing directory: {directory}")
            start_time = time.time()
            
            # Get all files in the directory
            files = list(client.list_objects('breached-credentials', prefix=directory))
            total_files = len(files)
            logger.info(f"Found {total_files} files in {directory}")
            
            # Process files in batches
            for i in range(0, total_files, options['batch_size']):
                batch = files[i:i + options['batch_size']]
                batch_start = time.time()
                
                for file_obj in batch:
                    try:
                        # Convert size from bytes to MB
                        size_in_mb = file_obj.size / (1024 * 1024)
                        
                        # Create or get ScrapFile record
                        scrap_file, created = ScrapFile.objects.get_or_create(
                            name=file_obj.object_name,
                            defaults={
                                'size': size_in_mb,  # Store size in MB
                                'count': 0  # Will be updated by the task
                            }
                        )
                        
                        # Start indexing task
                        index_breached_credential(scrap_file.id)
                        
                    except Exception as e:
                        logger.error(f"Error processing file {file_obj.object_name}: {str(e)}")
                
                batch_time = time.time() - batch_start
                logger.info(f"Processed batch {i//options['batch_size'] + 1} of {(total_files-1)//options['batch_size'] + 1} in {batch_time:.2f}s")
            
            total_time = time.time() - start_time
            logger.info(f"Finished processing {directory} in {total_time:.2f}s")