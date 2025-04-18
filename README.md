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
