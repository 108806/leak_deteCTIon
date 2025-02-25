from minio import Minio
from django.db import IntegrityError, transaction
from webui.models import ScrapFile, BreachedCredential
from core.settings import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_S3_ENDPOINT_URL,
    AWS_STORAGE_BUCKET_NAME,
)
from pathlib import Path
import hashlib
import os
import re
import requests
import traceback, logging

logging.basicConfig(level=logging.ERROR)

# MinIO Client
client = Minio(
    AWS_S3_ENDPOINT_URL,
    access_key=AWS_ACCESS_KEY_ID,
    secret_key=AWS_SECRET_ACCESS_KEY,
    secure=False,
)


def process_scrap_files(force_reprocess=False):
    print("[*] Running process_scrap_files...")
    bucket_name = AWS_STORAGE_BUCKET_NAME
    objects = client.list_objects(bucket_name, recursive=True)
    LINES_TOTAL = 0

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
                global FILE_SIZE
                FILE_SIZE = str(file.tell() / 1024**2)[:10]  # Max size up to petabytes
            file_hash = hasher.hexdigest()
        except Exception as e:
            print(f"Error calculating hash for file {obj.object_name}: {e}")
            try:
                os.remove(local_file)
            except Exception as e2:
                print(e2)
                traceback.print_exc()

            continue

        # Check if the file has already been processed
        try:
            with transaction.atomic():
                scrap_file = ScrapFile.objects.create(
                    name=obj.object_name, sha256=file_hash, size=FILE_SIZE
                )
                del FILE_SIZE
        except IntegrityError:
            print(f"File {obj.object_name} already processed...")
            if not force_reprocess:
                print("... Not processing again.")
                os.remove(local_file)
                continue

        try:
            with open(local_file, "r", encoding="utf-8") as file:
                for line in file:

                    # print('\n[*] LINE:',IDX, line, 'FILE:', local_file)
                    if not line:
                        continue
                    line = line.strip()
                    if len(line) > 512:  # Edge Cases with file in file
                        nested_lines = line_splitter(line)
                        for nested_line in nested_lines:
                            LINES_TOTAL += 1
                            if len(nested_line) > 1024:
                                print("\n[*]line_splitter failed, line still > 1024.")
                            try:
                                BreachedCredential.objects.create(
                                    string=nested_line,
                                    file=scrap_file,  # ForeignKey object
                                )
                            except Exception as e:
                                print(
                                    f"Error saving line from file {obj.object_name}: {nested_line}, Error: {e}"
                                )
                                traceback.print_exc()
                    LINES_TOTAL += 1
                    try:
                        BreachedCredential.objects.create(
                            string=line,
                            file=scrap_file,  # ForeignKey object
                        )
                    except Exception as e:
                        print(
                            f"Error saving line from file {obj.object_name}: {line}, Error: {e}"
                        )
                        traceback.print_exc()
        except Exception as e:
            print(f"Error processing file {obj.object_name}: {e}")
            traceback.print_exc()
        # Clean up the local file
        os.remove(local_file)
        print(f"Processed file: {obj.object_name}")
    print("Total Lines read : ", LINES_TOTAL)


def extract_website(line):
    """
    Extracts a website URL from the given line using regex.
    Returns the website if found; otherwise, None.
    NOT USED CURRENTLY.
    """
    # Match HTTP or HTTPS URLs
    match = re.search(r"(https?://[^\s]+)", line)
    return match.group(1) if match else None


def tld_extract(line):
    """
    Shorten long links to just TLD. Returns a string.
    NOT USED CURRENTLY.
    """
    url, response, tlds = "", "", ""
    if not line:
        return ""
    line = line.split("://")[-1]  # Cut http(s):// or leave as it is
    try:
        tlds = open("tlds.txt", "r").read().split("\n")
    except Exception as e:
        print("TLD from .txt file failed, trying to obtain from url...", e)
        traceback.print_exc()
    if not tlds:
        try:
            url = "https://data.iana.org/TLD/tlds-alpha-by-domain.txt"
            response = requests.get(url, timeout=60)
            tlds = response.text.splitlines()
            print("Valid TLDS from url obtained:", len(tlds))
            if not os.path.isfile("tlds.txt"):
                with open("tlds.txt", "w+", encoding="utf-8") as f:
                    if len(tlds) > len(f.readlines()):
                        f.writelines(tlds)
        except Exception as e:
            print("TLD from url failed :", e)
            traceback.print_exc()

    invalids = "@ # ! $ % & * + = ^ ~ < >".split()
    regex = re.compile(r"([a-zA-Z0-9-]+\.){1,128}([a-zA-Z]){2,14}")
    match = regex.search(line)
    if match and not any(x in match.group(0) for x in invalids):
        potential_tld = match.group(2).lower()
        if potential_tld in tlds:
            return match.group(0)
    return ""


def line_splitter(lines: str) -> dict:
    """
    Multiple lines in one string handler.
    """
    print(f"Splitting {len(lines)} long line. Assumming nested...")
    map = []
    # site_regex = r'((?:[-a-zA-Z0-9@:%_\+.~#?&//=]+(?:\.[-a-zA-Z0-9@%_\+~#?&]+){2,63}))'

    # S E P A R A T O R S:
    TYPE_1 = "/:"  # DOMAIN:/USERNAME:PASSWORD
    TYPE_2 = "https://"  # LONG_LINK_WITH_LOTS_OF_SPECIALS USERNAME:PASSWORD"

    if lines.count(TYPE_1) > lines.count(TYPE_2):
        lines = lines.split(TYPE_1)
        for line in lines:
            line = line.replace("https://", "")
            line = line.replace("http://", "")
            map.append(line)
    else:
        lines = lines.split(TYPE_2)
        for line in lines:
            line = line.replace("https://", "")
            line = line.replace("http://", "")
            map.append(line)
    return map
