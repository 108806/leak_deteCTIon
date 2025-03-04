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
import chardet
import time
import json
import os
import psutil  # Dodaj do requirements.txt: psutil==5.9.8
from django_q.tasks import async_task

logger = logging.getLogger(__name__)

def calculate_file_size(obj: Object) -> str:
    size_bytes = obj.size
    return f"{size_bytes / (1024 ** 2):.2f}"

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

def detect_encoding(data: bytes) -> str:
    result = chardet.detect(data)
    return result['encoding'] if result['encoding'] else 'utf-8'

def process_file_metadata(object_key: str, obj: Object, file_hash: str, expected_lines: int, force_reprocess: bool = False) -> ScrapFile:
    file_size = calculate_file_size(obj)
    with transaction.atomic():
        try:
            scrap_file, created = ScrapFile.objects.get_or_create(
                sha256=file_hash,
                defaults={"name": object_key, "size": file_size},
            )
            if not created:
                if force_reprocess:
                    logger.info(f"Forcing reprocess of {object_key} with hash {file_hash}")
                    print(f"[*] Forcing reprocess of {object_key} with hash {file_hash}")
                    scrap_file.breached_credentials.all().delete()
                    scrap_file.size = file_size
                    scrap_file.save(update_fields=["size"])
                elif scrap_file.count >= expected_lines:
                    logger.info(f"File {object_key} with hash {file_hash} already fully processed (count: {scrap_file.count})... Not processing again.")
                    print(f"[*] File {object_key} with hash {file_hash} already fully processed (count: {scrap_file.count})... Not processing again.")
                    raise SkipFileException()
                else:
                    logger.info(f"File {object_key} partially processed (count: {scrap_file.count} < {expected_lines}), continuing processing")
                    print(f"[*] File {object_key} partially processed (count: {scrap_file.count} < {expected_lines}), continuing processing")
            return scrap_file
        except IntegrityError as e:
            logger.warning(f"IntegrityError for {object_key} with hash {file_hash}: {str(e)}. Attempting to fetch existing ScrapFile.")
            scrap_file = ScrapFile.objects.get(sha256=file_hash)
            if scrap_file.count >= expected_lines and not force_reprocess:
                logger.info(f"File {object_key} already fully processed (count: {scrap_file.count})... Skipping.")
                print(f"[*] File {object_key} already fully processed (count: {scrap_file.count})... Skipping.")
                raise SkipFileException()
            return scrap_file

class SkipFileException(Exception):
    pass

