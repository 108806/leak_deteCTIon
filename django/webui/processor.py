from minio import Minio
from django.db import IntegrityError, transaction
from webui.models import ScrapFile, BreachedCredential
from core.settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_ENDPOINT_URL, AWS_STORAGE_BUCKET_NAME
from pathlib import Path
import hashlib
import os
import re
import requests
    

# MinIO Client
client = Minio(
    AWS_S3_ENDPOINT_URL,
    access_key=AWS_ACCESS_KEY_ID,
    secret_key=AWS_SECRET_ACCESS_KEY,
    secure=False
)

def process_scrap_files(force_reprocess=False):
    print('[*] Running process_scrap_files...')
    bucket_name = AWS_STORAGE_BUCKET_NAME
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
            print(f"File {obj.object_name} already processed...")
            if not force_reprocess:
                print("... Not processing again.")
                os.remove(local_file)
            continue

        # Process the file content
        try:
            with open(local_file, "r") as file:
                for line in file:        
                    line = line.strip()
                    # Extract website, username, and password
                    website = extract_website(line)
            
            # Remove website from the line for easier processing
            if website:
                line = line.replace(website, "").strip()
            
            if not re.match(r"^[^:]+:[^:]+$", line):  # Format validation
                print(f"Skipping invalid line in file {obj.object_name}: {line}")
                continue
            bad_comb0s = 0
            try:
                username, password = line.split(":")
                if username and password: # User & Password are required
                    BreachedCredential.objects.create(
                        username=username,
                        password=password,
                        file=scrap_file, # ForeignKey object
                        website=website # Website is optional
                    )
                else:
                    print('[*] ERROR: Combo not valid:', username, password, website)
                    bad_comb0s += 1
            except Exception as e:
                print(f"Error saving line from file {obj.object_name}: {line}, Error: {e}")

        except Exception as e:
            print(f"Error processing file {obj.object_name}: {e}")

        # Clean up the local file
        os.remove(local_file)
        print(f"Processed file: {obj.object_name}")
        print(f"Bad data format: {bad_comb0s}\n")


def extract_website(line):
    """
    Extracts a website URL from the given line using regex.
    Returns the website if found; otherwise, None.
    """
    # Match HTTP or HTTPS URLs
    match = re.search(r'(https?://[^\s]+)', line)
    return match.group(1) if match else None

def tld_extract(line):
    """
    Shorten long links to just TLD. Returns a string.
    """
    url, response, tlds = ''
    try:
        url = 'https://data.iana.org/TLD/tlds-alpha-by-domain.txt'
        response = requests.get(url)
        tlds = response.text.splitlines()
        if not os.path.isfile('tlds.txt'):
            with open('tlds.txt', 'w+') as f:
                if len(tlds) > len(f.readlines()):
                    f.writelines(tlds)
    except Exception as E:
        print('TLD from url failed :', E)

    try:
        tlds = open('tlds.txt', 'ra+').read().split('\n')
    except Exception as E:
        print('TLD from .txt file failed', )
    
    invalids = '@ # ! $ % & * + = ^ ~ < >'.split()
    regex = re.compile(r'([a-zA-Z0-9-]+\.){1,128}([a-zA-Z]){2,14}')
    match = regex.search(line)
    if match and not any(x in match.group(0) for x in invalids):
        potential_tld = match.group(2).lower()
        if potential_tld in tlds:
            return match.group(0)
    return ''