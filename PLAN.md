# Implementation Plan: Curated Product Library with Daily Amazon Sync

## Context

The motorcycle recommendation site currently stores products as flat JSON dicts
in `data/products/*.json`. Editorial data (pros, cons, ratings) and Amazon
data (price, reviews, availability) live in the same flat structure with no
separation. There is no product status system, no validation, no sync engine,
and no CLI management tool.

The existing `product_model.py` already enforces immutable identity vs mutable
commerce fields at the code level, and `product_matcher.py` already handles
deterministic matching. What's missing is the storage layer, sync engine, and
management tooling that the user has specified.

This plan builds those layers without breaking the existing 11 templates, the
recommendation engine, or the static site generator.

---

## Architecture Overview

```
data/products/helmets.json         # NEW structure: editorial + amazon + status
         |
product_library.py                 # Load, filter by status, validate, flatten
         |
    +----+----+
    |         |
generate.py   sync_engine.py      # Build uses library; sync updates amazon only
    |              |
templates/    bike.py (PA-API)     # Templates see flat dicts; sync fetches data
    |
site/         # Static output (unchanged)
```

---

## Files to Create

| File | Purpose |
|---|---|
| `product_library.py` | Core library: load, filter, validate, flatten, status management |
| `sync_engine.py` | Daily sync: fetch Amazon data, enrich products, preserve editorial |
| `products.py` | CLI: validate, sync, stats, import, export, find_duplicates |
| `data/products/.schema.json` | JSON Schema for product validation (optional reference) |

## Files to Modify

| File | Change |
|---|---|
| `data/products/accessories.json` | Migrate to new structure |
| `data/products/helmets.json` | Migrate to new structure |
| `data/products/maintenance.json` | Migrate to new structure |
| `generate.py` | Use `product_library.load_products()` instead of raw JSON loading |
| `product_engine.py` | Add status filter: only `status == "approved"` products pass through |

## Files NOT Modified

| File | Reason |
|---|---|
| `product_model.py` | Already has correct identity/commerce separation |
| `product_matcher.py` | Already handles deterministic matching correctly |
| `templates/*.html` | Flat dict access via `product.price` etc. continues to work |
| `static/js/main.js` | No changes needed |
| `static/css/style.css` | No changes needed |
| `bike.py`, `honda-cb350.py` | Amazon fetchers continue independently |

---

## Step 1: Define New Product JSON Structure

Each product JSON file becomes an array of products with clear separation:

```json
{
    "asin": "B0D9QTZYJW",
    "slug": "bobo-bm4-pro-plus",
    "title": "BOBO BM4 PRO Plus Jaw-Grip Phone Mount with Vibration Damper",
    "brand": "BOBO",
    "category": "Phone Mount",
    "type": "Handlebar Mount",
    "status": "approved",

    "editorial": {
        "score": 85,
        "pros": ["PRO+ vibration damper protects phone camera", ...],
        "cons": ["Vibration damper adds bulk", ...],
        "features": ["Vibration damper", "Jaw-grip", "Waterproof"],
        "fitment_notes": "Universal - fits all handlebars 22-32mm",
        "recommended_for": ["touring", "daily-commute"],
        "notes": "Best phone mount for camera protection"
    },

    "amazon": {
        "price": 1899,
        "mrp": null,
        "discount": null,
        "rating": 4.3,
        "review_count": 2100,
        "availability": "In Stock",
        "affiliate_url": "https://www.amazon.in/dp/B0D9QTZYJW?tag=xuy0834-21",
        "image": "images/products/bobo-bm4-pro-plus.jpg",
        "last_updated": null
    },

    "compatible_bikes": ["*"],

    "best_for": "Riders wanting secure phone mounting with camera vibration protection",
    "verdict": "The BOBO BM4 PRO Plus is the best phone mount..."
}
```

### Status Values

| Status | Appears in Engine? | Description |
|---|---|---|
| `draft` | No | Work in progress, not yet approved |
| `approved` | Yes | Active recommendation |
| `hidden` | No | Temporarily removed from display |
| `out_of_stock` | No | Currently unavailable |
| `discontinued` | No | Permanently removed |

### Mapping from Old to New

| Old Field | New Location |
|---|---|
| `pros`, `cons` | `editorial.pros`, `editorial.cons` |
| `editor_rating` | `editorial.score` |
| `best_for` | Top-level (kept for template compat) |
| `verdict` | Top-level (kept for template compat) |
| `price` | `amazon.price` |
| `rating` | `amazon.rating` |
| `reviews` | `amazon.review_count` |
| `affiliate_url` | `amazon.affiliate_url` |
| `image` | `amazon.image` |
| `compatible_bikes` | Top-level (editorial decision) |

---

## Step 2: Build `product_library.py`

Core module that manages the product library. Key functions:

### Loading & Flattening

