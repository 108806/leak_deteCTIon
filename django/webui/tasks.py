from django_elasticsearch_dsl import Document
from webui.documents import BreachedCredentialDocument
from webui.models import ScrapFile, BreachedCredential
import logging
import time
from django.db.models import Q, F
from django.utils import timezone
from celery import shared_task
from minio import Minio
from django.conf import settings
import io
import hashlib
from elasticsearch import Elasticsearch
from concurrent.futures import ThreadPoolExecutor
import gc
from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger(__name__)

def process_chunk(credentials, es_actions, es_client):
    """Process a chunk of credentials and actions"""
    if not credentials:
        return 0
        
    try:
        # Try bulk create first
        BreachedCredential.objects.bulk_create(credentials, batch_size=1000, ignore_conflicts=True)
    except Exception as e:
        logger.error(f"Error in bulk create: {str(e)}")
        # If bulk create fails, try individual inserts
        for cred in credentials:
            try:
                BreachedCredential.objects.create(
                    id=cred.id,
                    string=cred.string,
                    file=cred.file,
                    added_at=cred.added_at
                )
            except Exception as e:
                logger.debug(f"Duplicate credential skipped: {cred.id}")
                continue
    
    # Process Elasticsearch actions
    if es_actions:
        try:
            # Format actions for Elasticsearch bulk API
            formatted_actions = []
            for action in es_actions:
                # Add the index operation
                formatted_actions.append({
                    'index': {
                        '_index': action['_index'],
                        '_id': action['_id']
                    }
                })
                # Add the document
                formatted_actions.append(action['_source'])
            
            es_client.bulk(operations=formatted_actions, refresh=True)
        except Exception as e:
            logger.error(f"Error in Elasticsearch bulk: {str(e)}")
    
    return len(credentials)

