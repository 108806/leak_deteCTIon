leak-deteCTIon

Simple, clear and secure CTI for local usage.

## Stack:
Docker, Elasticsearch, Postgres, Python, Django

## Features:
- Fast and flexible credential search capabilities
- Multiple search query types for different use cases
- Performance benchmarking and analysis
- Pattern detection in breached credentials

## Plugins to do:
Telegram, Webscrapper


## Search Credentials

The system includes a powerful credential search tool with multiple query types:

```bash
# Basic search with all query types
docker exec -it django python manage.py search_credentials frost

# Search with specific query type
docker exec -it django python manage.py search_credentials frost --regexp

# Search with output options
docker exec -it django python manage.py search_credentials frost --output results --format json

# Field-specific search
docker exec -it django python manage.py search_credentials admin --field username

# Email-only search
docker exec -it django python manage.py search_credentials gmail --email-only --regexp
```

For complete search documentation, see `django/webui/management/commands/SEARCH_GUIDE.md`

## Mighty dev commands:

#CHECK THE ES DATA
docker exec -it qcluster curl http://elastic:9200 

#REBUILD INDEX
docker exec -it django python manage.py search_index --rebuild 

#FORCE PROCESSING SCRAP
docker exec -it django python manage.py process_scrap --force 

#CHECK THE ES FOR THE GIVEN SUBSTRING WITH CURL:
docker exec -it django curl -X POST "http://elastic:9200/breached_credentials/_search?pretty" -H "Content-Type: application/json" -d '{"query": {"query_string": {"query": "de"
}}}'


#CHECK THE NUMBER OF ALL RECORDS INDEXED IN THE ELASTIC SEARCH 
docker exec -it django curl -X GET "http://elastic:9200/breached_credentials/_count?pretty" -H "Content-Type: application/json" -d '{"query": {"match_all": {}}}'

#ES Rebuild index
python manage.py search_index --rebuild -f

#BAN SOME IP 
sudo fail2ban-client set <jail> unbanip <IP>

#UNBAN 
sudo fail2ban-client set sshd unbanip 192.168.1.100


#GIT REMOTE setup
git remote set-url origin git@github.com:108806/leak_deteCTIon.git
git remote set-url origin https://YOUR_GITHUB_USERNAME:YOUR_PERSONAL_ACCESS_TOKEN@github.com/108806/leak_deteCTIon.git

#MINIO CHECK THE DATA:
docker exec -it django python manage.py shell -c "from minio import Minio; from django.conf import settings; client = Minio('minio:9000', access_key=settings.AWS_ACCESS_KEY_ID, secret_key=settings.AWS_SECRET_ACCESS_KEY, secure=False); print('Directory sizes:'); [print(f'{obj.object_name}: {sum(o.size for o in client.list_objects(\"breached-credentials\", prefix=obj.object_name)) / (1024*1024*1024):.2f} GB') for obj in client.list_objects('breached-credentials')]"


#CHECK THE INDEXING OP IN PROGRESS
$ docker exec -it django python manage.py shell -c "from django_q.models import Task; [print(f'Task {t.id}: {t.func} - Started: {t.started}, Finished: {t.stopped}, Success: {t.success}') for t in Task.objects.filter(stopped__isnull=False).order_by('-stopped')[:5]]"


#CHECK WHAT FILES WERE PROCESSED DURING THE LAST INDEXING
$ docker exec -it django python manage.py shell -c "from webui.models import ScrapFile; [print(f'{f.name}: Added {f.added_at}, Credentials: {f.count:,}') for f in ScrapFile.objects.order_by('-added_at')[:5]]"



#CHECK THE PROCESSING SPEED
docker exec -it django python manage.py shell -c "from webui.models import BreachedCredential; from django.utils import timezone; from datetime import timedelta; now=timezone.now(); before=now-timedelta(minutes=10); count_before=BreachedCredential.objects.filter(added_at__lt=before).count(); count_now=BreachedCredential.objects.count(); print(f'Credentials processed in last 10 minutes: {count_now-count_before:,}\nProcessing rate: {(count_now-count_before)/10:,.0f} credentials/minute')"

# FIX FILE SIZES (one-time fix for existing files)
docker exec -it django python manage.py fix_file_sizes

# CHECK FILE SIZE STATUS
docker exec -it django python manage.py shell -c "from webui.models import ScrapFile; total = ScrapFile.objects.count(); incorrect = ScrapFile.objects.filter(size__gt=1024*1024).count(); print(f'Total files: {total}\\nFiles with incorrect sizes: {incorrect}\\nProgress: {(total-incorrect)/total*100:.2f}% files corrected ({total-incorrect}/{total})')"

#SEARCH CREDENTIALS WITH PERFORMANCE METRICS
docker exec -it django python manage.py search_credentials [SEARCH_TERM] --all
# For more options, see django/webui/management/commands/SEARCH_GUIDE.md


#FINDING MOST RECENT FILES IN TG DOWNLOADER
find /mnt/encrypted/leak_deteCTIon/telegram_downloader/app/channels -type f -mtime -30 | head -10

#CHECK LAST MIDIFICATION TIME IN MINIO
cd /mnt/encrypted/leak_deteCTIon && sudo ls -la data/minio_data/breached-credentials/ | head -5
#OR
cd /mnt/encrypted/leak_deteCTIon && sudo docker exec -it minio find /data/breached-credentials -type f -exec stat --format="%y %n" {} \; | sort -r | head -5



#CHECK THE MINIO COLLECTOR STATUS
cd /mnt/encrypted/leak_deteCTIon/django && python manage.py shell -c "from django_q.models import Task; print(Task.objects.filter(func__contains='collector').count())"

#MANUALLY SYNC TELEGRAM FILES TO MINIO
./sync_telegram_files.sh
# Or force re-upload of all files:
docker exec django python manage.py sync_telegram_files --force

