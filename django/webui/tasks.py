from django_elasticsearch_dsl import Document
from webui.documents import BreachedCredentialDocument
from webui.models import ScrapFile
import logging
import time

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