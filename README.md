leak-deteCTIon

Simple, clear and secure CTI for local usage.

Stack:
Docker, Elasticsearch, Postgres, Python, Django

Plugins to do:
Telegram, Webscrapper


Mighty dev commands:

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