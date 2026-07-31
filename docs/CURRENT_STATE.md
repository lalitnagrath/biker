# CURRENT_STATE.md

## Product Library

### Implementation Status
- **Core module created** (`product_library.py`) with loading, filtering, validation, stats, import/export
- **Not yet implemented**: migrate_json.py (migration for old data)

### Key Features
- **Two-level taxonomy**: `(category, subcategory)` from two-level taxonomy system
- **Status management**: `draft`, `approved`, `review`, `hidden`, `out_of_stock`, `discontinued`
- **Quality pipeline**: Score products, auto-assign status
- **Normalization**: `CANONICAL_CATEGORIES`, `CATEGORY_ALIASES`, `CATEGORY_DISPLAY`

### Filters
- `approved_products()` - Only products with status `approved`
- `active_products()` - `approved` + `out_of_stock` (shown with badge)
- `recommendable_products()` - `approved` + `review`

## Sync Engine

### Implementation Status
- **Core sync engine** (`sync_engine.py`) exists with:
  - Amazon feed loading
  - Product matching (ASIN, URL, title, brand+model)
  - Sync validation (safe updates only)
  - Sync result reporting

### Key Features
- **Sync safety**: Validates sync doesn't touch immutable fields
- **Risk mitigation**: No editorial modifications during sync
- **Sync modes**: `full`, `selective`, `asins`
- **Logging**: Sync log with timestamped entries

### Limitations
- **No database writer integration**
- **No CLI commands**
- **No sync log writing to database**

## CLI Tool

### Implementation Status
- **CLI structure** (`products.py`) exists but minimal implementation
- **Commands defined**: validate, sync, stats, import, export, find_duplicates, status, list, add
- **Commands implemented**: None (stubbed)

### Limitation
- CLI needs implementation

## Generator Engine

### Implementation Status  
- **Fully implemented** (`db/generator_engine.py`) with:
  - 18 public methods
  - Integration with 3 services
  - Support for motorcycle pages, collections, products
  - Niche-agnostic design

### Key Features
- **Dynamic sections**: Reads from `UpgradeSection` table
- **Comparison table**: Builds specs tables for any motorcycle set
- **Breadcrumbs**: Single source of truth
- **Related entities**: Products, motorcycles, FAQs, tags
- **Seeding**: Test data creation APIs

## Test Coverage

- **GeneratorEngine**: 24 tests
- **SmartCollections**: 21 tests  
- **product_engine**: 8 tests
- **KnowledgeGraph**: 24 tests
- **AmazonSearchService** (Phase 8.1 + 8.2): 18 tests
- **ProductImportService** (Phase 8.1): 9 tests
- **Control Center API** (Phase 8.1 + 8.2): 6 tests
- **Total**: 110 tests pass (run individually with system `python3`)

> Note: running all files in one `pytest test_*.py` invocation still hits the
> pre-existing `sys.modules` stub collision between `test_recommendation_engine.py`
> (stubs `db.smart_collections`) and `test_smart_collections.py`.

## Phase 8.1 — Product Discovery & Import Center

### Implementation Status
- **Milestone doc** (`MILESTONE_8.md`) defines Phase 8.1 + 8.2 scope
- **`db/amazon_search_service.py`** — keyword search (NOT URL) via CreatorsAPI SDK,
  returns import-ready flat dicts (category inferred, slug generated, status `draft`,
  affiliate URL built). Credentials resolve through `amazon_credentials.py` — the
  single source of truth shared with `bike.py` / `honda-cb350.py` (explicit args,
  then env vars, then built-in defaults). Injected `api` for tests.
- **`db/import_service.py`** — writes flat dicts straight into SQLite via
  `DatabaseWriter`; skips existing ASINs untouched; downloads images to
  `static/images/products/{slug}.jpg` and links them via the `Image` model.
- **Control Center**: `GET /api/amazon/search?keyword=...` returns results with
  `in_library` flag; `POST /api/import` returns `{submitted, imported,
  skipped_existing, failed, images}` report. New "Amazon Import" page in
  `editorial/index.html` (keyword search, multi-select, select all, import report).

### Key Rules (Phase 8.1)
- New products always enter with `status = "draft"` — editorial review before site visibility
- Existing ASINs are **never modified**; reported as `skipped_existing`
- No HTML generation — templates are presentation-only
- Search by keyword only (URL-based import is a later phase)

## Phase 8.2 — Full Discovery Workflow

### Implementation Status
- **Filters**: `/api/amazon/search` accepts `category` and `brand` query params;
  `db/amazon_search_service.search()` filters the current page via `_matches_filters()`
  (category matches display name or canonical form; brand is case-insensitive exact).
