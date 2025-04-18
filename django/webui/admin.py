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
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

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

        # Use Elasticsearch for searching
        search = BreachedCredentialDocument.search()
        
        # Create a multi-match query that searches across different fields
        query = Q(
            'multi_match',
            query=search_term,
            fields=[
                'string^3',  # Boost the main string field
                'string.ngram^2',  # Include ngram matches with lower boost
                'string.edge_ngram^2',  # Include edge ngram matches with lower boost
            ],
            type='best_fields',
            operator='or',
            fuzziness='AUTO'
        )
        
        # Add filters for any existing filters
        if queryset.exists():
            ids = list(queryset.values_list('id', flat=True))
            query = query & Q('terms', id=ids)
        
        search = search.query(query)
        
        # Execute the search
        response = search.execute()
        
        # Get the IDs from the search results
        result_ids = [hit.id for hit in response]
        
        # Get the queryset with the results in the same order as the search
        if result_ids:
            preserved = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(result_ids)])
            queryset = queryset.filter(id__in=result_ids).order_by(preserved)
        else:
            queryset = queryset.none()
        
        return queryset, False

    def get_queryset(self, request):
        logger.debug('[*] Get queryset was triggered')
        page = int(request.GET.get('p', 1))
        per_page = self.list_per_page
        start = (page - 1) * per_page
        end = start + per_page
        search = BreachedCredentialDocument.search()

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

        search = search[start:end]
        es_ids = [int(hit.id) for hit in search]
        logger.debug("ES IDs retrieved: %d - %s", len(es_ids), es_ids[:10])
        if not es_ids:
            return BreachedCredential.objects.none()
        queryset = BreachedCredential.objects.filter(id__in=es_ids).select_related('file')
        logger.debug("PSQL found %d records for IDs: %s", queryset.count(), es_ids[:10])
        return queryset

    def get_paginator(self, request, queryset, per_page, orphans=0, allow_empty_first_page=True):
        total_count = BreachedCredentialDocument.search().count()
        paginator = Paginator(queryset, per_page, orphans, allow_empty_first_page)
        paginator.count = total_count
        logger.debug("Paginator total_count: %d", total_count)
        logger.debug("Queryset actual count: %d", queryset.count())
        return paginator

    def file_name(self, obj):
        return obj.file.name if obj.file else 'No file'
    file_name.short_description = 'File Name'