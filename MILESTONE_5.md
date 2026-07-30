# Milestone 5: Smart Collections & Recommendation Engine

## Architecture

```
generate.py (static site generator)
    |
    +-- SmartCollectionService   (db/smart_collections.py)
    |       |
    |       +-- CollectionRepository (db/collection_repository.py)
    |               |
    |               +-- SQLite via SQLAlchemy models
    |
    +-- RecommendationEngine     (db/recommendation_engine.py)
    |       |
    |       +-- ProductService        (loads flat product dicts)
    |       +-- SmartCollectionService (collection membership)
    |       +-- product_engine        (ranking, diversity)
    |
    +-- templates/collection.html, collections.html
```

No existing services were refactored. Two new modules added:

### 1. `db/collection_repository.py`
Full CRUD for collections + product membership + rule evaluation engine.
- `create_collection`, `get_collection`, `update_collection`, `delete_collection`
- `search_collections` (filter by name, niche, visibility, featured, rule_type)
- `get_visible_collections`, `get_featured_collections`, `get_rule_collections`
- `add_product`, `remove_product`, `set_product_order`, `set_product_featured`
- `add_related`, `remove_related`
- `evaluate_rule` (static method) — evaluates a product against rule conditions

### 2. `db/smart_collections.py`
Service layer on top of `CollectionRepository`. Returns flat dicts.
- Full CRUD delegation
- Product membership management (add/remove/reorder/featured)
- Related collections management
- `refresh_rule_collections()` — evaluates all rule-based collections against all products
- `evaluate_product()` — checks a single product against all rules
- `seed_default_collections()` — creates 7 default rule-based collections:
  - Premium Helmets (score >= 85 AND category = Helmet)
  - Budget Friendly (price <= 2000)
  - Top Rated (rating >= 4.0 AND review_count >= 100)
  - Best Value Picks (score >= 75 AND price <= 5000)
  - Premium Riding Gear (price >= 5000 AND category in [Jackets, Gloves, ...])
  - Touring Essentials (category in [Saddle Bag, Tail Bag, ...])
  - Safety First (category in [Helmet, Disc Lock, Chain Lock, ...])

### 3. `db/recommendation_engine.py`
Grouped recommendations engine.
- `recommend_for_motorcycle(bike_slug)` — returns grouped recs for a bike
- `recommend_for_category(category)` — returns grouped recs for a category
- `recommend_for_product(product_slug)` — returns grouped recs for a product page
- Groups: **Protection**, **Style**, **Lighting**, **Touring**, **Maintenance**
- Uses `ProductService` for flat product dicts, `product_engine` for ranking/diversity

### 4. Generator integration (`generate.py`)
- Collections loaded at startup via `SmartCollectionService`
- `generate_collection_pages()` — renders collection index + individual pages
- Collection data available in `base_context` for templates
- Collection pages added to sitemap

## Rule DSL

Rules are JSON objects with conditions and logic:

```json
{
    "conditions": [
        {"field": "score", "op": ">=", "value": 85},
        {"field": "category", "op": "==", "value": "Helmet"},
        {"field": "price", "op": "<=", "value": 5000},
        {"field": "brand", "op": "in", "value": ["BrandA", "BrandB"]}
    ],
    "logic": "and"
}
```

Supported fields: `score`, `price`, `mrp`, `rating`, `review_count`, `status`, `brand`, `category`, `tag`
Supported operators: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`, `contains`

## Tests

- `python test_smart_collections.py` — 21 tests covering all CRUD, rule evaluation, and service-level operations
- `python test_recommendation_engine.py` — 8 tests covering group structure and empty-state handling

## Extending

1. **New rule fields**: Add to `_evaluate_condition` field_map in `collection_repository.py`
2. **New recommendation groups**: Add to `GROUP_CATEGORIES` in `recommendation_engine.py`
3. **New collections**: Use the API or add to `DEFAULT_RULE_COLLECTIONS` in `smart_collections.py`
