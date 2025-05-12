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
from queue import Queue
import gc
from django.core.exceptions import ObjectDoesNotExist
from django.db import models

logger = logging.getLogger(__name__)

def line_splitter(line: str, max_length: int = 1024) -> list[str]:
    """Split a line into multiple strings if longer than max_length, based on the most frequent separator."""
    if len(line) <= max_length:
        return [line]
    separators = ['https:\\\\', '\\\\', '::', ':', ';', ',', '\r\n', '\n', '\\r\\n']
    sep_count = {s: line.count(s) for s in separators}
    max_separator = max(sep_count, key=sep_count.get)
    logger.debug(f"Line: '{line[:50]}...', Separator counts: {sep_count}, Chosen: '{max_separator}'")
    split_lines = [s.strip() for s in line.split(max_separator) if s.strip()]
    print(f"[*] Split {len(line)} chars into {len(split_lines)} parts using '{max_separator}'")
    return [s[:max_length] for s in split_lines if len(s) > 0]

def process_chunk(credentials, es_actions, es_client):
    """Process a chunk of credentials and actions"""
    if not credentials:
        return 0
        
    # Split long strings before bulk create
    processed_credentials = []
    for cred in credentials:
        if len(cred.string) > 1024:
            split_strings = line_splitter(cred.string)
            for split_str in split_strings:
                # Create new credential with split string
                new_cred = BreachedCredential(
                    id=hashlib.md5(f"{split_str}{time.time()}".encode()).hexdigest(),
                    string=split_str,
                    file=cred.file,
                    added_at=cred.added_at
                )
                processed_credentials.append(new_cred)
        else:
            processed_credentials.append(cred)
    
    try:
        # Try bulk create with processed credentials
        BreachedCredential.objects.bulk_create(processed_credentials, batch_size=1000, ignore_conflicts=True)
    except Exception as e:
        logger.error(f"Error in bulk create: {str(e)}")
        # If bulk create fails, try individual inserts
        for cred in processed_credentials:
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
    
    return len(processed_credentials)

def writer_process(queue, es_client, total_processed):
    """Single writer process to handle database inserts"""
    credentials = []
    es_actions = []
    chunk_size = 10000
    
    while True:
        try:
            item = queue.get(timeout=5)  # 5 second timeout
            if item is None:  # Signal to stop
                break
                
            credentials.append(item['credential'])
            es_actions.append(item['es_action'])
            
            if len(credentials) >= chunk_size:
                try:
                    process_chunk(credentials, es_actions, es_client)
                    total_processed[0] += len(credentials)
                    credentials.clear()
                    es_actions.clear()
                except Exception as e:
                    logger.error(f"Error in writer process: {str(e)}")
                    if "deadlock" in str(e).lower():
                        time.sleep(5)  # Wait before retrying
                        continue
                    raise
                    
        except Exception as e:
            if isinstance(e, TimeoutError):
                break
            logger.error(f"Error in writer process: {str(e)}")
            raise
    
    # Process any remaining items
    if credentials:
        try:
            process_chunk(credentials, es_actions, es_client)
            total_processed[0] += len(credentials)
        except Exception as e:
            logger.error(f"Error processing final chunk: {str(e)}")
            raise

def clean_string(s: str) -> str:
    """Clean a string by removing NULL characters and other problematic characters."""
    # Remove NULL characters and other control characters
    s = ''.join(char for char in s if ord(char) >= 32 or char in '\n\r\t')
    # Remove any remaining NULL bytes
    s = s.replace('\x00', '')
    # Remove any other problematic characters
    s = s.encode('ascii', 'ignore').decode('ascii')
    return s.strip()

