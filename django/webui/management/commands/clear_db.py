from django.core.management.base import BaseCommand
from webui.models import BreachedCredential, ScrapFile
from elasticsearch_dsl import connections
from django.db import connection
import time

class Command(BaseCommand):
    help = "Clear PostgreSQL database and Elasticsearch index of all data with progress updates."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("Starting database cleanup..."))

        # Clear PostgreSQL - BreachedCredential
        self.stdout.write(self.style.NOTICE("Clearing BreachedCredential records..."))
        start_time = time.time()
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE webui_breachedcredential CASCADE;")
            elapsed = time.time() - start_time
            self.stdout.write(
                self.style.WARNING(
                    f"✅ Truncated BreachedCredential table in {elapsed:.2f} seconds."
                )
            )

        # Clear PostgreSQL - ScrapFile
        self.stdout.write(self.style.NOTICE("Clearing ScrapFile records..."))
        start_time = time.time()
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE webui_scrapfile CASCADE;")
            elapsed = time.time() - start_time
            self.stdout.write(
                self.style.WARNING(
                    f"✅ Truncated ScrapFile table in {elapsed:.2f} seconds."
                )
            )

        # Clear Elasticsearch index
        self.stdout.write(self.style.NOTICE("Clearing Elasticsearch index 'breached_credentials'..."))
        start_time = time.time()
        es_client = connections.get_connection()
        index_name = "breached_credentials"
        try:
            if es_client.indices.exists(index=index_name):
                es_client.indices.delete(index=index_name)
                self.stdout.write(
                    self.style.WARNING(f"✅ Deleted Elasticsearch index '{index_name}'.")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"ℹ️ Index '{index_name}' did not exist.")
                )
            es_client.indices.create(index=index_name)
            elapsed = time.time() - start_time
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Recreated Elasticsearch index '{index_name}' in {elapsed:.2f} seconds."
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Failed to clear Elasticsearch: {str(e)}")
            )
            return

        self.stdout.write(self.style.SUCCESS("✅ Database and Elasticsearch cleared successfully."))