def process_scrap_files(force_reprocess: bool = False, batch_size: int = 1000) -> None:
    print("[*] Running process_scrap_files...")
    client = Minio(AWS_S3_ENDPOINT_URL, access_key=AWS_ACCESS_KEY_ID, secret_key=AWS_SECRET_ACCESS_KEY, secure=False)
    bucket_name = AWS_STORAGE_BUCKET_NAME
    lines_total = 0

    HASH_CACHE_FILE = "/usr/src/app/file_hashes.json"
    hash_cache = {}
    try:
        if os.path.exists(HASH_CACHE_FILE):
            with open(HASH_CACHE_FILE, "r", encoding="utf-8") as f:
                hash_cache = json.load(f)
            print(f"[*] Loaded hash cache with {len(hash_cache)} entries")
        else:
            print(f"[*] No hash cache file found at {HASH_CACHE_FILE}, starting fresh")
    except Exception as e:
        logger.error(f"Error loading hash cache: {e}")
        print(f"[***] Error loading hash cache: {e}")

    try:
        if not client.bucket_exists(bucket_name):
            logger.warning(f"Bucket {bucket_name} does not exist, nothing to process.")
            print(f"[*] Bucket {bucket_name} does not exist, nothing to process.")
            return

        objects_list = list(client.list_objects(bucket_name, recursive=True))
        if not objects_list:
            logger.info(f"No objects found in bucket {bucket_name}, nothing to process.")
            print(f"[*] No objects found in bucket {bucket_name}, nothing to process.")
            return

        print(f"[*] Found {len(objects_list)} objects in bucket {bucket_name}")
        print(f"[*] Initial ScrapFile count: {ScrapFile.objects.count()}")

        for obj in objects_list:
            object_key = obj.object_name
            logger.info(f"Processing MinIO object: {object_key}")
            print(f"[*] Processing MinIO object: {object_key}")

            # Pomiar wolnej pamięci
            memory = psutil.virtual_memory()
            free_memory_mb = memory.available / (1024 ** 2)
            print(f"[*] Free memory before processing {object_key}: {free_memory_mb:.2f} MB")
            if free_memory_mb < 500:
                logger.warning(f"Low memory warning for {object_key}: {free_memory_mb:.2f} MB free")
                print(f"[*] WARNING: Low memory ({free_memory_mb:.2f} MB free), proceeding with caution")

            start_time = time.time()
            lines_processed = 0
            first_five_lines = []
            credential_objects = []
            batch_counter = 0
            total_db_time = 0.0  # Sumaryczny czas DB

            cached_hash = hash_cache.get(object_key)
            hasher = hashlib.sha256()
            response = client.get_object(bucket_name, object_key)
            content_buffer = b""

            initial_chunk = next(response.stream(262144))
            hasher.update(initial_chunk)
            encoding = detect_encoding(initial_chunk)
            content_buffer += initial_chunk

            # Oblicz hash i pobierz scrap_file przed przetwarzaniem
            io_start = time.time()
            for chunk in response.stream(262144):
                hasher.update(chunk)
            file_hash = hasher.hexdigest() if not cached_hash else cached_hash
            try:
                scrap_file = process_file_metadata(object_key, obj, file_hash, lines_processed, force_reprocess)
            except SkipFileException:
                elapsed_time = time.time() - start_time
                processed_size_mb = obj.size / (1024 ** 2)
                speed_mb_s = processed_size_mb / elapsed_time if elapsed_time > 0 else 0.0
                print(f"[*] Speed: {speed_mb_s:.2f} MB/s for {object_key} ({processed_size_mb:.2f} MB in {elapsed_time:.2f} s) - Skipped")
                print(f"[*] First 5 lines of {object_key}: {[f'{line[:50]}... ({len(line)} chars)' for line in first_five_lines[:5]]}")
                response.close()
                continue

            # Reset hasher i ponownie przetwarzaj plik
            hasher = hashlib.sha256()
            response = client.get_object(bucket_name, object_key)
            content_buffer = b""
            initial_chunk = next(response.stream(262144))
            hasher.update(initial_chunk)
            content_buffer += initial_chunk

            for chunk in response.stream(262144):
                hasher.update(chunk)
                content_buffer += chunk
                content_buffer = content_buffer.replace(b'\r\n', b'\n').replace(b'\r', b'\n')

                while b'\n' in content_buffer:
                    line, content_buffer = content_buffer.split(b'\n', 1)
                    if line.strip():
                        decoded_line = line.decode(encoding, errors="ignore").strip().replace('\x00', '')
                        if len(decoded_line) > 1024:
                            print(f"[*] Long line detected: {len(decoded_line)} chars")
                            logger.info(f"Long line: {decoded_line[:50]}... ({len(decoded_line)} chars)")
                        if lines_processed < 5:
                            first_five_lines.append(decoded_line)
                        nested_lines = line_splitter(decoded_line)
                        if len(nested_lines) > 1:
                            print(f"[*] Split {len(decoded_line)} chars into {len(nested_lines)} parts")
                        lines_processed += len(nested_lines)
                        lines_total += len(nested_lines)
                        credential_objects.extend(
                            BreachedCredential(string=nested_line, file=None)
                            for nested_line in nested_lines
                        )

                        if len(credential_objects) >= batch_size:
                            try:
                                db_start = time.time()
                                with transaction.atomic():
                                    logger.info(f"Assigning ScrapFile {scrap_file.id} to {len(credential_objects)} credentials")
                                    for cred in credential_objects:
                                        cred.file = scrap_file
                                    logger.info(f"Starting bulk_create for batch {batch_counter + 1}")
                                    BreachedCredential.objects.bulk_create(credential_objects, batch_size=batch_size, ignore_conflicts=True)
                                    logger.info(f"Completed bulk_create for batch {batch_counter + 1}")
                                batch_counter += 1
                                total_db_time += time.time() - db_start
                                credential_objects = []
                            except Exception as e:
                                logger.error(f"Error in bulk_create for {object_key}, batch {batch_counter + 1}: {str(e)}", exc_info=True)
                                raise

            if content_buffer.strip():
                decoded_line = content_buffer.decode(encoding, errors="ignore").strip().replace('\x00', '')
                if len(decoded_line) > 1024:
                    print(f"[*] Long line detected: {len(decoded_line)} chars")
                    logger.info(f"Long line: {decoded_line[:50]}... ({len(decoded_line)} chars)")
                if lines_processed < 5 and len(first_five_lines) < 5:
                    first_five_lines.append(decoded_line)
                nested_lines = line_splitter(decoded_line)
                if len(nested_lines) > 1:
                    print(f"[*] Split {len(decoded_line)} chars into {len(nested_lines)} parts")
                lines_processed += len(nested_lines)
                lines_total += len(nested_lines)
                credential_objects.extend(
                    BreachedCredential(string=nested_line, file=None)
                    for nested_line in nested_lines
                )

            if credential_objects:
                try:
                    db_start = time.time()
                    with transaction.atomic():
                        logger.info(f"Assigning ScrapFile {scrap_file.id} to {len(credential_objects)} credentials")
                        for cred in credential_objects:
                            cred.file = scrap_file
                        logger.info(f"Starting bulk_create for final batch {batch_counter + 1}")
                        BreachedCredential.objects.bulk_create(credential_objects, batch_size=batch_size, ignore_conflicts=True)
                        logger.info(f"Completed bulk_create for final batch {batch_counter + 1}")
                    total_db_time += time.time() - db_start
                except Exception as e:
                    logger.error(f"Error in bulk_create for {object_key}, final batch {batch_counter + 1}: {str(e)}", exc_info=True)
                    raise

            io_end = time.time()
            print(f"[*] IO time: {io_end - io_start:.2f} s")
            print(f"[*] Total DB time for {object_key}: {total_db_time:.2f} s")
            print(f"[*] First 5 lines of {object_key}: {[f'{line[:50]}... ({len(line)} chars)' for line in first_five_lines[:5]]}")

            if cached_hash:
                print(f"[*] Loaded hash from cache: {cached_hash}")
            file_hash = hasher.hexdigest()

            new_hash = hasher.hexdigest()
            if not cached_hash or cached_hash != new_hash:
                with transaction.atomic():
                    scrap_file.sha256 = new_hash
                    scrap_file.count = lines_processed
                    scrap_file.save(update_fields=['sha256', 'count'])
                hash_cache[object_key] = new_hash
                print(f"[*] Updated hash cache for {object_key} with hash {new_hash}")
            else:
                with transaction.atomic():
                    scrap_file.count = lines_processed
                    scrap_file.save(update_fields=['count'])

            try:
                async_task('webui.tasks.index_breached_credential', scrap_file.id)
                print(f"[*] Queued Elasticsearch indexing for ScrapFile {scrap_file.id}")
            except Exception as e:
                logger.error(f"Failed to queue Elasticsearch indexing: {e}")
                print(f"[***] Failed to queue Elasticsearch indexing: {e}")

            response.close()
            elapsed_time = time.time() - start_time
            processed_size_mb = obj.size / (1024 ** 2)
            speed_mb_s = processed_size_mb / elapsed_time if elapsed_time > 0 else 0.0
            print(f"[*] Speed: {speed_mb_s:.2f} MB/s for {object_key} ({processed_size_mb:.2f} MB in {elapsed_time:.2f} s)")
            print(f"[*] Processed {lines_processed} lines in {object_key}")
            logger.info(f"Processed object: {object_key}")
            print(f"[*] Processed object: {object_key}")

        with open(HASH_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(hash_cache, f, indent=4)
        print(f"[*] Saved updated hash cache with {len(hash_cache)} entries")
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
    finally:
        with open(HASH_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(hash_cache, f, indent=4)
        print(f"[*] Saved hash cache on exit with {len(hash_cache)} entries")

if __name__ == "__main__":
    process_scrap_files(batch_size=1000)