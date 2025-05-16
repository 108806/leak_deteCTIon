#!/bin/bash

# Script to test the Telegram file sync functionality

echo "Testing Telegram file sync..."

# Run the sync script
/mnt/encrypted/leak_deteCTIon/sync_telegram_files.sh

# Check the results
echo "Checking MinIO for recently uploaded files..."
cd /mnt/encrypted/leak_deteCTIon && docker exec -it minio find /data/breached-credentials -type f -exec stat --format="%y %n" {} \; | sort -r | head -5

echo "Checking for recent files processed in the database..."
docker exec -it django python manage.py shell -c "from webui.models import ScrapFile; [print(f'{f.name}: Added {f.added_at}, Credentials: {f.count:,}') for f in ScrapFile.objects.order_by('-added_at')[:5]]"

echo "Test completed."