```python
def load_products(products_dir: Path) -> list[dict]:
    """Load all product JSON files from the products directory.

    Returns flat dicts compatible with templates and product_engine.
    Each product dict includes:
    - Top-level: asin, slug, title, brand, category, type, status,
      compatible_bikes, best_for, verdict
    - Flattened: price, rating, reviews (alias for review_count),
      affiliate_url, image (alias for amazon.image)
    - Editorial: pros, cons, editor_rating (alias for editorial.score),
      features, fitment_notes, recommended_for, notes
    - Amazon metadata: availability, mrp, discount, last_updated,
      amazon_synced (boolean)
    """
```

The flattening layer is critical: templates access `product.price`,
`product.rating`, `product.reviews`, `product.image` etc. via attribute/dict
access. The `Product` class is a dict subclass, so we must produce flat dicts
that have these keys at the top level. The `amazon.last_updated` and
`editorial.*` nested data is preserved for the sync engine and validation.

### Filtering

```python
def approved_products(products: list[dict]) -> list[dict]:
    """Return only products with status == 'approved'."""

def active_products(products: list[dict]) -> list[dict]:
    """Return products that should appear on the website.

    Includes: approved, out_of_stock (shown with badge)
    Excludes: draft, hidden, discontinued
    """
```

### Validation

```python
def validate_products(products: list[dict]) -> dict:
    """Validate the entire product library.

    Checks:
    - Duplicate ASINs
    - Missing affiliate links (approved products)
    - Missing images (approved products)
    - Invalid prices (negative, zero for approved)
    - Missing categories
    - Missing editorial info (pros, cons, score)
    - Broken compatibility (empty compatible_bikes)
    - Products missing from any category

    Returns: {errors: [...], warnings: [...], stats: {...}}
    """
```

### Import/Export

```python
def import_from_legacy(products_dir: Path) -> None:
    """Migrate old flat JSON files to new structure."""

def export_products(products: list[dict], output_path: Path) -> None:
    """Export products to JSON (for backup/sharing)."""
```

### Stats

```python
def generate_stats(products: list[dict]) -> dict:
    """Generate comprehensive product library statistics.

    Returns:
    - total_products
    - by_category: {category: count}
    - by_brand: {brand: count}
    - by_status: {status: count}
    - average_rating
    - average_discount
    - out_of_stock_count
    - draft_count
    - discontinued_count
    - missing_editorial: [slugs]
    - missing_images: [slugs]
    - missing_affiliate: [slugs]
    - duplicate_asins: [{asin: ..., products: [...]}]
    """
```

---

## Step 3: Build `sync_engine.py`

The daily sync engine that updates Amazon data without touching editorial data.

### Sync Flow

```
1. Load product library
2. For each approved product with an ASIN:
   a. Look up current Amazon data (from PA-API or cached feed)
   b. Match product to Amazon record (using product_matcher)
   c. Update ONLY amazon.* fields:
      - price, mrp, discount
      - rating, review_count
      - availability
      - image (if changed)
      - affiliate_url (if updated)
      - last_updated = now
   d. NEVER touch:
      - editorial.* fields
      - status
      - compatible_bikes
      - category, brand, type
      - pros, cons, verdict, best_for
   e. Record sync log entry
3. Save updated product library
4. Generate sync report
```

### Key Design Decisions

1. **Sync uses `product_matcher.py`** for deterministic matching (ASIN > URL ASIN > title > brand+model). No fuzzy matching.

2. **Sync only processes `approved` products**. Draft products are not synced.

3. **Sync creates a backup** before writing (`products/*.json.bak`).

4. **Sync logs are saved** to `data/products/sync_log.json` with timestamps.

5. **Editorial data is immutable during sync**. If a sync accidentally tries to modify editorial fields, it's logged as an error and skipped.

### Sync Modes

```python
def sync_products(products_dir: Path, feed_path: Path, mode: str = 'full') -> dict:
    """Sync Amazon data into the product library.

    Modes:
    - 'full': Process all approved products
    - 'selective': Only products where last_updated > N days ago
    - 'asins': Only specific ASINs (for targeted updates)

    Returns sync report.
    """
```

---

## Step 4: Build `products.py` (CLI)

Management utility with these commands:

```
python products.py validate        # Validate entire library
python products.py sync            # Run daily Amazon sync
python products.py stats           # Print library statistics
python products.py import          # Migrate legacy JSON to new format
python products.py export          # Export library to JSON
python products.py find_duplicates # Find duplicate ASINs/titles
python products.py status <slug>   # Show/edit product status
python products.py list            # List all products
python products.py add             # Add a new product (interactive)
```

Each command prints clear, actionable output. Validation errors include
specific file paths and line references.

---

## Step 5: Update `generate.py`

Change the product loading path in `SiteGenerator.__init__`:

