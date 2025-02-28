from core.settings import AWS_STORAGE_BUCKET_NAME, AWS_S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from webui.models import ScrapFile, BreachedCredential
from minio import Minio
from minio.error import S3Error
from minio.datatypes import Object
import hashlib
import logging
import io
import traceback

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
        # Check if the bucket exists
        if not client.bucket_exists(bucket_name):
            logger.warning(f"Bucket {bucket_name} does not exist, nothing to process.")
            print(f"[*] Bucket {bucket_name} does not exist, nothing to process.")
            return

        # List objects in bucket
        objects = client.list_objects(bucket_name, recursive=True)
        objects_list = list(objects)  # Convert iterator to list for debugging

        if not objects_list:
            logger.info(f"No objects found in bucket {bucket_name}, nothing to process.")
            print(f"[*] No objects found in bucket {bucket_name}, nothing to process.")
            return

        logger.info(f"Found {len(objects_list)} objects in bucket {bucket_name}")
        print(f"[*] Found {len(objects_list)} objects in bucket {bucket_name}")

        for obj in objects_list:
            object_key = obj.object_name
            logger.info(f"Processing MinIO object: {object_key}")
            print(f"[*] Processing MinIO object: {object_key}")

            # Stream the entire object content into memory once
            try:
                response = client.get_object(bucket_name, object_key)
                content = io.BytesIO()
                for chunk in response.stream(8192):
                    content.write(chunk)
                content.seek(0)  # Reset to start

                # Calculate SHA-256 hash
                hasher = hashlib.sha256()
                content.seek(0)  # Rewind to start for hashing
                for chunk in iter(lambda: content.read(8192), b""):
                    hasher.update(chunk)
                file_hash = hasher.hexdigest()
                logger.debug(f"Calculated hash for {object_key}: {file_hash}")

                # Calculate file size
                file_size = calculate_file_size(obj)

                # Check if the file has already been processed (by sha256)
                try:
                    with transaction.atomic():
                        scrap_file, created = ScrapFile.objects.get_or_create(
                            sha256=file_hash,
                            defaults={
                                "name": object_key,
                                "size": file_size,
                            },
                        )
                        if not created and not force_reprocess:
                            logger.info(f"File {object_key} already processed... Not processing again.")
                            print(f"[*] File {object_key} already processed... Not processing again.")
                            response.close()
                            continue
                        elif not created and force_reprocess:
                            logger.info(f"Forcing reprocess of {object_key}")
                            print(f"[*] Forcing reprocess of {object_key}")
                            scrap_file.size = file_size
                            scrap_file.save(update_fields=["size"])

                except IntegrityError as e:
                    logger.error(f"Database integrity error for file {object_key}: {e}")
                    response.close()
                    continue

                # Process lines into BreachedCredentials
                try:
                    content.seek(0)  # Rewind to start for reading lines
                    lines = (line.decode("utf-8").strip() for line in content if line.strip())
                    lines_list = list(lines)  # Convert to list for debugging
                    logger.info(f"Found {len(lines_list)} lines in {object_key}")
                    print(f"[*] Found {len(lines_list)} lines in {object_key}")

                    if not lines_list:
                        logger.warning(f"No non-empty lines found in {object_key}, skipping...")
                        print(f"[*] No non-empty lines found in {object_key}, skipping...")
                        response.close()
                        continue

                    for line in lines_list:
                        if not line:
                            continue
                        nested_lines = line_splitter(line, max_length=1024)
                        for nested_line in nested_lines:
                            lines_total += 1
                            try:
                                BreachedCredential.objects.create(
                                    string=nested_line,
                                    file=scrap_file,
                                )
                                logger.debug(f"Created BreachedCredential for line: {nested_line}")
                            except (ValidationError, Exception) as e:
                                logger.error(f"Error saving line from {object_key}: {nested_line}, Error: {e}")
                                traceback.print_exc()
                except Exception as e:
                    logger.error(f"Error processing lines for {object_key}: {e}")
                    traceback.print_exc()

                response.close()
                logger.info(f"Processed object: {object_key}")
                print(f"[*] Processed object: {object_key}")

            except S3Error as e:
                logger.error(f"S3Error processing object {object_key}: {e}")
                print(f"[***] S3Error processing object {object_key}: {e}")
                if 'response' in locals():
                    response.close()
                continue
            except Exception as e:
                logger.error(f"Critical error processing object {object_key}: {e}")
                print(f"[***] Critical error processing object {object_key}: {e}")
                traceback.print_exc()
                if 'response' in locals():
                    response.close()
                continue

        print(f"Total lines read: {lines_total}")
    except S3Error as e:
        logger.error(f"S3Error in process_scrap_files: {e}")
        print(f"[***] S3Error in process_scrap_files: {e}")
        traceback.print_exc()
        raise
    except Exception as e:
        logger.error(f"Critical error in process_scrap_files: {e}")
        print(f"[***] Critical error in process_scrap_files: {e}")
        traceback.print_exc()
        raise