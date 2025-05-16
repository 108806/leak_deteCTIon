#!/bin/bash

# Script to sync Telegram files to MinIO
# This should be run once per day via cron

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Log file for capturing output
LOG_FILE="$SCRIPT_DIR/logs/telegram_sync_$(date +%Y%m%d).log"
mkdir -p "$SCRIPT_DIR/logs"

echo "=========================================" >> "$LOG_FILE"
echo "Starting Telegram file sync: $(date)" >> "$LOG_FILE"

# Check if containers are running
if ! docker ps | grep -q telegram-downloader; then
  echo "Telegram downloader container is not running. Starting it..." >> "$LOG_FILE"
  cd "$SCRIPT_DIR/telegram_downloader" && docker-compose up -d
fi

if ! docker ps | grep -q minio; then
  echo "MinIO container is not running. Starting main services..." >> "$LOG_FILE"
  cd "$SCRIPT_DIR" && docker-compose up -d
fi

# Run the sync command
echo "Running sync command..." >> "$LOG_FILE"
docker exec django python manage.py sync_telegram_files 2>&1 | tee -a "$LOG_FILE"

# Process any new files that were uploaded to MinIO
echo "Processing newly uploaded files..." >> "$LOG_FILE"
docker exec django python manage.py process_scrap 2>&1 | tee -a "$LOG_FILE"

echo "Telegram file sync completed: $(date)" >> "$LOG_FILE"
echo "=========================================" >> "$LOG_FILE"

echo "Sync completed. See log at $LOG_FILE"
