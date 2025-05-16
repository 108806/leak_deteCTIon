from minio import Minio
from minio.error import S3Error
from core.settings import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_STORAGE_BUCKET_NAME,
    AWS_S3_ENDPOINT_URL,
)
import os
import hashlib
import json
import logging
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize MinIO Client
minio_client = Minio(
    AWS_S3_ENDPOINT_URL,
    access_key=AWS_ACCESS_KEY_ID,
    secret_key=AWS_SECRET_ACCESS_KEY,
    secure=False,
)

# Define paths
TARGET_PATHS = ["/usr/share/Telegram-Files/", "/usr/share/combos"]
HASH_CACHE_FILE = "/usr/src/app/file_hashes.json"

def load_hash_cache() -> dict:
    """Load the hash cache from the JSON file, or return an empty dict if it doesn't exist."""
    try:
        if os.path.exists(HASH_CACHE_FILE):
            with open(HASH_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Failed to load hash cache from {HASH_CACHE_FILE}: {e}")
        return {}

def save_hash_cache(hash_cache: dict) -> None:
    """Save the hash cache to the JSON file."""
    try:
        with open(HASH_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(hash_cache, f, indent=4)
        logger.info(f"Saved hash cache to {HASH_CACHE_FILE}")
    except Exception as e:
        logger.error(f"Failed to save hash cache to {HASH_CACHE_FILE}: {e}")

def calculate_file_hash(file_path: str) -> str:
    """Calculate the SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):  # Read in 8KB chunks
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def collect_and_upload_files(
    source_paths=TARGET_PATHS, bucket_name: str = AWS_STORAGE_BUCKET_NAME
):
    """
    Collect files from source paths and upload them to MinIO, skipping duplicates based on SHA-256 hash using a local JSON cache.

    Args:
        source_paths (list): List of directories to scan for files.
        bucket_name (str): MinIO bucket to upload files to.
    """
    ACCEPTED_FILETYPES = [".txt", ".lst", ".json"]

    # Load the hash cache
    hash_cache = load_hash_cache()
    uploaded_files = set(hash_cache.keys())  # Set of file paths already processed

    try:
        # Check if the bucket exists, create if it doesn't
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
            logger.info(f"Created bucket: {bucket_name}")
        else:
            logger.info(f"Bucket {bucket_name} already exists")

        for source_path in source_paths:
            if not os.path.exists(source_path):
                logger.warning(f"Source path {source_path} does not exist, skipping...")
                continue

            logger.info(f"Starting to process the files in: {source_path}")
            # Walk through the directories
            for root, _, files in os.walk(source_path):
                for file in files:
                    logger.info(f"Processing file: {file}")
                    if any(file.endswith(x) for x in ACCEPTED_FILETYPES):
                        file_path = os.path.join(root, file)
                        # Handle file paths with spaces for MinIO upload
                        object_name = os.path.relpath(file_path, source_path).replace(
                            os.sep, "/"
                        )
                        # Replace spaces with underscores in the object name for MinIO compatibility
                        object_name = object_name.replace(" ", "_")

                        # Check if the file path is already in the cache
                        if file_path in uploaded_files:
                            logger.info(
                                f"File {file_path} already uploaded to bucket {bucket_name}, "
                                f"skipping upload."
                            )
                            continue

                        # Calculate the SHA-256 hash of the local file
                        try:
                            file_hash = calculate_file_hash(file_path)
                            logger.debug(f"Calculated hash for {file_path}: {file_hash}")
                        except Exception as e:
                            logger.error(f"Failed to calculate hash for {file_path}: {e}")
                            continue

                        # Check if a file with the same hash has already been uploaded
                        if file_hash in hash_cache.values():
                            logger.info(
                                f"File with hash {file_hash} already uploaded to bucket {bucket_name}, "
                                f"skipping upload: {file_path}"
                            )
                            # Still add to cache to avoid recomputing hash in future runs
                            hash_cache[file_path] = file_hash
                            uploaded_files.add(file_path)
                            save_hash_cache(hash_cache)
                            continue

                        # Upload the file to MinIO
                        try:
                            with open(file_path, "rb") as data:
                                minio_client.put_object(
                                    bucket_name,
                                    object_name,
                                    data,
                                    length=os.path.getsize(file_path),
                                    content_type="application/octet-stream",
                                )
                            logger.info(f"Uploaded {file_path} to bucket {bucket_name} as {object_name}")
                            # Mark the file as uploaded
                            hash_cache[file_path] = file_hash
                            uploaded_files.add(file_path)
                            save_hash_cache(hash_cache)
                        except S3Error as e:
                            logger.error(f"S3Error while uploading {file_path}: {e}")
                        except Exception as e:
                            logger.error(f"Error uploading {file_path}: {e}")
                            traceback.print_exc()
                    else:
                        logger.info(
                            f"Not matched extension whitelist: {ACCEPTED_FILETYPES} VS {file}"
                        )
    except S3Error as e:
        logger.error(f"S3Error occurred: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    collect_and_upload_files()