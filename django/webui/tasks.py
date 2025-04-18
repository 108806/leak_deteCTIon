from django_elasticsearch_dsl import Document
from webui.documents import BreachedCredentialDocument
from webui.models import ScrapFile
import logging
import time
from django.db.models import Q, F
from django.utils import timezone
from celery import task

logger = logging.getLogger(__name__)

def index_breached_credential(scrap_file_id):
    logger.debug(f"Task started for ScrapFile {scrap_file_id}")
    try:
        logger.debug(f"Fetching ScrapFile {scrap_file_id}")
        start_time = time.time()
        scrap_file = ScrapFile.objects.get(id=scrap_file_id)
        logger.debug(f"ScrapFile {scrap_file_id} fetched in {time.time() - start_time:.2f}s")

        total = scrap_file.count
        logger.debug(f"Indexing {total} credentials for ScrapFile {scrap_file_id}")

        batch_size = 1000
        batch_timeout = 300
        processed = 0

        credentials = scrap_file.breached_credentials.all()
        actual_count = credentials.count()
        logger.debug(f"Actual count from PSQL: {actual_count}")

        while processed < total:
            batch_start = time.time()
            logger.debug(f"Processing batch starting at offset {processed}")
            batch = credentials[processed:processed + batch_size]
            batch_count = len(batch)
            logger.debug(f"Fetched {batch_count} credentials in {time.time() - batch_start:.2f}s")

            if not batch:
                logger.warning(f"No more credentials at offset {processed}, expected {total}")
                break

            for cred in batch:
                #logger.debug(f"Indexing credential {cred.id}")
                doc = BreachedCredentialDocument.get(id=cred.id, ignore=404)
                if doc:
                    doc.update(cred)
                else:
                    BreachedCredentialDocument(id=cred.id, string=cred.string, added_at=cred.added_at).save()

            processed += batch_count
            logger.debug(f"Indexed batch of {batch_count} in {time.time() - batch_start:.2f}s, total processed: {processed}/{total}")
            if time.time() - batch_start > batch_timeout:
                logger.warning(f"Batch at offset {processed} exceeded timeout ({batch_timeout}s), stopping")
                break

        logger.debug(f"Finished indexing {processed}/{total} credentials for ScrapFile {scrap_file_id}")
    except Exception as e:
        logger.error(f"Error indexing ScrapFile {scrap_file_id}: {str(e)}", exc_info=True)

@task
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