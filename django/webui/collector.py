from minio import Minio
from minio.error import S3Error
from core.settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME, AWS_S3_ENDPOINT_URL
import os

import traceback, logging
logging.basicConfig(level=logging.ERROR)

# Initialize MinIO Client
minio_client = Minio(
    AWS_S3_ENDPOINT_URL,
    access_key=AWS_ACCESS_KEY_ID,
    secret_key=AWS_SECRET_ACCESS_KEY,
    secure=False
)

TARGET_PATH = '/usr/share/Telegram-Files/'

def collect_and_upload_files(source_path=TARGET_PATH, bucket_name:str=AWS_STORAGE_BUCKET_NAME):
    
    ACCEPTED_FILETYPES = ['.txt', '.lst', '.json']

    try:
        # Check if the bucket exists, create if it doesn't
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)

        # Walk through the directory
        for root, _, files in os.walk(source_path):
            for file in files:
                print ('[*] Processing file: ', file)
                if any(file.endswith(x) for x in ACCEPTED_FILETYPES):
                    file_path = os.path.join(root, file)
                    object_name = os.path.relpath(file_path, source_path).replace(os.sep, '/')
                    
                    with open(file_path, 'rb') as data:
                        minio_client.put_object(
                            bucket_name,
                            object_name,
                            data,
                            length=os.path.getsize(file_path),
                            content_type='application/octet-stream'
                        )
                    print(f"[*] Uploaded {file_path} to bucket {bucket_name}")
                else:
                    print('[*] Not matched extension whitelist:', ACCEPTED_FILETYPES, "VS", file)
    except S3Error as e:
        print(f"[***] Error occurred: {e}")
    except Exception as e:
        print(f"[***] An unexpected error occurred: {e}")
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    collect_and_upload_files()