def reader_process(chunk, scrap_file, queue):
    """Process a chunk of data and put results in queue"""
    try:
        for line in chunk.splitlines():
            line = line.strip()
            if ':' in line:  # Basic validation
                # Clean the line before processing
                line = clean_string(line)
                if not line:  # Skip if line is empty after cleaning
                    continue
                    
                # Generate ID
                unique_string = line.strip()
                cred_id = hashlib.md5(unique_string.encode()).hexdigest()
                
                # Create credential
                credential = BreachedCredential(
                    id=cred_id,
                    string=line,
                    file=scrap_file,
                    added_at=timezone.now()
                )
                
                # Prepare Elasticsearch action
                es_action = {
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
                }
                
                # Put in queue
                queue.put({
                    'credential': credential,
                    'es_action': es_action
                })
    except Exception as e:
        logger.error(f"Error in reader process: {str(e)}")
        raise

@shared_task(bind=True, max_retries=3)
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
        
        # Setup queue and shared counter
        queue = Queue(maxsize=100000)  # Limit queue size to prevent memory issues
        total_processed = [0]  # Use list for mutable shared state
        last_log_time = time.time()
        
        # Start writer process
        with ThreadPoolExecutor(max_workers=1) as writer_executor:
            writer_future = writer_executor.submit(writer_process, queue, es_client, total_processed)
            
            # Start reader processes
            with ThreadPoolExecutor(max_workers=4) as reader_executor:
                futures = []
                buffer = ""
                
                try:
                    for chunk in data.stream(32768):
                        buffer += chunk.decode('utf-8', errors='replace')
                        chunks = buffer.splitlines()
                        buffer = chunks.pop() if chunks else ""
                        
                        # Submit chunks to reader processes
                        for chunk in chunks:
                            futures.append(reader_executor.submit(reader_process, chunk, scrap_file, queue))
                            
                            # Log progress every 5 seconds
                            current_time = time.time()
                            if current_time - last_log_time >= 5:
                                logger.debug(f"Processed {total_processed[0]} lines so far")
                                last_log_time = current_time
                
                except Exception as e:
                    logger.error(f"Error processing file content: {str(e)}")
                    data.close()
                    raise
                
                finally:
                    data.close()
                    
                    # Wait for all reader processes to complete
                    for future in futures:
                        future.result()
                    
                    # Signal writer to stop
                    queue.put(None)
                    
                    # Wait for writer to complete
                    writer_future.result()
        
        # Update scrap file count
        scrap_file.count = BreachedCredential.objects.filter(file=scrap_file).count()
        scrap_file.save()

        # Verify counts
        total_scrap_count = ScrapFile.objects.aggregate(total=models.Sum('count'))['total'] or 0
        total_credential_count = BreachedCredential.objects.count()
        
        logger.debug(f"Total ScrapFile count: {total_scrap_count}")
        logger.debug(f"Total BreachedCredential count: {total_credential_count}")
        logger.debug(f"Count difference: {total_credential_count - total_scrap_count}")
        
        if total_scrap_count != total_credential_count:
            logger.warning(f"Count mismatch! ScrapFiles: {total_scrap_count}, Credentials: {total_credential_count}")
            print(f"[*] WARNING: Count mismatch! ScrapFiles: {total_scrap_count}, Credentials: {total_credential_count}")

        processing_time = time.time() - start_time
        logger.debug(f"Finished processing ScrapFile {scrap_file_id} in {processing_time:.2f}s")
        logger.debug(f"Total processed: {total_processed[0]} credentials")
        
        return {
            'status': 'success',
            'scrap_file_id': scrap_file_id,
            'file_name': scrap_file.name,
            'total_processed': total_processed[0],
            'processing_time': processing_time,
            'total_scrap_count': total_scrap_count,
            'total_credential_count': total_credential_count,
            'count_mismatch': total_scrap_count != total_credential_count
        }
        
    except Exception as e:
        logger.error(f"Error processing ScrapFile {scrap_file_id}: {str(e)}", exc_info=True)
        if "deadlock" in str(e).lower():
            raise self.retry(exc=e, countdown=5)
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