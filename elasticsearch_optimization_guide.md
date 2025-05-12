# Elasticsearch Search Optimization Guide for Credential Database

## Current System Performance

Our performance benchmarks on the ~120 million credential database show:

| Query Type | Pattern | Results | Time (s) | Hits/sec | 
|------------|---------|---------|----------|----------|
| Term | `frost` (exact match) | 360 | 0.234 | 1,539.3 |
| Regexp | `.*[fF][rR][oO][sS][tT].*` | 25,148 | 4.807 | 5,232.1 |
| Wildcard | `*frost*` | 25,148 | 5.220 | 4,818.1 |
| Match | `frost` | 360 | 0.014 | 25,749.0 |
| Case-insensitive | Combined wildcards | 25,148 | 10.024 | 2,508.9 |

## Recommended Elasticsearch Optimizations

### 1. Index Configuration Improvements

#### Add Custom Analyzers

```json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "credential_analyzer": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "credential_ngram"]
        }
      },
      "filter": {
        "credential_ngram": {
          "type": "ngram",
          "min_gram": 3,
          "max_gram": 4
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "string": {
        "type": "text",
        "fields": {
          "keyword": { "type": "keyword" },
          "analyzed": {
            "type": "text",
            "analyzer": "credential_analyzer"
          }
        }
      }
    }
  }
}
```

#### Increase Number of Shards

For better search parallelization, consider increasing the number of shards. The current index has only 1 shard:

```json
{
  "settings": {
    "number_of_shards": 5,
    "number_of_replicas": 1
  }
}
```

### 2. Query Optimization Techniques

#### Case-Insensitive Search Optimization

Current case-insensitive searches are slow. Instead of using combined wildcards or regexp:

```json
{
  "query": {
    "match": {
      "string.analyzed": "frost"
    }
  }
}
```

#### N-gram Indexing for Substring Searches

The n-gram filter in the custom analyzer will enable faster substring searches:

```json
{
  "query": {
    "match": {
      "string.analyzed": "frost"
    }
  }
}
```

#### Caching Frequent Queries

For frequently searched terms, enable query cache:

```json
{
  "query": {
    "term": {
      "string.keyword": "frost"
    }
  },
  "_source": false,
  "size": 0,
  "cached": true
}
```

### 3. Performance Tuning

#### JVM Heap Size

Increase JVM heap size to accommodate large indices (adjust based on available RAM):

```
-Xms4g -Xmx4g
```

#### Field Data Cache

For aggregations and sorting, increase field data cache:

```json
{
  "indices.fielddata.cache.size": "10%"
}
```

#### Search Thread Pool

Adjust search thread pool to optimize for search-heavy workloads:

```json
{
  "thread_pool.search.size": 10,
  "thread_pool.search.queue_size": 1000
}
```

### 4. Implementation Plan

1. Create a new index with the optimized configuration
2. Reindex data from the current index to the new index
3. Swap the alias to point to the new index
4. Test search performance with various query types
5. Fine-tune settings based on performance results

### 5. Expected Improvements

| Query Type | Current Time (s) | Expected Time (s) | Improvement |
|------------|------------------|-------------------|-------------|
| Case-insensitive | 10.024 | 0.5-1.0 | ~90% |
| Wildcard | 5.220 | 0.8-1.5 | ~80% |
| Regexp | 4.807 | 1.0-2.0 | ~70% |
| Term | 0.234 | 0.1-0.2 | ~30% |
| Match | 0.014 | 0.010-0.014 | ~0-30% |

## Conclusion

Implementing these Elasticsearch optimizations should significantly improve search performance across all query types, with the most dramatic improvements for case-insensitive and substring searches. The custom analyzers and increased shard count will enable more efficient parallel processing, while n-gram indexing will dramatically speed up substring matching.

These optimizations do come at a cost of increased index size and indexing time, but the performance benefits for search-heavy workloads will generally outweigh these costs.