```python
# BEFORE:
self.data = load_all_data()  # loads raw JSON directly

# AFTER:
from product_library import load_products, approved_products
all_products = load_products(DATA_DIR / 'products')
self.data = load_all_data()
self.data['products'] = all_products
```

The `load_all_data()` function in generate.py loads ALL JSON including
products. We need to modify it so products go through the library loader
instead of raw JSON reading.

Specifically, in `load_all_data()` (generate.py:142-150), replace the raw
product loading with:

```python
from product_library import load_products
data['products'] = load_products(DATA_DIR / 'products')
```

The rest of generate.py continues to work unchanged because `load_products()`
returns flat dicts with all the same keys.

---

## Step 6: Update `product_engine.py`

Add status filtering at the entry point. Every function that accepts a
`products` list should filter out non-approved products at the top:

```python
def _filter_approved(products: list) -> list:
    """Return only products with status 'approved' (or no status for legacy compat)."""
    return [p for p in products if p.get('status', 'approved') == 'approved']
```

Apply this filter in:
- `recommend_products()` (line 712)
- `recommend_for_category()` (line 788)
- `recommend_sidebar_products()` (line 959)
- `filter_compatible_products()` (line 1058)
- `best_per_category()` (line 1096)
- `find_products_by_category()` (line 663)

This ensures no draft, hidden, or discontinued products ever appear on
the website.

---

## Step 7: Migrate Existing Product Data

Convert the 3 existing product files (11 total products) to the new format.

### accessories.json (4 products)
- BOBO BM4 PRO Plus: score=85, status=approved, price=1899
- BOBO BM14 PRO Plus: score=83, status=approved, price=1999
- Xiaomi Air Compressor 1S: score=80, status=approved, price=1999
- STRIFF EZ Air: score=75, status=approved, price=1679

### helmets.json (3 products)
- Studds Raider Super: score=75, status=approved, price=1345
- TVS Raider Helmet: score=78, status=approved, price=1550
- Studds RAY Super: score=72, status=approved, price=750

### maintenance.json (4 products)
- Motul 7100 10W40: score=90, status=approved, price=764
- Motul 3100 10W30: score=80, status=approved, price=520
- Motul C2 Chain Lube: score=85, status=approved, price=229
- Motul C1 Chain Cleaner: score=85, status=approved, price=420

Mapping:
- `editor_rating` -> `editorial.score`
- `pros`, `cons` -> `editorial.pros`, `editorial.cons`
- `price`, `rating`, `reviews` -> `amazon.price`, `amazon.rating`, `amazon.review_count`
- `affiliate_url` -> `amazon.affiliate_url`
- `image` -> `amazon.image`
- All existing products get `status: "approved"`
- New fields `editorial.features`, `editorial.fitment_notes`, `editorial.recommended_for`, `editorial.notes` populated from existing data or set to sensible defaults

---

## Step 9: Future-Ready Design

The architecture supports future extensions without structural changes:

### Price History
Add `amazon.price_history: [{date, price, mrp}]` array. Sync appends to it.
Product library exposes `get_price_history(asin, days)`.

### Price Drop Alerts
Compare `amazon.price` vs `amazon.price_history[-2].price`.
Product library exposes `get_price_drops(threshold_pct)`.

### Multiple Affiliate Networks
Extend `amazon` to `commerce` with nested sources:
```json
"commerce": {
    "amazon": { "price": 1899, "affiliate_url": "..." },
    "flipkart": { "price": 1799, "affiliate_url": "..." },
    "croma": { "price": 1899, "affiliate_url": "..." }
}
```
The sync engine's `COMMERCE_FIELDS` pattern already supports this.

### Version History
Add `version: 1` and `history: [...]` at product level.
Product library exposes `get_version_history(slug)`.

### Bulk Editing
CLI `products.py bulk-edit --category "Phone Mount" --set status=hidden`.
The flat dict structure supports this naturally.

---

## Implementation Order

1. **product_library.py** - Core module (loading, filtering, validation, stats)
2. **Migrate JSON files** - Convert existing 3 product files to new structure
3. **Update generate.py** - Switch to `product_library.load_products()`
4. **Update product_engine.py** - Add status filtering
5. **Verify existing pages** - Run `python generate.py`, check all pages render
6. **sync_engine.py** - Build the sync engine
7. **products.py** - Build the CLI tool
8. **Run full validation** - `python products.py validate` + `python generate.py`

---

## Verification

After implementation, verify:

1. `python generate.py` produces identical output for all existing pages
2. `python products.py validate` passes with no errors
3. `python products.py stats` shows correct counts
4. `python products.py sync` runs without modifying editorial data
5. Product engine only recommends `approved` products
6. Templates render product cards correctly (price, rating, image, affiliate URL)
7. No template changes were required
8. `product_model.py` IdentityError is never triggered during sync
