from django.contrib import admin
from django_elasticsearch_dsl import Document
from webui.models import BreachedCredential, ScrapFile
from django_q.models import Task
from webui.documents import BreachedCredentialDocument
from elasticsearch_dsl import Q
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime, timedelta

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
    list_filter = ('added_at',)  # Keep for PSQL filtering, we'll add custom ES filter
    list_per_page = 50

    def get_search_results(self, request, queryset, search_term):
        if not search_term:
            return queryset, False
        search = BreachedCredentialDocument.search()
        wildcard_term = f"*{search_term.lower()}*"
        query = Q("wildcard", string=wildcard_term)
        search = search.query(query)
        es_ids = []
        for hit in search.scan():
            es_ids.append(int(hit.id))
        es_ids = es_ids[:50000]
        queryset = BreachedCredential.objects.filter(id__in=es_ids).select_related('file')
        return queryset, True

    def get_queryset(self, request):
        page = int(request.GET.get('p', 1))
        per_page = self.list_per_page
        start = (page - 1) * per_page
        end = start + per_page
        search = BreachedCredentialDocument.search()

        # Apply date filter from ES if present
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

            search = search.filter('range', indexed_at={
                'gte': start_date,
                'lte': end_date
            })

        search = search[start:end]
        es_ids = [int(hit.id) for hit in search]
        return BreachedCredential.objects.filter(id__in=es_ids).select_related('file')

    def get_paginator(self, request, queryset, per_page, orphans=0, allow_empty_first_page=True):
        total_count = BreachedCredentialDocument.search().count()
        paginator = Paginator(queryset, per_page, orphans, allow_empty_first_page)
        paginator.count = total_count
        return paginator

    def file_name(self, obj):
        return obj.file.name if obj.file else 'No file'
    file_name.short_description = 'File Name'