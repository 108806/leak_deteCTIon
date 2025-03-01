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

logger = logging.getLogger(__name__)

def calculate_file_size(obj: Object) -> str:
    size_bytes = obj.size
    return f"{size_bytes / (1024 ** 2):.2f}"

def line_splitter(line: str, max_length: int = 1024) -> list[str]:
    if len(line) <= max_length:
        return [line]
    chunks = []
    while line:
        chunk = line[:max_length].rsplit(" ", 1)[0] if " " in line[:max_length] else line[:max_length]
        chunks.append(chunk)
        line = line[len(chunk):].lstrip()
    return chunks

def detect_encoding(data: bytes) -> str:
    result = chardet.detect(data)
    return result['encoding'] if result['encoding'] else 'utf-8'

def process_file_metadata(object_key: str, obj: Object, file_hash: str, expected_lines: int, force_reprocess: bool = False) -> ScrapFile:
    file_size = calculate_file_size(obj)
    with transaction.atomic():
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

class SkipFileException(Exception):
    pass

def process_scrap_files(force_reprocess: bool = False, batch_size: int = 10) -> None:
    print("[*] Running process_scrap_files...")
    client = Minio(
        AWS_S3_ENDPOINT_URL,
        access_key=AWS_ACCESS_KEY_ID,
        secret_key=AWS_SECRET_ACCESS_KEY,
        secure=False,
    )
    bucket_name = AWS_STORAGE_BUCKET_NAME
    lines_total = 0

    # Load hash cache
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
        hash_cache = {}

    try:
        if not client.bucket_exists(bucket_name):
            logger.warning(f"Bucket {bucket_name} does not exist, nothing to process.")
            print(f"[*] Bucket {bucket_name} does not exist, nothing to process.")
            return

        objects = client.list_objects(bucket_name, recursive=True)
        objects_list = list(objects)

        if not objects_list:
            logger.info(f"No objects found in bucket {bucket_name}, nothing to process.")
            print(f"[*] No objects found in bucket {bucket_name}, nothing to process.")
            return

        logger.info(f"Found {len(objects_list)} objects in bucket {bucket_name}")
        print(f"[*] Found {len(objects_list)} objects in bucket {bucket_name}")
        print(f"[*] Initial ScrapFile count: {ScrapFile.objects.count()}")

        for obj in objects_list:
            object_key = obj.object_name
            logger.info(f"Processing MinIO object: {object_key}")
            print(f"[*] Processing MinIO object: {object_key}")

            start_time = time.time()
            lines_processed = 0
            first_five_lines = []
            credential_objects = []

            # Check cache and compute hash if needed
            cached_hash = hash_cache.get(object_key)
            hasher = hashlib.sha256()
            response = client.get_object(bucket_name, object_key)
            content_buffer = b""

            initial_chunk = next(response.stream(131072))  # 128 KB chunk
            hasher.update(initial_chunk)
            encoding = detect_encoding(initial_chunk)
            content_buffer += initial_chunk

            io_start = time.time()
            for chunk in response.stream(131072):
                hasher.update(chunk)
                content_buffer += chunk

                while b'\n' in content_buffer:
                    line, content_buffer = content_buffer.split(b'\n', 1)
                    if line.strip():
                        decoded_line = line.decode(encoding, errors="ignore").strip()
                        if lines_processed < 5:
                            first_five_lines.append(decoded_line)
                        nested_lines = line_splitter(decoded_line)
                        lines_processed += len(nested_lines)
                        lines_total += len(nested_lines)
                        credential_objects.extend(
                            BreachedCredential(string=nested_line) for nested_line in nested_lines
                        )

            if content_buffer.strip():
                decoded_line = content_buffer.decode(encoding, errors="ignore").strip()
                if lines_processed < 5 and len(first_five_lines) < 5:
                    first_five_lines.append(decoded_line)
                nested_lines = line_splitter(decoded_line)
                lines_processed += len(nested_lines)
                lines_total += len(nested_lines)
                credential_objects.extend(
                    BreachedCredential(string=nested_line) for nested_line in nested_lines
                )

            io_end = time.time()
            print(f"[*] IO time: {io_end - io_start:.2f} s")

            # Determine ScrapFile before batches
            file_hash = cached_hash if cached_hash else hasher.hexdigest()
            if cached_hash:
                print(f"[*] Loaded hash from cache: {cached_hash}")
            try:
                scrap_file = process_file_metadata(object_key, obj, file_hash=file_hash, expected_lines=lines_processed, force_reprocess=force_reprocess)
            except SkipFileException:
                elapsed_time = time.time() - start_time
                processed_size_mb = obj.size / (1024 ** 2)
                speed_mb_s = processed_size_mb / elapsed_time if elapsed_time > 0 else 0.0
                print(f"[*] Speed: {speed_mb_s:.2f} MB/s for {object_key} ({processed_size_mb:.2f} MB in {elapsed_time:.2f} s) - Skipped")
                print(f"[*] First 5 lines of {object_key}: {first_five_lines if first_five_lines else 'None'}")
                scrap_file.refresh_from_db()
                actual_count = BreachedCredential.objects.filter(file=scrap_file).count()
                print(f"[*] Actual DB count for {object_key}: {actual_count}")
                with transaction.atomic():
                    ScrapFile.objects.filter(id=scrap_file.id).update(count=actual_count)
                    scrap_file.refresh_from_db()
                print(f"[*] Updated count for {object_key}: {scrap_file.count}")
                count_end = time.time()
                print(f"[*] Count update time: {count_end - io_end:.2f} s")
                print(f"[*] Processed {lines_processed} lines in {object_key}")
                response.close()
                print(f"[*] Processed object: {object_key}")
                continue

            # Process batches
            db_start = time.time()
            while credential_objects:
                batch = credential_objects[:batch_size]
                with transaction.atomic():
                    for cred in batch:
                        cred.file = scrap_file
                    BreachedCredential.objects.bulk_create(
                        batch, batch_size=batch_size, ignore_conflicts=True
                    )
                credential_objects = credential_objects[batch_size:]

            db_end = time.time()
            print(f"[*] DB time: {db_end - db_start:.2f} s")

            # Update hash and cache
            new_hash = hasher.hexdigest()
            if not cached_hash or cached_hash != new_hash:
                with transaction.atomic():
                    scrap_file.sha256 = new_hash
                    scrap_file.save(update_fields=['sha256'])
                hash_cache[object_key] = new_hash
                print(f"[*] Updated hash cache for {object_key} with hash {new_hash}")

            elapsed_time = time.time() - start_time
            processed_size_mb = obj.size / (1024 ** 2)
            speed_mb_s = processed_size_mb / elapsed_time if elapsed_time > 0 else 0.0
            print(f"[*] Speed: {speed_mb_s:.2f} MB/s for {object_key} ({processed_size_mb:.2f} MB in {elapsed_time:.2f} s)")
            print(f"[*] First 5 lines of {object_key}: {first_five_lines if first_five_lines else 'None'}")

            scrap_file.refresh_from_db()
            actual_count = BreachedCredential.objects.filter(file=scrap_file).count()
            print(f"[*] Actual DB count for {object_key}: {actual_count}")

            # Inline count update since models.py not changed
            with transaction.atomic():
                ScrapFile.objects.filter(id=scrap_file.id).update(count=actual_count)
                scrap_file.refresh_from_db()
            print(f"[*] Updated count for {object_key}: {scrap_file.count}")

            count_end = time.time()
            print(f"[*] Count update time: {count_end - db_end:.2f} s")
            print(f"[*] Processed {lines_processed} lines in {object_key}")

            response.close()
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