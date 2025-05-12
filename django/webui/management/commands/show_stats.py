from django.core.management.base import BaseCommand
from django.db.models import Count, Sum, Avg
from django.db.models.functions import TruncDate
from webui.models import BreachedCredential, ScrapFile
from elasticsearch import Elasticsearch
from minio import Minio
from django.conf import settings
import re

class Command(BaseCommand):
    help = 'Show statistics about indexed credentials and files'

    def get_minio_size(self, file_name):
        try:
            client = Minio(
                'minio:9000',
                access_key=settings.AWS_ACCESS_KEY_ID,
                secret_key=settings.AWS_SECRET_ACCESS_KEY,
                secure=False
            )
            # Get the size in bytes and convert to MB
            obj = client.stat_object('breached-credentials', file_name)
            return obj.size / (1024 * 1024)  # Convert bytes to MB
        except Exception as e:
            return 0

    def handle(self, *args, **options):
        # Database stats
        total_credentials = BreachedCredential.objects.count()
        total_files = ScrapFile.objects.count()
        active_files = ScrapFile.objects.filter(is_active=True).count()
        
        # Get files statistics from DB
        files_by_status = ScrapFile.objects.aggregate(
            total_size=Sum('size'),
            avg_credentials=Avg('count')
        )
        
        # Get recent activity
        recent_files = ScrapFile.objects.order_by('-added_at')[:5]

        # Output statistics
        self.stdout.write('\n=== CTI Statistics ===')
        self.stdout.write(f'Total credentials in DB: {total_credentials:,}')
        self.stdout.write(f'Total files: {total_files:,} (Active: {active_files:,})')
        
        self.stdout.write('\nMost recent files:')
        for f in recent_files:
            actual_size = self.get_minio_size(f.name)
            self.stdout.write(
                f"- {f.name}\n"
                f"  * Stored size: {f.size:.2f} MB\n"
                f"  * Actual size: {actual_size:.2f} MB\n"
                f"  * Credentials: {f.count:,}"
            )

        # Elasticsearch stats
        try:
            es = Elasticsearch('http://elastic:9200')
            es_stats = es.indices.stats()
            total_indexed = es_stats['_all']['total']['docs']['count'] if es.indices.exists(index='credentials') else 0
            self.stdout.write(f'\nTotal documents indexed in Elasticsearch: {total_indexed:,}')
        except Exception as e:
            self.stdout.write(f'\nError connecting to Elasticsearch: {str(e)}')