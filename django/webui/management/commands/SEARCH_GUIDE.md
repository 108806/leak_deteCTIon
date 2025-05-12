# Credential Search Tool Guide

This document explains how to use the credential search tool to efficiently search the breached credentials database using different query types and measure search performance.

## Basic Usage

```bash
# Run a basic search with all query types
docker exec -it django python manage.py search_credentials frost

# Specify number of results to return
docker exec -it django python manage.py search_credentials frost --size 10

# Run only specific query types
docker exec -it django python manage.py search_credentials frost --term --regexp

# Save results to a file with specific format
docker exec -it django python manage.py search_credentials frost --output /path/to/results --format json
```

## Query Types

The tool supports different search query types, each with its own advantages:

1. **Term Query** (`--term`): Exact match search
   - Fastest method but case-sensitive and only matches exact terms
   - Example: `frost` will match "frost" but not "Frost" or "frosty"

2. **Wildcard Query** (`--wildcard`): Pattern matching with * and ?
   - Flexible but slower, especially for large datasets
   - Example: `*frost*` matches anything containing "frost"

3. **Regexp Query** (`--regexp`): Regular expression matching
   - Good balance of flexibility and performance
   - Automatically creates case-insensitive patterns
   - Example: `.*[fF][rR][oO][sS][tT].*` matches any case of "frost"

4. **Match Query** (`--match`): Text analysis-based matching
   - Uses Elasticsearch's text analysis capabilities
   - Performance depends on analyzer configuration

5. **Case-insensitive Query** (`--case-insensitive`): Combines approaches
   - Uses bool/should with wildcards for different cases
   - Example: searches for both `*frost*` and `*Frost*`

## Advanced Features

### Field-Specific Searches

You can narrow your search to specific parts of credentials:

```bash
# Search only in usernames
docker exec -it django python manage.py search_credentials admin --field username

# Search only in passwords
docker exec -it django python manage.py search_credentials pass123 --field password

# Search in both username and password (default)
docker exec -it django python manage.py search_credentials test --field both
```

### Email-Only Filtering

Focus your search on email addresses only:

```bash
docker exec -it django python manage.py search_credentials gmail --email-only
```

### Output Formats

Save results in different formats:

```bash
# Save as plain text (default)
docker exec -it django python manage.py search_credentials frost --output results --format txt

# Save as CSV
docker exec -it django python manage.py search_credentials frost --output results --format csv

# Save as JSON
docker exec -it django python manage.py search_credentials frost --output results --format json

# Save as Markdown
docker exec -it django python manage.py search_credentials frost --output results --format md
```

### Result Sorting

Sort results by relevance or date:

```bash
# Sort by date (newest first)
docker exec -it django python manage.py search_credentials frost --sort date

# Sort by relevance (default)
docker exec -it django python manage.py search_credentials frost --sort relevance
```

### Verbose Output

Get detailed information about the queries and results:

```bash
docker exec -it django python manage.py search_credentials frost --verbose
```

### Saving Full Results

By default, the tool only saves performance metrics. To save actual results:

```bash
docker exec -it django python manage.py search_credentials frost --output results.json --format json --save-results
```

## Performance Considerations (on 120M Credentials)

- **Term queries** are fastest but most restrictive (~0.2s for "frost")
- **Match queries** are very fast for exact matches (~0.01s)
- **Regexp queries** offer the best balance of speed and flexibility (~4.8s for case-insensitive "frost")
- **Wildcard queries** are comprehensive but can be slow for large result sets (~5.2s)
- **Case-insensitive queries** using bool/should are the slowest but most comprehensive (~10.0s)
- All queries use `track_total_hits: true` to get accurate counts

## Examples

1. Search for email addresses containing "admin":
   ```bash
   docker exec -it django python manage.py search_credentials admin --regexp --email-only --size 20
   ```

2. Search for exact password "123456":
   ```bash
   docker exec -it django python manage.py search_credentials 123456 --term --field password
   ```

3. Compare performance of different query types and save as markdown:
   ```bash
   docker exec -it django python manage.py search_credentials password --all --output password_perf --format md
   ```

4. Case-insensitive search for usernames with "Smith":
   ```bash
   docker exec -it django python manage.py search_credentials Smith --case-insensitive --field username
   ```

5. Get the 100 most recent credentials containing "company":
   ```bash
   docker exec -it django python manage.py search_credentials company --regexp --size 100 --sort date
   ```

## Interpreting Results

The tool provides:
- Number of matching credentials for each query type
- Time taken to execute each query
- Sample matching credentials
- Performance summary (hits/second)

## Troubleshooting

- If searches are timing out, try reducing the `--size` parameter
- For complex patterns, use `--regexp` rather than `--wildcard`
- If getting no results with `--match`, try other query types as the analyzer might not be configured correctly
- Use `--verbose` to see detailed information about the queries being run
- For memory-intensive searches, consider using a smaller `--size` and saving results incrementally
