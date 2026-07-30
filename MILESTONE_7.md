# Milestone 7: Website Generation Engine 2.0

## Objective

Upgrade the static site generator from hardcoded sections and content to a
fully **data-driven** engine that reads everything from the database
(Knowledge Graph + Smart Collections + Products).  The engine works for any
future niche without code changes.

## What Changed

### New file: `db/generator_engine.py`

The `GeneratorEngine` class replaces the hardcoded data-building logic inside
`SiteGenerator` with database-driven queries.

| Before (generate.py) | After (GeneratorEngine) |
|---|---|
| `build_motorcycle_editorial()` — hardcoded FAQ text, use cases, buyer setups | `get_faqs(slug)` — reads from KG `MotorcycleFAQ` table |
| Hardcoded `accessory_nav` (5 fixed categories) | `build_page_sections(bike)` — reads from `UpgradeSection` table |
| Hardcoded `maintenance_schedule` (4 entries) | `build_comparison_table(ids)` — reads specs from `Motorcycle` table |
| Hardcoded `sidebar_similar_bikes` — type-based filter | `get_related_motorcycles(slug)` — reads from `MotorcycleRelation` table |
| Hardcoded `recommended_products` rewrite (100+ lines) | `get_recommended_products(slug)` — reads from `MotorcycleRecommendedProduct` table |
| Hardcoded breadcrumbs in every generator method | `build_breadcrumbs(page_type, **kwargs)` — single source of truth |
| Motorcycles loaded from JSON files | Motorcycles from KG service (SQLite) |

### What stays the same

- `generate.py` is NOT refactored — the engine is additive.
- All existing templates (`motorcycle.html`, `collection.html`, etc.)
  continue to work.
- All 77 existing tests pass without modification.

## Architecture

```
GeneratorEngine
 ├── MotorcycleKnowledgeGraphService  (motorcycles, tags, FAQs, sections, relations)
 ├── SmartCollectionService           (collections, featured collections)
 └── ProductService                   (product flat dicts)
```

Every public method returns **flat dicts** (never SQLAlchemy models).

## Engine API

### Motorcycle pages

```python
engine = GeneratorEngine()

# All motorcycles for listing pages
bikes = engine.get_all_motorcycles()

# Single motorcycle with all relationships
bike = engine.get_motorcycle("honda-cb350")

# Dynamic sections from UpgradeSection table
sections = engine.build_page_sections(bike, max_products_per_section=6)

# Comparison table from any set of motorcycle IDs
table = engine.build_comparison_table([1, 2, 3])
```

### Editorial data (from KG)

```python
faqs = engine.get_faqs("honda-cb350")        # MotorcycleFAQ table
tags = engine.get_tags("honda-cb350")         # MotorcycleTag table
related = engine.get_related_motorcycles("honda-cb350")  # MotorcycleRelation
```

### Products and Collections

```python
recs = engine.get_recommended_products("honda-cb350")
cols = engine.get_motorcycle_collections(bike_id)
all_cols = engine.get_all_collections()
featured = engine.get_featured_collections()
```

### Index / Listing data

```python
index_data = engine.build_motorcycle_index_data()
# Returns: { motorcycles, brands_grouped, type_counts, total_count }
```

### Breadcrumbs (single source of truth)

```python
engine.build_breadcrumbs("motorcycle", brand="Honda", model="CB350")
# → [{"name": "Home", "url": "./index.html"},
#     {"name": "Motorcycles", "url": "../motorcycles/index.html"},
#     {"name": "Honda CB350"}]

engine.build_breadcrumbs("collection", name="Best Safety Gear")
engine.build_breadcrumbs("category", name="Helmets")
engine.build_breadcrumbs("motorcycles_index")
```

### Seeding test data

```python
bike = engine.seed_motorcycle("Honda", "CB350", "honda-cb350",
                               tags=["retro"], faqs=[...])
engine.seed_upgrade_sections()
engine.add_motorcycle_to_section(bike["id"], [1, 2, 3])
engine.add_recommended_product(bike["id"], product_id)
```

## Dynamic Sections (no hardcoded categories)

The upgrade-sections system is fully database-driven:

1. **`UpgradeSection`** table stores: Protection, Style, Lighting, Touring,
   Comfort, Maintenance — each with a slug, icon, description, sort_order.
2. **`MotorcycleUpgradeSection`** junction assigns sections to motorcycles.
3. **`ProductUpgradeSection`** junction assigns products to sections.
4. `build_page_sections()` reads all three and returns structured data.

Adding a new section = adding a row to `UpgradeSection`. No code changes.

## Niche Agnostic

The engine works for any niche because:

- Section names come from `UpgradeSection`, not hardcoded strings.
- Breadcrumbs use dynamic page type + kwargs, not hardcoded labels.
- Comparisons read spec fields from the model, not hardcoded field names.
- Tags, FAQs, related entities all come from junction tables.
- Products are looked up by upgrade section membership, not category filters.

**Tested**: `test_niche_agnostic()` creates a "Generic Model X" scooter with
electric tags, assigns upgrade sections, builds page sections — everything
works without any motorcycle-specific logic.

## Files

| File | Lines | Purpose |
|---|---|---|
| `db/generator_engine.py` | ~270 | Engine class with 18 public methods |
| `test_generator_engine.py` | ~290 | 24 tests covering all engine features |

## Test Coverage (24 tests)

| Group | Tests | What it verifies |
|---|---|---|
| Motorcycle CRUD | 4 | create, fetch, not-found, multiple |
| Page Sections | 3 | empty sections, populated sections, max-products |
| Comparison Table | 2 | empty, populated |
| Breadcrumbs | 4 | motorcycle, index, collection, category |
| Editorial data | 2 | tags, FAQs |
| Related entities | 2 | recommended products, related motorcycles |
| Collections | 2 | empty, get-all |
| Index data | 1 | grouping and counts |
| Niche agnostic | 1 | no hardcoded logic |
| Edge cases | 3 | max products, no products in section, missing motorcycle |

## Running the Tests

```bash
cd biker
python test_generator_engine.py        # 24 tests
python test_smart_collections.py       # 21 tests
python test_recommendation_engine.py   # 8 tests
python test_knowledge_graph.py         # 24 tests
```

All 77 tests pass.
