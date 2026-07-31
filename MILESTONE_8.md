# Milestone 8: Product Discovery & Import Center

## Objective

Products should enter the system **only through the Control Center**.

No more editing JSON files by hand. An editor searches Amazon by keyword,
reviews the results, selects the products worth curating, and imports them
straight into the database.

Milestone 8 is split into phases. **Phase 8.1** built the search + import
foundation; **Phase 8.2** completed the discovery workflow (filters,
pagination, preview).

### Phase 8.1 Scope

- Build an **Amazon Search service** — search by **keyword**, not by URL.
- Display search results in the Control Center.
- Allow selecting one or multiple products.
- Import selected products into the database.
- Download product images.
- **Do not** generate HTML yet.
- **Do not** modify existing products.
- Use the existing Service layer.
- Add tests and documentation.

## Architecture

```
editorial/index.html (Control Center)
    |
    +-- GET /api/amazon/search?keyword=...
    |       |
    |       +-- AmazonSearchService  (db/amazon_search_service.py)
    |               |
    |               +-- CreatorsAPI SDK (search_items by keyword)
    |               +-- product_library (category inference, slugs)
    |
    +-- POST /api/import   { products: [flat dicts], download_images: bool }
            |
            +-- ProductImportService  (db/import_service.py)
                    |
                    +-- DatabaseWriter (db/writer.py)  -> SQLite (bikereview.db)
                    +-- static/images/products/        -> downloaded images
```

### New modules

| File | Purpose |
|---|---|
| `db/amazon_search_service.py` | Keyword search against Amazon (CreatorsAPI). Returns import-ready flat dicts. |
| `db/import_service.py` | Writes selected products to SQLite, downloads images, never edits existing products. |

### Modified files

| File | Change |
|---|---|
| `editorial/server.py` | New API endpoints `/api/amazon/search` and `/api/import`. |
| `editorial/index.html` | New "Amazon Import" page with keyword search, result cards, multi-select, import action. |

## AmazonSearchService

```python
svc = AmazonSearchService()            # credentials from env / constants
result = svc.search("motorcycle helmet", item_count=20)

# -> {
#     "keyword": "motorcycle helmet",
#     "page": 1,
#     "count": 20,
#     "results": [ { "asin", "slug", "title", "brand", "category",
#                    "type", "status": "draft", "price", "mrp",
#                    "discount", "rating", "review_count", "reviews",
#                    "availability", "affiliate_url", "image",
#                    "amazon_image_url", ... }, ... ]
# }
```

- Each result is a **flat product dict** in the exact format that
  `DatabaseWriter.save_product()` consumes, so search results can be handed
  straight to the importer.
- Category is inferred from the title via `product_library.infer_category_from_title`
  and converted to its display name (`helmet` → `Helmet`).
- Status is always `draft` — imported products need editorial review before
  they ever appear on the site.
- The service accepts an injected `api` object for tests (no network needed).
- Missing credentials raise `AmazonSearchError` with a clear message.

## ProductImportService

```python
svc = ProductImportService()
known = svc.existing_asins()           # ASINs already in the library
report = svc.import_products(flat_products, download_images=True)

# -> {
#     "submitted": 3,
#     "imported": [ ...new product flat dicts... ],
#     "skipped_existing": [ ...products already in the DB... ],
#     "failed": [ {"asin", "title", "error"} ],
#     "images": { "downloaded": 2, "skipped": 0, "failed": 1 },
# }
```

### Import rules

1. **Existing products are never modified.** Any ASIN already in the
   `products` table is skipped and reported as `skipped_existing`.
2. **New products are inserted with `status = "draft"`.** They only appear on
   the website after an editor approves them.
3. **Images are downloaded** to `static/images/products/{slug}.jpg`; the local
   path is stored on the `Image` row (same convention as the curated catalog).
4. Upserts go through `DatabaseWriter` (db/writer.py) — brand, category,
   editorial score, price history, and compatibility rows are created.

## Control Center API

```text
GET  /api/amazon/search?keyword=motorcycle+helmet&item_count=20
     # search results as flat dicts, each with "in_library": bool

POST /api/import
     { "products": [ ...flat dicts... ], "download_images": true }
     # import report (see ProductImportService)
```