- **Pagination**: search returns `total` (Amazon `totalResultCount`, falls back to
  count), plus `categories` / `brands` facet lists from the unfiltered page so
  dropdowns stay stable while filtering.
- **UI** (`editorial/index.html`): category + brand dropdowns, pagination bar
  (Prev/Next, page info), ASIN shown on every product card, and a **Preview
  before import** modal (full product details, cancel/confirm).
- **Duplicate detection**: ASIN-based; existing products show an "Already in
  library" badge and are reported as `skipped_existing` by the import service.

### Key Rules (Phase 8.2)
- Imported products are always **Draft**; editorial fields remain empty until reviewed
- Filters/pagination are server-side; the Control Center never filters client-side
- Amazon discovery is the **primary** way new products enter the system

## Migration Status

### Product Data
- **New structure defined** but existing JSON files not yet migrated
- **Old structure**: Flat dicts (pros, cons, price in top-level)
- **New structure**: Nested `editorial` + `amazon` fields

### Files in Current State
- `data/products/accessories.json` - Not migrated (4 products)
- `data/products/helmets.json` - Not migrated (3 products)
- `data/products/maintenance.json` - Not migrated (4 products)

## Missing Components

1. **Database migration**: `product_library.import_from_legacy()` not implemented
2. **CLI implementation**: `products.py` commands not implemented
3. **Product Library migration**: 11 products not migrated to new structure
4. **Status filtering**: Not yet applied to `product_engine`
5. **Template updates**: No changes needed (templates accept flat dicts)

## Recommendation Engine Status

### Implementation Status
- **Fully functional** (`product_engine.py`)
- **Modern architecture**: Completely rewritten in v2
- **No motorcycle-specific logic**: Works for any niche
- **Department-agnostic**: Supports products, accessories, maintenance

### Core Features
- **Relevance scoring**: Editorial signal + rating + reviews + price
- **Brand diversity**: Max 2 per brand per category
- **Category matching**: Supports category, type, keyword matching
- **Compatibility filtering**: Motorcycle-specific matching
- **Universal categories**: Products that fit any motorcycle (helmets, gloves, etc.)
- **Bike-specific categories**: Need compatibility matching (crash guards, etc.)

## Sync Engine Status

### Product Library Integration
- **Fully implemented** - sync_engine.py uses product_library.py
- **Status filtering** - Only syncs approved products
- **Amazon data enrichment** - Updates price, rating, reviews, availability
- **Safety validation** - Never modifies editorial data
- **Deterministic matching** - Uses product_matcher.py

