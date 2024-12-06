from minio import Minio
from django.db import IntegrityError, transaction
from webui.models import ScrapFile, BreachedCredential
from core.settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_ENDPOINT_URL
import hashlib
import os
import re

# MinIO Client
client = Minio(
    AWS_S3_ENDPOINT_URL,
    access_key=AWS_ACCESS_KEY_ID,
    secret_key=AWS_SECRET_ACCESS_KEY,
    secure=False
)

def process_scrap_files():
    bucket_name = "scraps"
    objects = client.list_objects(bucket_name, recursive=True)

    for obj in objects:
        local_file = f"/tmp/{os.path.basename(obj.object_name)}"
        try:
            # Download the file locally
            client.fget_object(bucket_name, obj.object_name, local_file)
        except Exception as e:
            print(f"Error downloading file {obj.object_name}: {e}")
            continue

        # Calculate file hash
        try:
            hasher = hashlib.sha256()
            with open(local_file, "rb") as file:
                while chunk := file.read(8192):  # Read in chunks of 8KB
                    hasher.update(chunk)
            file_hash = hasher.hexdigest()
        except Exception as e:
            print(f"Error calculating hash for file {obj.object_name}: {e}")
            os.remove(local_file)
            continue

        # Check if the file has already been processed
        try:
            with transaction.atomic():
                scrap_file = ScrapFile.objects.create(name=obj.object_name, hash=file_hash)
        except IntegrityError:
            print(f"File {obj.object_name} already processed.")
            os.remove(local_file)
            continue

        # Process the file content
        try:
            with open(local_file, "r") as file:
                for line in file:
                    line = line.strip()
                    if not re.match(r"^[^:]+:[^:]+$", line):  # Format validation
                        print(f"Skipping invalid line in file {obj.object_name}: {line}")
                        continue
                    try:
                        username, password = line.split(":")
                        BreachedCredential.objects.create(
                            username=username,
                            password=password,
                            file=scrap_file  # ForeignKey object
                        )
                    except Exception as e:
                        print(f"Error saving line from file {obj.object_name}: {line}, Error: {e}")
        except Exception as e:
            print(f"Error processing file {obj.object_name}: {e}")

        # Clean up the local file
        os.remove(local_file)
        print(f"Processed file: {obj.object_name}")
