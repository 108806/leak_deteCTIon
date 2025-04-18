from django.contrib import admin
from django.contrib.sessions.models import Session
from django_elasticsearch_dsl import Document
from webui.models import BreachedCredential, ScrapFile
from django_q.models import Task
from webui.documents import BreachedCredentialDocument
from elasticsearch_dsl import Q
from django.db.models import Case, When
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime, timedelta
import logging

# Configure logging to ensure debug output
logger = logging.getLogger('webui')
logger.setLevel(logging.DEBUG)

# Add console handler if not already present
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# Register default Django admin models
admin.site.register(Session)

@admin.register(ScrapFile)
class ScrapFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'count', 'added_at', 'size', 'sha256')
    search_fields = ('name', 'sha256')
    list_filter = ('added_at', 'count', 'size')

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'func', 'started', 'stopped', 'success')
    list_filter = ('success', 'started')
    search_fields = ('name', 'func')

@admin.register(BreachedCredential)
class BreachedCredentialAdmin(admin.ModelAdmin):
    list_display = ('string', 'added_at', 'file_name')
    search_fields = ['string']
    list_filter = ('added_at',)
    list_per_page = 50

    def get_search_results(self, request, queryset, search_term):
        if not search_term:
            return queryset, False

        print(f"\n[*] DEBUG: Search term: {search_term}")
        print(f"[*] DEBUG: Initial queryset count: {queryset.count()}")

        # Use Elasticsearch for searching
        search = BreachedCredentialDocument.search()
        print(f"[*] DEBUG: Using index: {search._index}")
        
        # Use query_string with wildcards
        query = Q(
            'query_string',
            query=f"*{search_term}*",
            fields=['string', 'string.ngram'],
            analyze_wildcard=True
        )
        search = search.query(query)
        
        # Set a larger size for the search results
        search = search.extra(size=10000)  # Return up to 10k results
        
        # Print the actual query being sent to Elasticsearch
        print(f"[*] DEBUG: Full Elasticsearch query: {search.to_dict()}")
        
        # Execute the search without any filters
        response = search.execute()
        print(f"[*] DEBUG: Raw Elasticsearch response total: {response.hits.total.value}")
        print(f"[*] DEBUG: Raw Elasticsearch response hits: {len(response.hits)}")
        
        # Print first few hits to verify content and IDs
        print("\n[*] DEBUG: First 5 hits:")
        for hit in response.hits[:5]:
            print(f"  - ID: {hit.meta.id} (type: {type(hit.meta.id)})")
            print(f"  - String: {hit.string}")
        
        # Get the IDs from the search results
        result_ids = [hit.meta.id for hit in response]
        
        # Get the queryset with the results in the same order as the search
        if result_ids:
            # Convert IDs to integers if they're strings
            result_ids = [int(id) if isinstance(id, str) else id for id in result_ids]
            
            preserved = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(result_ids)])
            queryset = queryset.filter(id__in=result_ids).order_by(preserved)
            print(f"[*] DEBUG: Final queryset count: {queryset.count()}")
        else:
            queryset = queryset.none()
        
        return queryset, False

    def get_queryset(self, request):
        logger.debug('[*] Get queryset was triggered')
        
        # If this is a search request, let get_search_results handle it
        if request.GET.get('q'):
            return super().get_queryset(request)
            
        # Otherwise, handle normal list view with pagination
        page = int(request.GET.get('p', 1))
        per_page = self.list_per_page
        start = (page - 1) * per_page
        end = start + per_page
        
        search = BreachedCredentialDocument.search()
        
        # Apply date filters if present
        date_filter = request.GET.get('added_at__day', None)
        if date_filter:
            today = timezone.now().date()
            start_date = today
            if date_filter == 'today':
                end_date = today + timedelta(days=1)
            elif date_filter == 'past_7_days':
                start_date = today - timedelta(days=7)
                end_date = today + timedelta(days=1)
            elif date_filter == 'this_month':
                start_date = today.replace(day=1)
                end_date = (start_date + timedelta(days=32)).replace(day=1)
            elif date_filter == 'this_year':
                start_date = today.replace(month=1, day=1)
                end_date = today.replace(month=12, day=31)
            search = search.filter('range', indexed_at={'gte': start_date, 'lte': end_date})
        
        # Apply pagination
        search = search[start:end]
        es_ids = [hit.meta.id for hit in search]
        
        logger.debug("ES IDs retrieved: %d - %s", len(es_ids), es_ids[:10])
        if not es_ids:
            return BreachedCredential.objects.none()
            
        queryset = BreachedCredential.objects.filter(id__in=es_ids).select_related('file')
        logger.debug("PSQL found %d records for IDs: %s", queryset.count(), es_ids[:10])
        return queryset

    def get_paginator(self, request, queryset, per_page, orphans=0, allow_empty_first_page=True):
        # If this is a search request, use the actual count from the queryset
        if request.GET.get('q'):
            total_count = queryset.count()
        else:
            # For normal list view, use Elasticsearch count
            total_count = BreachedCredentialDocument.search().count()
            
        paginator = Paginator(queryset, per_page, orphans, allow_empty_first_page)
        paginator.count = total_count
        logger.debug("Paginator total_count: %d", total_count)
        logger.debug("Queryset actual count: %d", queryset.count())
        return paginator

    def file_name(self, obj):
        return obj.file.name if obj.file else 'No file'
    file_name.short_description = 'File Name'