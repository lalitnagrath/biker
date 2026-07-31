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
- No database writer integration
- No CLI commands
- No sync log writing to database

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
- **ProductEngine**: 8 tests
- **KnowledgeGraph**: 24 tests
- **AmazonSearchService** (Phase 8.1): 11 tests
- **ProductImportService** (Phase 8.1): 9 tests
- **Control Center API** (Phase 8.1): 5 tests
- **Total**: 102 tests pass (run individually with system `python3`)

> Note: running all files in one `pytest test_*.py` invocation still hits the
> pre-existing `sys.modules` stub collision between `test_recommendation_engine.py`
> (stubs `db.smart_collections`) and `test_smart_collections.py`.

## Phase 8.1 — Product Discovery & Import Center

### Implementation Status
- **Milestone doc** (`MILESTONE_8.md`) defines Phase 8.1 scope; later phases planned
- **`db/amazon_search_service.py`** — keyword search (NOT URL) via CreatorsAPI SDK,
  returns import-ready flat dicts (category inferred, slug generated, status `draft`,
  affiliate URL built). Credentials from `AMAZON_CREATOR_CREDENTIAL_ID` /
  `AMAZON_CREATOR_CREDENTIAL_SECRET` env vars. Injected `api` for tests.
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
4. **Status filtering**: Not yet applied to ProductEngine
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
- **No database integration** - sync_results.json file logging only
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