@shared_task(bind=True, max_retries=0)  # Disable retries for this task
def index_breached_credential(self, scrap_file_id):
    """
    Index a breached credential file.
    
    Args:
        scrap_file_id: The ID of the ScrapFile to process
        
    Returns:
        dict: Status information about the processing
    """
    logger.debug(f"Task started for ScrapFile {scrap_file_id}")
    try:
        # Validate scrap_file_id exists before proceeding
        try:
            scrap_file = ScrapFile.objects.get(id=scrap_file_id)
        except ObjectDoesNotExist:
            logger.error(f"ScrapFile {scrap_file_id} does not exist")
            return {
                'status': 'error',
                'message': f'ScrapFile {scrap_file_id} does not exist',
                'scrap_file_id': scrap_file_id
            }

        logger.debug(f"ScrapFile {scrap_file_id} fetched")
        start_time = time.time()

        # Initialize clients
        minio_client = Minio(
            'minio:9000',
            access_key=settings.AWS_ACCESS_KEY_ID,
            secret_key=settings.AWS_SECRET_ACCESS_KEY,
            secure=False
        )
        es_client = Elasticsearch(['http://elastic:9200'])

        # Get file from MinIO
        logger.debug(f"Reading file {scrap_file.name} from MinIO")
        try:
            data = minio_client.get_object('breached-credentials', scrap_file.name)
        except Exception as e:
            logger.error(f"Error accessing MinIO file {scrap_file.name}: {str(e)}")
            return {
                'status': 'error',
                'message': f'Error accessing MinIO file: {str(e)}',
                'scrap_file_id': scrap_file_id,
                'file_name': scrap_file.name
            }
        
        # Process file content in chunks
        logger.debug(f"Processing file content")
        credentials = []
        es_actions = []
        chunk_size = 50000  # Increased chunk size
        buffer = ""
        total_processed = 0
        last_log_time = time.time()
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            
            try:
                for chunk in data.stream(32768):  # Increased buffer size
                    buffer += chunk.decode('utf-8', errors='replace')
                    lines = buffer.splitlines()
                    buffer = lines.pop() if lines else ""
                    
                    for line in lines:
                        line = line.strip()
                        if ':' in line:  # Basic validation
                            # Generate ID
                            unique_string = line.strip()  # Just use the credential string itself
                            cred_id = hashlib.md5(unique_string.encode()).hexdigest()
                            
                            # Create credential
                            credentials.append(BreachedCredential(
                                id=cred_id,
                                string=line,
                                file=scrap_file,
                                added_at=timezone.now()
                            ))
                            
                            # Prepare Elasticsearch action
                            es_actions.append({
                                '_index': 'breached_credentials',
                                '_id': cred_id,
                                '_source': {
                                    'string': line,
                                    'added_at': timezone.now().isoformat(),
                                    'file_id': scrap_file.id,
                                    'file_name': scrap_file.name,
                                    'file_size': float(scrap_file.size),
                                    'file_uploaded_at': scrap_file.added_at.isoformat()
                                }
                            })
                            
                            # Process chunk when we reach chunk_size
                            if len(credentials) >= chunk_size:
                                # Submit chunk for processing
                                futures.append(executor.submit(
                                    process_chunk,
                                    credentials.copy(),
                                    es_actions.copy(),
                                    es_client
                                ))
                                
                                # Clear current chunk
                                credentials.clear()
                                es_actions.clear()
                                
                                # Force garbage collection
                                gc.collect()
                                
                                # Log progress every 5 seconds
                                current_time = time.time()
                                if current_time - last_log_time >= 5:
                                    completed = sum(f.done() for f in futures)
                                    total_processed += completed * chunk_size
                                    logger.debug(f"Processed {total_processed} lines so far")
                                    last_log_time = current_time
                
                # Process remaining credentials
                if credentials:
                    futures.append(executor.submit(
                        process_chunk,
                        credentials,
                        es_actions,
                        es_client
                    ))
                
                # Wait for all futures to complete
                total_processed += sum(f.result() for f in futures)
                
            except Exception as e:
                logger.error(f"Error processing file content: {str(e)}")
                data.close()
                raise
            
            finally:
                data.close()
        
        # Update scrap file count
        scrap_file.count = BreachedCredential.objects.filter(file=scrap_file).count()
        scrap_file.save()

        processing_time = time.time() - start_time
        logger.debug(f"Finished processing ScrapFile {scrap_file_id} in {processing_time:.2f}s")
        logger.debug(f"Total processed: {total_processed} credentials")
        
        return {
            'status': 'success',
            'scrap_file_id': scrap_file_id,
            'file_name': scrap_file.name,
            'total_processed': total_processed,
            'processing_time': processing_time
        }
        
    except Exception as e:
        logger.error(f"Error processing ScrapFile {scrap_file_id}: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'message': str(e),
            'scrap_file_id': scrap_file_id
        }

@shared_task
def index_breached_credentials():
    """Index all breached credentials in Elasticsearch."""
    try:
        # Get all credentials that need indexing
        credentials = BreachedCredential.objects.filter(
            Q(indexed=False) | Q(modified__gt=F('last_indexed'))
        ).select_related('file')
        
        if not credentials.exists():
            return "No credentials need indexing"
        
        # Bulk index the credentials
        actions = []
        for credential in credentials:
            doc = BreachedCredentialDocument(
                meta={'id': credential.id},
                string=credential.string,
                file_id=credential.file.id,
                file_name=credential.file.name,
                file_size=credential.file.size,
                file_uploaded_at=credential.file.uploaded_at,
                created_at=credential.created_at,
                modified=credential.modified
            )
            actions.append(doc)
        
        # Bulk index the documents
        BreachedCredentialDocument.bulk(actions)
        
        # Update the indexed status
        credentials.update(
            indexed=True,
            last_indexed=timezone.now()
        )
        
        return f"Successfully indexed {len(credentials)} credentials"
        
    except Exception as e:
        logger.error("Error indexing credentials: %s", str(e))
        raise