### Current Limitations
- **No database integration** - `data/products/sync_log.json` file logging only
- **No backup** - products/*.json.bak backups not implemented
- **No CLI commands** - sync_engine not exposed via CLI
- **Limited logging** - sync results not fully tracked

## Best Practices

### Identity & Commerce Separation
- **Identity fields**: asin, slug, title, brand, category, type, specifications, pros, cons, features (immutable)
- **Commerce fields**: price, mrp, discount, affiliate_url, amazon_url, image_url, rating, review_count, bestseller, amazon_choice, bought_last_month, availability (mutable)
- **Enrichment**: Only through `product.enrich()` method

### Product Status System
- **Approved**: Active recommendation
- **Review**: Queued for editorial review
- **Draft**: Work in progress
- **Hidden**: Temporarily removed
- **Out of stock**: Available with badge
- **Discontinued**: Permanently removed

### Sync Safety
- **Immutable fields**: Must never change during sync
- **Safe updates**: Only touch SYNCABLE_FIELDS
- **Validation**: _validate_sync_safety() prevents edits to editorial fields
- **Logging**: All changes logged with old/new values

## Motorcycle Compatibility Engine — Milestone 9

### Implementation Status
- **In Progress** — Building compatibility system

### Current Database Schema
- **Motorcycles** table (`db/models.py`) — motorcycle entities with specs
- **Products** table (`db/models.py`) — product catalog (helmets, gloves, etc.)
- **ProductMotorcycle** table (`db/models.py:354`) — existing compatibility link
  - Simple product-to-motorcycle connection
  - Fields: `id`, `product_id`, `motorcycle_id`, `confidence`, `match_strategy`, `notes`
  - Supports universal products (helmets, gloves) + category-specific matching

### Scope for Phase 9

#### 1. Create Accessory Type Model
- Model: `AccessoryType` (
  - `id`: Primary key
  - `name`: Unique, like "Crash Guard", "Leg Guard", etc.
  - `slug`: URL-friendly identifier
  - `description`: Optional details
  - `created_at`: Timestamp
- Product belongs to one AccessoryType (optional for universal products)

#### 2. Enhance ProductCompatibility Model
- **File**: `db/models.py`
- **Base on**: `ProductMotorcycle` with enhanced fields
- Fields:
  - `product_id`, `motorcycle_id` (Foreign keys)
  - `fitment_status`: Enum with "Verified", "Manufacturer Confirmed", "AI Suggested", "Universal", "Requires Modification", "Not Compatible"
  - `confidence`: Float (0.0-1.0)
  - `verified`: Boolean flag
  - `installation_notes`: Text
  - `source`: String ("manual", "ai", "manufacturer")
  - `created_at`: Timestamp

#### 3. Create Supporting Models
- `FitmentStatus` — Enum (INSERT after AccessoryType)

#### 4. Extend Repositories & Services
- `ProductCompatibilityRepository` — service for compatibility operations
- `AccessoryTypeRepository` — service for accessory type management
- Update `MotorcycleService` — add compatible products filtering
- Update `ProductService` — add motorcycles filtering by accessory type

#### 5. Add Tests

#### 6. Update Documentation
- Current State document
- API documentation
- Feature documentation

### Architecture Notes

#### Relationships
- **One-to-Many**: AccessoryType → Products (optional)
- **Many-to-Many**: Product ↔ Motorcycle (via ProductCompatibility)

#### Query Patterns
```python
# Find compatible products for a motorcycle
service.find_compatible_products(motorcycle_id)

# Find motorcycles that accept a product
service.find_motorcycles_for_product(product_id)

# Filter by accessory type
service.find_compatible_by_accessory_type(accessory_type_id)

# Get compatibility details
service.get_compatibility_details(product_id, motorcycle_id)
```

#### Service Layer Design
```python
class ProductCompatibilityService:
    def find_compatible_products(self, motorcycle_id: int, **filters) -> List[Product]:

    def find_motorcycles_for_product(self, product_id: int, **filters) -> List[Motorcycle]:

    def add_compatibility(self, product_id: int, motorcycle_id: int, data: dict) -> ProductCompatibility:

    def update_compatibility(self, product_id: int, motorcycle_id: int, data: dict) -> ProductCompatibility:

    def delete_compatibility(self, product_id: int, motorcycle_id: int) -> bool
```

### Integration Points

#### Motorcycle Pages
- **Filter by accessory type**: Show compatible products by type (crash guards, leg guards, etc.)
- **Quick access**: Direct product links with installation notes

#### Product Pages
- **Show compatibility**: Multiple motorcycles and fitment details
- **Filter by type**: Products for specific accessory types

#### Amazon Import
- **Import with compatibility**: Set default fitment_status as "AI Suggested"
- **Modify existing**: Update ProductMotorcycle entries during sync

#### Upgrade Garage
- **Manage compatibility**: Add/edit compatibility relationships
- **Filter by vehicle**: Find suitable upgrades for specific bikes

#### Bike Configurator
- **Enforce rules**: Validate compatibility based on fitment_status
- **Recommend parts**: Suggest compatible accessories based on vehicle specs

### Implementation Plan

#### Phase 1: Database Models
1. **Create `AccessoryType` model** in `db/models.py`
2. **Extend `ProductMotorcycle`** with new fields
3. **Create `FitmentStatus` enum** for status values

#### Phase 2: Repository Layer
1. **`ProductCompatibilityRepository`** in `db/motorcycle_repository.py`
2. **`AccessoryTypeRepository`** in new `db/accessory_type_repository.py`

#### Phase 3: Service Layer
1. **`ProductCompatibilityService`** in new `db/product_compatibility_service.py`
2. **`AccessoryTypeService`** in new `db/accessory_type_service.py`

#### Phase 4: Tests
1. **Unit tests** for new models and services
2. **Integration tests** for compatibility features
3. **E2E tests** for UI integration

#### Phase 5: Updates
1. **`CURRENT_STATE.md`** — Update with milestone 9 progress
2. **Documentation** — Add architecture and API docs

### Key Design Decisions

#### Separation of Concerns
- **Compatibility**: Filtered by accessory type + fitment status
- **Installation**: Notes and confidence scores
- **Source tracking**: Manual vs AI vs manufacturer data

#### Query Optimization
- **Index**: Composite indexes on `(product_id, motorcycle_id)` and `(motorcycle_id, fitment_status)`
- **Filtering**: Support efficient lookups by accessory type, status, and motorcycle

#### Backward Compatibility
- **Reuse**: Existing `ProductMotorcycle` table with enhanced structure
- **Migration**: Phase 9 migration script to add new columns
- **Optional**: AccessoryType association remains optional (universal products)
