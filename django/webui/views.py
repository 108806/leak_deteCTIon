from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.urls import reverse_lazy
from .models import BreachedCredential, ScrapFile
from .documents import BreachedCredentialDocument
from elasticsearch_dsl import Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.conf import settings
import logging
import time

logger = logging.getLogger(__name__)

# List View
class BreachedCredentialListView(ListView):
    model = BreachedCredential
    template_name = "webui/list.html"
    context_object_name = "credentials"
    paginate_by = 20
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Get search parameters
        query = self.request.GET.get('q', '')
        search_type = self.request.GET.get('search_type', 'case_insensitive')
        field = self.request.GET.get('field', 'string')
        email_only = self.request.GET.get('email_only', 'false').lower() == 'true'
        sort_order = self.request.GET.get('sort', 'relevance')
        
        # Store initial query count for metrics
        self.initial_count = queryset.count()
        
        # Reset search error and fallback flags
        self.search_error = None
        self.search_suggestion = None
        self.search_fallback = None
        
        if query:
            try:
                # Choose search strategy based on search_type parameter
                if search_type == 'exact':
                    # Use filter here as we're not using Elasticsearch yet
                    queryset = queryset.filter(string__exact=query)
                elif search_type == 'wildcard':
                    # Simulate wildcard with contains
                    queryset = queryset.filter(string__contains=query)
                elif search_type == 'regexp':
                    # For regexp, we'll need to use icontains as a simpler alternative
                    queryset = queryset.filter(string__icontains=query)
                elif search_type == 'match':
                    # Match query in ES, in Django we'll use contains
                    queryset = queryset.filter(string__contains=query)
                else:
                    # Default case-insensitive search
                    queryset = queryset.filter(string__icontains=query)
                
                # Apply field filtering if needed
                if field == 'username':
                    # Ensure the string has a colon and filter for the username part
                    queryset = queryset.filter(string__regex=r'^[^:]+:')
                elif field == 'password':
                    # Ensure the string has a colon and password part
                    queryset = queryset.filter(string__regex=r':.+')
                
                # Add email filter if requested
                if email_only:
                    queryset = queryset.filter(string__regex=r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
                
                # Apply sorting
                if sort_order == 'date':
                    queryset = queryset.order_by('-added_at')
                    
            except Exception as e:
                logger.error(f"Search error in ListView: {str(e)}")
                self.search_error = f"Search error: {str(e)}"
                self.search_suggestion = "Try a simpler search query or a different search type."
                
                # Fallback to a very basic search
                try:
                    queryset = queryset.filter(string__icontains=query)[:100]
                    self.search_fallback = "Search encountered an error. Showing limited basic results."
                except Exception as fallback_e:
                    # If even the basic search fails, return an empty queryset
                    logger.error(f"Fallback search error: {str(fallback_e)}")
                    queryset = BreachedCredential.objects.none()
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add search parameters to context for form persistence
        context['query'] = self.request.GET.get('q', '')
        context['search_type'] = self.request.GET.get('search_type', 'case_insensitive')
        context['field'] = self.request.GET.get('field', 'string')
        context['email_only'] = self.request.GET.get('email_only', 'false').lower() == 'true'
        context['sort_order'] = self.request.GET.get('sort', 'relevance')
        
        # Add error and fallback messages
        context['search_error'] = getattr(self, 'search_error', None)
        context['search_suggestion'] = getattr(self, 'search_suggestion', None)
        context['search_fallback'] = getattr(self, 'search_fallback', None)
        
        return context


# Create View
class BreachedCredentialCreateView(CreateView):
    model = BreachedCredential
    fields = ["string", "file"]
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
    fields = ["string", "file"]
    template_name = "webui/form.html"
    success_url = reverse_lazy("webui:list")


# Delete View
class BreachedCredentialDeleteView(DeleteView):
    model = BreachedCredential
    template_name = "webui/confirm_delete.html"
    success_url = reverse_lazy("webui:list")


# Dashboard View
class DashboardView(TemplateView):
    template_name = "webui/dashboard.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        from elasticsearch_dsl.connections import get_connection
        from django.db.models import Count
        import datetime
        import elastic_transport  # Import for exception handling
        
        # Initialize default values for ES stats
        context.update({
            "es_status": "error",
            "es_error": "Not connected",
            "es_health": {},
            "es_indices": [],
            "es_nodes": [],
            "doc_count": 0,
            "store_size": 0,
            "query_total": 0,
            "query_time": 0,
            "fetch_total": 0,
            "fetch_time": 0,
        })
        
        # Get Elasticsearch cluster health with timeout handling
        try:
            es_client = get_connection()
            # Use a shorter timeout for initial health check to make the page load faster
            health = es_client.cluster.health(request_timeout=5)
            
            # Only fetch additional details if basic health check succeeds
            context["es_health"] = health
            context["es_status"] = "connected"
            
            try:
                # Get indices
                indices = es_client.cat.indices(format="json")
                context["es_indices"] = indices
                
                # Get nodes
                nodes = es_client.cat.nodes(format="json")
                context["es_nodes"] = nodes
                
                # Check if the index exists first - note: the correct index name is 'breached_credentials' (plural)
                if es_client.indices.exists(index='breached_credentials', request_timeout=5):
                    try:
                        index_stats = es_client.indices.stats(index='breached_credentials', request_timeout=5)
                        
                        # Extract statistics for template (avoiding underscore-prefixed attributes)
                        if index_stats and '_all' in index_stats and 'primaries' in index_stats['_all']:
                            primaries = index_stats['_all']['primaries']
                            
                            # Document count
                            if 'docs' in primaries and 'count' in primaries['docs']:
                                context['doc_count'] = primaries['docs']['count']
                            
                            # Storage size
                            if 'store' in primaries and 'size_in_bytes' in primaries['store']:
                                context['store_size'] = primaries['store']['size_in_bytes']
                            
                            # Query stats
                            if 'search' in primaries:
                                context['query_total'] = primaries['search'].get('query_total', 0)
                                context['query_time'] = primaries['search'].get('query_time_in_millis', 0)
                                context['fetch_total'] = primaries['search'].get('fetch_total', 0)
                                context['fetch_time'] = primaries['search'].get('fetch_time_in_millis', 0)
                    except (elastic_transport.ConnectionTimeout, Exception) as e:
                        logger.warning(f"Error fetching index stats: {str(e)}. Dashboard will show limited information.")
                else:
                    logger.warning("Index 'breached_credentials' does not exist yet. This is normal if no data has been indexed.")
            except (elastic_transport.ConnectionTimeout, Exception) as e:
                logger.warning(f"Error fetching ES details: {str(e)}. Dashboard will show limited information.")
                
        except (elastic_transport.ConnectionTimeout, Exception) as e:
            logger.error(f"Error connecting to Elasticsearch: {str(e)}")
            context["es_error"] = f"Connection issue: {str(e)}"
        
        # Get database stats
        context["total_credentials"] = BreachedCredential.objects.count()
        context["total_files"] = ScrapFile.objects.count()
        
        # Get recent files
        context["recent_files"] = ScrapFile.objects.all().order_by('-added_at')[:5]
        
        # Get credential count by date (last 7 days)
        from django.utils import timezone
        end_date = timezone.now()
        start_date = end_date - datetime.timedelta(days=7)
        
        try:
            daily_counts = BreachedCredential.objects.filter(
                added_at__range=(start_date, end_date)
            ).extra({
                'day': "date(added_at)"
            }).values('day').annotate(count=Count('id')).order_by('day')
            
            # Format data for chart
            context["credential_dates"] = [entry['day'].strftime('%Y-%m-%d') for entry in daily_counts]
            context["credential_counts"] = [entry['count'] for entry in daily_counts]
        except Exception as e:
            logger.error(f"Error generating daily counts: {str(e)}")
            context["credential_dates"] = []
            context["credential_counts"] = []
        
        return context


@require_http_methods(["GET"])
def search_credentials(request):
    try:
        # Get search parameters from request
        query = request.GET.get('q', '')
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        search_type = request.GET.get('search_type', 'case_insensitive')  # Default to case-insensitive
        field = request.GET.get('field', 'string')  # Options: string, username, password
        email_only = request.GET.get('email_only', 'false').lower() == 'true'  # Filter for emails only
        sort_order = request.GET.get('sort', 'relevance')  # Options: relevance, date
        
        logger.debug(f"Search request: query='{query}', type={search_type}, field={field}, email_only={email_only}, sort={sort_order}")

        if not query:
            return JsonResponse({
                'results': [],
                'total': 0,
                'page': page,
                'per_page': per_page,
                'search_type': search_type,
                'field': field,
                'email_only': email_only,
                'sort_order': sort_order
            })

        # Choose search strategy based on search_type parameter
        if search_type == 'exact':
            # Term query - exact match
            search_query = Q('term', string=query)
        elif search_type == 'wildcard':
            # Wildcard search that matches any string containing the query
            search_query = Q('wildcard', string={'value': f'*{query}*'})
        elif search_type == 'regexp':
            # Create a case-insensitive regexp pattern
            pattern = ".*"
            for char in query:
                if char.isalpha():
                    pattern += f"[{char.lower()}{char.upper()}]"
                else:
                    pattern += char
            pattern += ".*"
            search_query = Q('regexp', string={'value': pattern})
        elif search_type == 'match':
            # Standard match query
            search_query = Q('match', string=query)
        else:
            # Default case-insensitive search using ngram field
            search_query = Q('match', **{'string.ngram': query})
        
        # Start with base search
        search = BreachedCredentialDocument.search().query(search_query)
        
        # Apply field filtering if needed
        if field == 'username':
            # Filter for username part (before the colon)
            search = search.filter('regexp', string='^[^:]+:')
        elif field == 'password':
            # Filter for password part (after the colon)
            search = search.filter('regexp', string=':.+')
        
        # Add email filter if requested
        if email_only:
            search = search.filter('regexp', string='[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}')
        
        # Apply sorting
        if sort_order == 'date':
            search = search.sort('-added_at')
            
        # Get search parameters from settings
        from django.conf import settings
        search_params = getattr(settings, 'ELASTICSEARCH_SEARCH_PARAMS', {})
        
        # Track performance
        start_time = time.time()
        
        try:
            # Execute search with timeout and error handling
            response = search.params(**search_params).execute()
            
            # Process results
            results = []
            for hit in response:
                results.append({
                    'id': hit.meta.id,
                    'string': hit.string,
                    'file_name': hit.file_name,
                    'file_size': hit.file_size,
                    'file_uploaded_at': hit.file_uploaded_at,
                    'created_at': hit.added_at,
                    'modified': getattr(hit, 'modified', None)
                })
                
            elapsed_time = time.time() - start_time
            logger.info(f"Search completed: {response.hits.total.value} results in {elapsed_time:.3f} seconds")
            
            # Paginate results
            paginator = Paginator(results, per_page)
            page_obj = paginator.get_page(page)

            return JsonResponse({
                'results': list(page_obj),
                'total': response.hits.total.value,
                'page': page,
                'per_page': per_page,
                'search_type': search_type,
                'field': field,
                'email_only': email_only,
                'sort_order': sort_order,
                'elapsed_time': elapsed_time,
                'status': 'success'
            })
            
        except Exception as e:
            # Handle Elasticsearch timeouts and other connection errors
            import elastic_transport
            elapsed_time = time.time() - start_time
            
            error_type = type(e).__name__
            error_message = str(e)
            
            logger.error(f"Elasticsearch search error ({error_type}): {error_message}")
            
            # For timeout errors, try a fallback to database search for simple queries
            if isinstance(e, elastic_transport.ConnectionTimeout) and search_type in ['exact', 'wildcard', 'match']:
                logger.info(f"Elasticsearch timeout, attempting database fallback for query: {query}")
                
                # Attempt database fallback
                try:
                    fallback_start_time = time.time()
                    
                    # Basic Django ORM query (this will be much more limited than ES)
                    db_queryset = BreachedCredential.objects.all()
                    
                    if search_type == 'exact':
                        db_queryset = db_queryset.filter(string__exact=query)
                    elif search_type in ['wildcard', 'match']:
                        db_queryset = db_queryset.filter(string__icontains=query)
                    
                    # Limit results to avoid performance issues
                    db_queryset = db_queryset[:100]
                    
                    # Convert to list of dictionaries for JSON response
                    fallback_results = []
                    for cred in db_queryset:
                        fallback_results.append({
                            'id': cred.id,
                            'string': cred.string,
                            'created_at': cred.added_at,
                            'file_name': cred.file.name if cred.file else 'Unknown',
                        })
                    
                    fallback_elapsed_time = time.time() - fallback_start_time
                    total_elapsed_time = time.time() - start_time
                    
                    logger.info(f"Database fallback completed: {len(fallback_results)} results in {fallback_elapsed_time:.3f} seconds")
                    
                    return JsonResponse({
                        'results': fallback_results,
                        'total': len(fallback_results),
                        'page': 1,
                        'per_page': 100,
                        'search_type': search_type,
                        'field': field,
                        'email_only': email_only,
                        'sort_order': sort_order,
                        'elapsed_time': total_elapsed_time,
                        'status': 'fallback',
                        'message': 'Search completed using database fallback due to Elasticsearch timeout',
                    })
                    
                except Exception as fallback_error:
                    logger.error(f"Database fallback also failed: {str(fallback_error)}")
            
            # If we get here, both Elasticsearch and fallback failed or fallback wasn't attempted
            return JsonResponse({
                'results': [],
                'total': 0,
                'page': page,
                'per_page': per_page,
                'search_type': search_type,
                'field': field,
                'email_only': email_only,
                'sort_order': sort_order,
                'elapsed_time': elapsed_time,
                'status': 'error',
                'error': {
                    'type': error_type,
                    'message': error_message,
                },
                'message': 'Search failed due to an Elasticsearch error. Please try a different search or try again later.'
            }, status=500)
    
    except Exception as e:
        # Handle any other errors
        logger.error(f"Unexpected error in search_credentials: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'An unexpected error occurred during search processing',
            'error': str(e)
        }, status=500)
