from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from .models import BreachedCredential
from .documents import BreachedCredentialDocument
from elasticsearch_dsl import Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# List View
class BreachedCredentialListView(ListView):
    model = BreachedCredential
    template_name = "webui/list.html"
    context_object_name = "credentials"


# Create View
class BreachedCredentialCreateView(CreateView):
    model = BreachedCredential
    fields = ["STRING", "source"]
    template_name = "webui/form.html"
    success_url = reverse_lazy("webui:list")


# Detail View
class BreachedCredentialDetailView(DetailView):
    model = BreachedCredential
    template_name = "webui/detail.html"
    context_object_name = "credential"


# Update View
class BreachedCredentialUpdateView(UpdateView):
    model = BreachedCredential
    fields = ["STRING", "source"]
    template_name = "webui/form.html"
    success_url = reverse_lazy("webui:list")


# Delete View
class BreachedCredentialDeleteView(DeleteView):
    model = BreachedCredential
    template_name = "webui/confirm_delete.html"
    success_url = reverse_lazy("webui:list")


@require_http_methods(["GET"])
def search_credentials(request):
    try:
        query = request.GET.get('q', '')
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))

        if not query:
            return JsonResponse({
                'results': [],
                'total': 0,
                'page': page,
                'per_page': per_page
            })

        # Simple wildcard search that should match any string containing the query
        search_query = Q('wildcard', string={'value': f'*{query}*'})
        search = BreachedCredentialDocument.search().query(search_query)
        response = search.execute()

        # Process results
        results = []
        for hit in response:
            results.append({
                'id': hit.meta.id,
                'string': hit.string,
                'file_name': hit.file_name,
                'file_size': hit.file_size,
                'file_uploaded_at': hit.file_uploaded_at,
                'created_at': hit.created_at,
                'modified': hit.modified
            })

        # Paginate results
        paginator = Paginator(results, per_page)
        page_obj = paginator.get_page(page)

        return JsonResponse({
            'results': list(page_obj),
            'total': response.hits.total.value,
            'page': page,
            'per_page': per_page,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous()
        })

    except Exception as e:
        logger.error(f"Error in search_credentials: {str(e)}")
        return JsonResponse({
            'error': 'An error occurred while searching',
            'details': str(e)
        }, status=500)