The search endpoint marks every result with `in_library`, so the UI can show
"Already in library" and prevent accidental duplicates.

## Control Center UI

New sidebar item **Amazon Import** under "Control Center":

- Keyword search box.
- Result cards: image, title, brand, price, rating, reviews, category,
  "Already in library" badge.
- Per-result checkbox + "Select all".
- "Import selected (N)" button that POSTs the chosen flat dicts to
  `/api/import` and renders the report (imported / skipped / failed, image
  download summary).

## Tests

```bash
python test_amazon_search_service.py   # keyword search + flat conversion
python test_product_import_service.py  # DB import + image download rules
python test_control_center_api.py      # FastAPI endpoints
```

### Coverage

| Group | Verifies |
|---|---|
| Search service | keyword → API call, flat dict shape, price/rating extraction, affiliate URL fallback, empty results, missing keyword, credentials error, injected fake API |
| Import service | new products inserted as `draft`, existing ASINs skipped untouched, image download + local path, failure handling, report structure |
| API | `/api/amazon/search` returns results with `in_library`, `/api/import` returns a report, error responses |

## Status (Phase 8.1 — implemented)

- [x] `db/amazon_search_service.py` — keyword search via CreatorsAPI SDK, flat dicts, injected API
- [x] `db/import_service.py` — SQLite import, skip existing ASINs, image download + link
- [x] Control Center endpoints: `GET /api/amazon/search`, `POST /api/import`
- [x] Control Center UI: "Amazon Import" page (search, multi-select, import report)
- [x] Tests: 11 search + 9 import + 5 API (all pass with system `python3`)
- [x] Docs: `docs/CURRENT_STATE.md` updated
- [ ] Live credentials wired in the running environment (search returns 502 until
      `AMAZON_CREATOR_CREDENTIAL_ID` / `AMAZON_CREATOR_CREDENTIAL_SECRET` are set)
- [ ] Live smoke test of an actual Amazon import against the production DB

## Phase 8.2 — Full Discovery Workflow

### Scope

Complete the Amazon product discovery workflow so it becomes the **primary way
new products enter the system**:

- Search Amazon by keyword.
- Optional **category filter** and **brand filter**.
- **Pagination** with total result count.
- Product cards with image, title, price, rating, review count and **ASIN**.
- Show whether a product **already exists** in the database (`in_library`).
- **Preview before import** (detail modal, confirm step).
- Import one or multiple selected products.
- Duplicate detection via ASIN (existing ASINs skipped, never modified).
- Imported products are created as **Draft**; editorial fields stay empty until
  reviewed.
- Preserve the existing service/repository architecture.

### Changes

| File | Change |
|---|---|
| `db/amazon_search_service.py` | `search()` accepts `category`/`brand` filters, returns `total` (Amazon `totalResultCount`), `categories`, `brands` facets; `_matches_filters()` helper |
| `editorial/server.py` | `/api/amazon/search` accepts `category` and `brand` query params |
| `editorial/index.html` | Filter dropdowns (category/brand), pagination bar, ASIN on cards, Preview modal + confirm-import flow |

### API

```text
GET /api/amazon/search?keyword=motorcycle+helmet&item_count=20&page=2&category=Helmet&brand=Steelbird
     # returns { keyword, page, count, total, categories, brands, results }
```

- `category` matches the display name or canonical form (e.g. `Helmet` or `helmet`).
- `brand` matches the exact brand name (case-insensitive).
- `categories`/`brands` facets come from the unfiltered page so dropdowns stay
  stable while filtering.

### Tests

```bash
python test_amazon_search_service.py   # + category filter, brand filter, combined filters, facets, total
python test_control_center_api.py      # + category/brand/pagination params forwarded
python test_product_import_service.py  # unchanged
```

## Future Phases (not in this milestone)

- Editorial review + approve flow for imported drafts.
- Automatic editorial generation (pros/cons/verdict) for imported products.
- Post-import HTML generation and site refresh.
- Price-history tracking after import.
- URL-based (ASIN/URL) import — Phase 8.1 is keyword-only.
