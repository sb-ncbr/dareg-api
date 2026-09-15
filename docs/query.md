## Generic Search API

### Endpoint
`POST /api/v1/query/`

### Description
Search across registered models using trigram similarity or metadata filters. Returns paginated results with highlights.

### Request Body (JSON)

| Field       | Type     | Required | Description |
|-------------|----------|----------|-------------|
| `q`         | string   | no       | Query string for trigram full-text search. |
| `filters`   | object   | no       | Filter conditions using a JSON-like query language. |
| `schema`    | string   | no       | Schema UUID to validate metadata filters (optional). |
| `model`     | string   | no       | Restrict to a specific model name (e.g., `Dataset`, `Project`). |

### Filter Operators
- `$eq`, `$ne`: equals / not equals
- `$gt`, `$gte`, `$lt`, `$lte`: numeric comparisons
- `$contains`: substring match
- `$regex`: case-insensitive search
- `$in`, `$nin`: list inclusion / exclusion
- `$null`: test for null value (boolean)
- `$and`, `$or`, `$not`: logical combinations

### Metadata Filters
To filter nested JSON fields in `metadata`, use dot notation:
```json
{
  "filters": {
    "metadata.title": { "$regex": "membrane" },
    "metadata.year": { "$gte": 2020 }
  }
}
```

You can combine filters:
```json
{
  "$or": [
    { "metadata.title": { "$regex": "membrane" } },
    { "metadata.year": { "$gte": 2020 } }
  ]
}
```

### Example 1: Basic Text Search
```json
{
  "q": "lipid"
}
```

### Example 2: Filter Without Query
```json
{
  "filters": {
    "metadata.publication_year": { "$gte": 2020 }
  },
  "schema": "d7dbdd5e-b69a-4243-8c4d-ce01a9346386",
  "model": "Dataset"
}
```

### Example 3: Combined Query and Filters
```json
{
  "q": "membrane",
  "filters": {
    "$or": [
      { "metadata.title": { "$regex": "membrane" } },
      { "metadata.publication_year": { "$gte": 2020 } }
    ]
  },
  "schema": "d7dbdd5e-b69a-4243-8c4d-ce01a9346386",
  "model": "Dataset"
}
```

### Example 4: Complex Chaining of Filters
```json
{
  "model": "Dataset",
  "q": "lipid",
  "filters": {
    "$and": [
      {
        "$not": {
          "tags": {
            "$in": ["draft", "deprecated"]
          }
        }
      },
      {
        "metadata.project_type": {
          "$eq": "simulation"
        }
      }
    ]
  }
}
```

### Response Format
Paginated list of matching objects with highlights:
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 42,
      "text": "Dataset about membrane lipids",
      "highlights": [
        "name: Dataset about membrane lipids",
        "metadata.title → membrane"
      ],
      "model": "Dataset"
    }
  ]
}
```

### Notes
- Only models that define `trigram_search_fields` will support query string `q`.
- Metadata filters require a valid schema to determine allowed field names and types.
- User permissions are enforced: results include only viewable objects.

