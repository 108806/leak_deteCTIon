# Automatic Telegram File Synchronization

This document explains the automatic synchronization system for Telegram files.

## Overview

The system now includes an automatic daily synchronization of files from the Telegram downloader to the MinIO storage system. This ensures that any new files downloaded from Telegram channels are properly processed and indexed in the system.

## Components

1. **Django Management Command**: `sync_telegram_files.py`
   - Located at `/django/webui/management/commands/sync_telegram_files.py`
   - Scans the Telegram download directories for new files
   - Uploads new files to MinIO using the hash-based cache system
   - Can be run with `--force` to re-upload all files

2. **Daily Synchronization Script**: `sync_telegram_files.sh`
   - Located at the root of the project
   - Ensures that both the Telegram downloader and MinIO containers are running
   - Executes the Django management command
   - Triggers the processing of newly uploaded files
   - Logs all operations to the `logs/` directory

3. **Cron Job**
   - Runs the synchronization script once a day at 3:00 AM
   - Added via: `crontab -l | cat - /tmp/telegram_sync_cron | crontab -`

## Usage

### Manual Synchronization

To manually trigger the synchronization process:

```bash
./sync_telegram_files.sh
```

### Force Re-upload of All Files

To force re-upload all files, ignoring the hash cache:

```bash
docker exec django python manage.py sync_telegram_files --force
```

### Testing the Synchronization

A test script is provided to verify the synchronization process:

```bash
./test_telegram_sync.sh
```

This script runs the synchronization and then checks MinIO and the database for recently processed files.

## Troubleshooting

1. **Check Logs**: Synchronization logs are stored in the `logs/` directory with filenames like `telegram_sync_YYYYMMDD.log`.

2. **Check File Hash Cache**: The file hash cache is stored at `/usr/src/app/file_hashes.json` within the Django container. You can inspect it to see which files have been processed.

3. **Verify MinIO Contents**: Use the commands in the README.md to check the contents of the MinIO bucket.

4. **Manual Processing**: If needed, you can manually trigger the processing of files with `docker exec django python manage.py process_scrap`.

## Notes

- The system now handles files with spaces in their names by replacing spaces with underscores when uploading to MinIO.
- The synchronization process is idempotent - running it multiple times will not cause duplicate uploads due to the hash-based cache system.
- For large files, the system may take longer to process. Be patient and check the logs for progress.
