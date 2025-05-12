from django.core.management.base import BaseCommand
from django.conf import settings
import json
import time
from datetime import datetime
import requests
import logging
import csv
import os

# Setup logging
logger = logging.getLogger(__name__)

# Configuration
ELASTIC_INDEX = "breached_credentials"
DEFAULT_SIZE = 5

class Command(BaseCommand):
    help = 'Search for credentials and measure performance of different query types'

    def add_arguments(self, parser):
        parser.add_argument("search_term", help="Term to search for")
        parser.add_argument("--size", type=int, default=DEFAULT_SIZE, help="Number of results to return")
        parser.add_argument("--all", action="store_true", help="Run all query types")
        parser.add_argument("--term", action="store_true", help="Run term query (exact match)")
        parser.add_argument("--wildcard", action="store_true", help="Run wildcard query")
        parser.add_argument("--regexp", action="store_true", help="Run regexp query")
        parser.add_argument("--match", action="store_true", help="Run match query")
        parser.add_argument("--case-insensitive", action="store_true", help="Run case-insensitive query")
        parser.add_argument("--output", help="Save results to file")
        parser.add_argument("--format", choices=["txt", "csv", "json", "md"], default="txt", 
                           help="Output format (default: txt)")
        parser.add_argument("--field", choices=["string", "username", "password", "both"], default="string",
                           help="Field to search in (default: string, searches whole credential)")
        parser.add_argument("--email-only", action="store_true", help="Search only for email addresses")
        parser.add_argument("--sort", choices=["relevance", "date"], default="relevance",
                           help="Sort order for results (default: relevance)")
        parser.add_argument("--verbose", action="store_true", help="Show verbose output including query details")
        parser.add_argument("--save-results", action="store_true", help="Save actual results, not just statistics")

    def handle(self, *args, **options):
        # If no specific query types are selected, default to --all
        if not (options.get('all') or options.get('term') or options.get('wildcard') or 
                options.get('regexp') or options.get('match') or options.get('case_insensitive')):
            options['all'] = True
        
        search_term = options['search_term']
        size = options['size']
        verbose = options.get('verbose', False)
        field = options.get('field', 'string')
        email_only = options.get('email_only', False)
        sort_order = options.get('sort', 'relevance')
        
        self.stdout.write(
            self.style.SUCCESS(f"[*] Starting search for '{search_term}' at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        )
        self.stdout.write(f"[*] Index: {ELASTIC_INDEX}")
        
        if verbose:
            self.stdout.write(f"[*] Search field: {field}")
            self.stdout.write(f"[*] Email only: {email_only}")
            self.stdout.write(f"[*] Sort order: {sort_order}")
        
        # Get Elasticsearch URL from settings
        es_url = f"{settings.ELASTICSEARCH_DSL['default']['hosts']}/{ELASTIC_INDEX}/_search"
        
        results = []
        all_hits = {}
        
        if options['all'] or options['term']:
            count, elapsed, hits = self.run_query(
                es_url, self.term_query(search_term, size, field, email_only, sort_order), 
                "TERM QUERY (exact match)",
                verbose
            )
            results.append(("Term", count, elapsed))
            all_hits["Term"] = hits
        
        if options['all'] or options['wildcard']:
            count, elapsed, hits = self.run_query(
                es_url, self.wildcard_query(f"*{search_term}*", size, field, email_only, sort_order), 
                "WILDCARD QUERY (*term*)",
                verbose
            )
            results.append(("Wildcard", count, elapsed))
            all_hits["Wildcard"] = hits
        
        if options['all'] or options['regexp']:
            # Create a case-insensitive regexp pattern
            pattern = ".*"
            for char in search_term:
                if char.isalpha():
                    pattern += f"[{char.lower()}{char.upper()}]"
                else:
                    pattern += char
            pattern += ".*"
            
            count, elapsed, hits = self.run_query(
                es_url, self.regexp_query(pattern, size, field, email_only, sort_order),
                f"REGEXP QUERY (case-insensitive: {pattern})",
                verbose
            )
            results.append(("Regexp", count, elapsed))
            all_hits["Regexp"] = hits
        
        if options['all'] or options['match']:
            count, elapsed, hits = self.run_query(
                es_url, self.match_query(search_term, size, field, email_only, sort_order),
                "MATCH QUERY",
                verbose
            )
            results.append(("Match", count, elapsed))
            all_hits["Match"] = hits
        
        if options['all'] or options['case_insensitive']:
            count, elapsed, hits = self.run_query(
                es_url, self.case_insensitive_query(search_term, size, field, email_only, sort_order),
                "CASE-INSENSITIVE QUERY (bool/should with wildcards)",
                verbose
            )
            results.append(("Case-insensitive", count, elapsed))
            all_hits["Case-insensitive"] = hits
        
        # Print summary table
        self.stdout.write(self.style.SUCCESS("\n[*] SEARCH PERFORMANCE SUMMARY"))
        self.stdout.write("-" * 60)
        self.stdout.write(f"{'Query Type':<20} {'Results':<10} {'Time (s)':<10} {'Hits/sec':<10}")
        self.stdout.write("-" * 60)
        
        for query_type, count, elapsed in results:
            if count > 0 and elapsed > 0:
                rate = count / elapsed
            else:
                rate = 0
            self.stdout.write(f"{query_type:<20} {count:<10} {elapsed:<10.3f} {rate:<10.1f}")
        
        if options.get('output'):
            try:
                output_format = options.get('format', 'txt')
                output_file = options['output']
                
                # Ensure file has correct extension
                if not output_file.endswith(f".{output_format}"):
                    output_file = f"{output_file}.{output_format}"
                
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
                
                # Save results in chosen format
                if output_format == 'csv':
                    self._save_csv(output_file, search_term, results, all_hits if options.get('save_results') else None)
                elif output_format == 'json':
                    self._save_json(output_file, search_term, results, all_hits if options.get('save_results') else None)
                elif output_format == 'md':
                    self._save_markdown(output_file, search_term, results, all_hits if options.get('save_results') else None)
                else:  # Default to txt
                    self._save_txt(output_file, search_term, results, all_hits if options.get('save_results') else None)
                
                self.stdout.write(self.style.SUCCESS(f"[+] Results saved to {output_file}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[!] Error saving results: {e}"))

    def _save_txt(self, file_path, search_term, results, hits=None):
        """Save results in plain text format."""
        with open(file_path, 'w') as f:
            f.write(f"# Search Performance Results for '{search_term}'\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"{'Query Type':<20} {'Results':<10} {'Time (s)':<10} {'Hits/sec':<10}\n")
            f.write("-" * 60 + "\n")
            
            for query_type, count, elapsed in results:
                if count > 0 and elapsed > 0:
                    rate = count / elapsed
                else:
                    rate = 0
                f.write(f"{query_type:<20} {count:<10} {elapsed:<10.3f} {rate:<10.1f}\n")
            
            # Include actual results if requested
            if hits:
                f.write("\n\n# Sample Results\n")
                for query_type, query_hits in hits.items():
                    f.write(f"\n## {query_type} Query Results\n")
                    for i, hit in enumerate(query_hits[:5], 1):
                        source = hit.get('_source', {})
                        string = source.get('string', 'N/A')
                        f.write(f"{i}. {string}\n")

    def _save_csv(self, file_path, search_term, results, hits=None):
        """Save results in CSV format."""
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Query Type', 'Results', 'Time (s)', 'Hits/sec'])
            
            for query_type, count, elapsed in results:
                if count > 0 and elapsed > 0:
                    rate = count / elapsed
                else:
                    rate = 0
                writer.writerow([query_type, count, f"{elapsed:.3f}", f"{rate:.1f}"])
            
            # Include actual results if requested
            if hits:
                writer.writerow([])
                writer.writerow(['Query Type', 'Result #', 'Credential'])
                
                for query_type, query_hits in hits.items():
                    for i, hit in enumerate(query_hits[:5], 1):
                        source = hit.get('_source', {})
                        string = source.get('string', 'N/A')
                        writer.writerow([query_type, i, string])

    def _save_json(self, file_path, search_term, results, hits=None):
        """Save results in JSON format."""
        data = {
            'search_term': search_term,
            'date': datetime.now().isoformat(),
            'results': []
        }
        
        for query_type, count, elapsed in results:
            rate = count / elapsed if count > 0 and elapsed > 0 else 0
            data['results'].append({
                'query_type': query_type,
                'count': count,
                'time': elapsed,
                'hits_per_second': rate
            })
        
        # Include actual results if requested
        if hits:
            data['sample_hits'] = {}
            for query_type, query_hits in hits.items():
                data['sample_hits'][query_type] = []
                for hit in query_hits[:5]:
                    source = hit.get('_source', {})
                    data['sample_hits'][query_type].append(source)
        
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _save_markdown(self, file_path, search_term, results, hits=None):
        """Save results in Markdown format."""
        with open(file_path, 'w') as f:
            f.write(f"# Search Performance Results for '{search_term}'\n\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write("## Performance Summary\n\n")
            f.write("| Query Type | Results | Time (s) | Hits/sec |\n")
            f.write("|------------|---------|----------|----------|\n")
            
            for query_type, count, elapsed in results:
                if count > 0 and elapsed > 0:
                    rate = count / elapsed
                else:
                    rate = 0
                f.write(f"| {query_type} | {count} | {elapsed:.3f} | {rate:.1f} |\n")
            
            # Include actual results if requested
            if hits:
                f.write("\n## Sample Results\n\n")
                for query_type, query_hits in hits.items():
                    f.write(f"### {query_type} Query Results\n\n")
                    
                    for i, hit in enumerate(query_hits[:5], 1):
                        source = hit.get('_source', {})
                        string = source.get('string', 'N/A')
                        f.write(f"{i}. `{string}`\n")
                    
                    f.write("\n")

    def run_query(self, es_url, query, description, verbose=False):
        """Run an Elasticsearch query and measure performance."""
        self.stdout.write(f"\n[*] Running {description}")
        
        if verbose:
            self.stdout.write(f"[*] Query: {query}")
            
        start_time = time.time()
        
        try:
            # Execute the query using HTTP request
            headers = {'Content-Type': 'application/json'}
            response = requests.post(es_url, headers=headers, data=query)
            response.raise_for_status()  # Raise exception for 4XX/5XX responses
            
            result = response.json()
            elapsed = time.time() - start_time
            
            # Parse the response
            hit_count = result['hits']['total']['value']
            relation = result['hits']['total']['relation']
            hit_display = f"{hit_count}" if relation == "eq" else f"{hit_count}+"
            
            self.stdout.write(self.style.SUCCESS(f"[+] Found {hit_display} results in {elapsed:.3f} seconds"))
            
            if result['hits']['hits']:
                self.stdout.write(f"\n[*] Sample Results:")
                for i, hit in enumerate(result['hits']['hits'][:5], 1):
                    source = hit.get('_source', {})
                    string = source.get('string', 'N/A')
                    self.stdout.write(f"    {i}. {string}")
            
            return hit_count, elapsed, result['hits']['hits']
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[!] Error: {e}"))
            return 0, 0, []

    def _build_query_with_options(self, base_query, size, field, email_only, sort_order):
        """Build a query with filters and sorting options."""
        # Start with the base query
        query_dict = {"size": size, "track_total_hits": True}
        
        # Add field-specific filtering if needed
        if field != "string" or email_only:
            # If we're searching a specific part of the credential
            if field == "username":
                base_query = {"bool": {"must": [base_query], "filter": {"regexp": {"string": "^[^:]+:"}}}}
            elif field == "password":
                base_query = {"bool": {"must": [base_query], "filter": {"regexp": {"string": ":.+"}}}}
            
            # Add email filter if requested
            if email_only:
                email_filter = {"regexp": {"string": "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}"}}
                if "bool" in base_query:
                    if "filter" in base_query["bool"]:
                        base_query["bool"]["filter"] = [base_query["bool"]["filter"], email_filter]
                    else:
                        base_query["bool"]["filter"] = email_filter
                else:
                    base_query = {"bool": {"must": [base_query], "filter": email_filter}}
        
        # Add the query to the query dictionary
        query_dict["query"] = base_query
        
        # Add sorting if requested
        if sort_order == "date":
            query_dict["sort"] = [{"added_at": {"order": "desc"}}]
        
        return json.dumps(query_dict)

    def term_query(self, term, size=DEFAULT_SIZE, field="string", email_only=False, sort_order="relevance"):
        """Create term query using keyword field for exact matches."""
        base_query = {"term": {"string.keyword": term}}
        return self._build_query_with_options(base_query, size, field, email_only, sort_order)

    def wildcard_query(self, pattern, size=DEFAULT_SIZE, field="string", email_only=False, sort_order="relevance"):
        """Create wildcard query with caching for improved performance."""
        query_dict = {
            "wildcard": {"string.keyword": pattern},
            "_cache": True
        }
        return self._build_query_with_options(query_dict, size, field, email_only, sort_order)

    def regexp_query(self, pattern, size=DEFAULT_SIZE, field="string", email_only=False, sort_order="relevance"):
        """Create regexp query - if possible, prefer using analyzed fields instead."""
        base_query = {"regexp": {"string.keyword": pattern}}
        return self._build_query_with_options(base_query, size, field, email_only, sort_order)

    def match_query(self, text, size=DEFAULT_SIZE, field="string", email_only=False, sort_order="relevance"):
        """Create match query using the analyzed field for better performance."""
        base_query = {"match": {"string.analyzed": text}}
        return self._build_query_with_options(base_query, size, field, email_only, sort_order)

    def case_insensitive_query(self, term, size=DEFAULT_SIZE, field="string", email_only=False, sort_order="relevance"):
        """Create case-insensitive query using the optimized analyzed field."""
        # Using the string.analyzed field with the credential_analyzer for better performance
        base_query = {"match": {"string.analyzed": term}}
        return self._build_query_with_options(base_query, size, field, email_only, sort_order)
