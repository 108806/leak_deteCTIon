from core.settings import AWS_STORAGE_BUCKET_NAME, AWS_S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from webui.models import ScrapFile, BreachedCredential
from minio import Minio
from minio.datatypes import Object
import hashlib
import logging
import io

logger = logging.getLogger(__name__)

def calculate_file_size(obj: Object) -> str:
    """Calculate file size in MB from MinIO object metadata, rounded to 2 decimal places."""
    size_bytes = obj.size
    return f"{size_bytes / (1024 ** 2):.2f}"

def line_splitter(line: str, max_length: int = 1024) -> list[str]:
    """Split a line into chunks if it exceeds max_length, preserving content."""
    if len(line) <= max_length:
        return [line]
    # Simple split by whitespace or characters, adjust for CTI needs (e.g., email:pass)
    chunks = []
    while line:
        chunk = line[:max_length].rsplit(" ", 1)[0]  # Split on last space
        chunks.append(chunk)
        line = line[len(chunk):].lstrip()
    return chunks

def process_scrap_files(force_reprocess: bool = False) -> None:
    """
    Process scrap files from MinIO by streaming content, create ScrapFile and BreachedCredential instances,
    with deduplication by SHA-256 hash.

    Args:
        force_reprocess (bool): If True, reprocess files even if already processed.
    """
    print("[*] Running process_scrap_files...")
    client = Minio(
        AWS_S3_ENDPOINT_URL,
        access_key=AWS_ACCESS_KEY_ID,
        secret_key=AWS_SECRET_ACCESS_KEY,
        secure=False,  # Use True if SSL/TLS enabled; adjust based on AWS_S3_ENDPOINT_URL
    )
    bucket_name = AWS_STORAGE_BUCKET_NAME
    lines_total = 0

    try:
        objects = client.list_objects(bucket_name, recursive=True)
        for obj in objects:
            object_key = obj.object_name  # This is the path (key) in MinIO, e.g., "1501020529/1192_Hungary_Combolistfresh.txt"
            logger.info(f"Processing MinIO object: {object_key}")

            # Calculate SHA-256 hash and file size by streaming
            try:
                hasher = hashlib.sha256()
                response = client.get_object(bucket_name, object_key)
                file_size = calculate_file_size(obj)  # Use object metadata for size

                # Stream and hash the object content
                for chunk in response.stream(8192):  # Read in chunks of 8KB
                    hasher.update(chunk)
                file_hash = hasher.hexdigest()

                # Process content into lines for BreachedCredentials
                content = io.BytesIO()
                for chunk in response.stream(8192):
                    content.write(chunk)
                content.seek(0)  # Reset to start for reading lines
                lines = (line.decode("utf-8").strip() for line in content if line.strip())

                # Check if the file has already been processed (by sha256)
                try:
                    with transaction.atomic():
                        scrap_file, created = ScrapFile.objects.get_or_create(
                            sha256=file_hash,
                            defaults={
                                "name": object_key,  # Store the MinIO object key as the name
                                "size": file_size,
                            },
                        )
                        if not created and not force_reprocess:
                            logger.info(f"File {object_key} already processed... Not processing again.")
                            response.close()
                            continue
                        elif not created and force_reprocess:
                            logger.info(f"Forcing reprocess of {object_key}")
                            scrap_file.size = file_size  # Update size if reprocessing
                            scrap_file.save(update_fields=["size"])

                except IntegrityError as e:
                    logger.error(f"Database integrity error for file {object_key}: {e}")
                    response.close()
                    continue

                # Process lines into BreachedCredentials
                try:
                    for line in lines:
                        if not line:
                            continue
                        nested_lines = line_splitter(line, max_length=1024)  # Match BreachedCredential max_length
                        for nested_line in nested_lines:
                            lines_total += 1
                            try:
                                BreachedCredential.objects.create(
                                    string=nested_line,
                                    file=scrap_file,  # ForeignKey object
                                )
                                logger.debug(f"Created BreachedCredential for line: {nested_line}")
                            except (ValidationError, Exception) as e:
                                logger.error(f"Error saving line from {object_key}: {nested_line}, Error: {e}")
                                traceback.print_exc()
                except Exception as e:
                    logger.error(f"Error processing lines for {object_key}: {e}")
                    traceback.print_exc()

                response.close()  # Ensure the response is closed
                logger.info(f"Processed object: {object_key}")

            except Exception as e:
                logger.error(f"Critical error processing object {object_key}: {e}")
                traceback.print_exc()
                if 'response' in locals():
                    response.close()
                continue

        print(f"Total lines read: {lines_total}")
    except Exception as e:
        logger.error(f"Critical error in process_scrap_files: {e}")
        traceback.print_exc()
        raise