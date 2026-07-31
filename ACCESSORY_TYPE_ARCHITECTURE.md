# AccessoryType Architecture

## Overview

AccessoryType is a first-class entity in the Biker product catalog system. It provides a dedicated taxonomy for motorcycle accessory products, independent from the existing product category system. Each product can optionally reference exactly one accessory type.

---

## Database Schema

### AccessoryType Table (`accessory_types`)

| Column        | Type               | Constraints                          | Description                              |
|---------------|--------------------|--------------------------------------|------------------------------------------|
| id            | Integer            | PRIMARY KEY                          | Unique identifier                        |
| name          | String(255)        | NOT NULL, UNIQUE, INDEX              | Display name (e.g., "Bar End Mirror")    |
| slug          | String(255)        | NOT NULL, INDEX                      | URL-friendly identifier                  |
| description   | Text               | nullable                             | Human-readable description               |
| icon          | String(100)        | nullable                             | Icon reference for UI rendering          |
| is_active     | Boolean            | NOT NULL, DEFAULT True               | Soft-delete / deactivate flag            |
| created_at    | DateTime           | DEFAULT datetime.utcnow              | Record creation timestamp                |
| updated_at    | DateTime           | DEFAULT datetime.utcnow, auto-update | Last modification timestamp              |

### Product Table — Added Columns

| Column              | Type                      | Constraints                          | Description                              |
|---------------------|---------------------------|--------------------------------------|------------------------------------------|
| accessory_type_id   | Integer                   | FOREIGN KEY (`accessory_types.id`)   | Nullable; links product to an accessory type |
| compatible_bikes    | JSON                      | nullable                             | Array of motorcycle slugs this product is compatible with |
| universal           | Boolean                   | NOT NULL, DEFAULT False              | If true, product appears on every bike page |

### UpgradeSection Table — Added Columns

| Column              | Type                      | Constraints                          | Description                              |
|---------------------|---------------------------|--------------------------------------|------------------------------------------|
| accessory_type_id   | Integer                   | FOREIGN KEY (`accessory_types.id`)   | Nullable; links upgrade section to type  |

---

## Product Relationship to AccessoryType

### How It Works

A `Product` references zero or one `AccessoryType` via the `accessory_type_id` foreign key:

```
Product.accessory_type_id  ──►  AccessoryType.id
```

- **One-to-Many**: One `AccessoryType` can have many `Product` records.
- **Nullable**: `accessory_type_id` allows `NULL`, so existing products without an accessory type are unaffected.
- **Back-populates**: The `Product.accessory_type` relationship provides convenient ORM access to the parent `AccessoryType`.

### Product Model Excerpt (`db/models.py`)

```python
class Product(Base):
    __tablename__ = "products"
    # ... existing columns ...

    accessory_type_id = Column(Integer, ForeignKey("accessory_types.id"), nullable=True)
    accessory_type = relationship("AccessoryType", back_populates="products")
```

### AccessoryType Model Excerpt (`db/models.py`)

```python
class AccessoryType(Base):
    __tablename__ = "accessory_types"
    # ... existing columns ...

    products = relationship("Product", back_populates="accessory_type")
    upgrade_sections = relationship(
        "UpgradeSection",
        back_populates="accessory_type",
        cascade="all, delete-orphan"
    )
```

### UpgradeSection Relationship

`UpgradeSection` also optionally links to an `AccessoryType`, allowing accessory categorization at the upgrade-section level:

```python
class UpgradeSection(Base):
    # ... existing columns ...

    accessory_type_id = Column(Integer, ForeignKey("accessory_types.id"), nullable=True)
    accessory_type = relationship("AccessoryType", back_populates="upgrade_sections")
```

---

## Existing Categories Are Unchanged

The `Product` model retains its existing many-to-many relationship with `Category` through the `product_categories` junction table. AccessoryType is a completely independent axis of classification:

- **Category**: Broad product grouping (e.g., "Helmet", "Jacket")
- **AccessoryType**: Specific accessory kind (e.g., "Visor", "Crash Guard")

A product can simultaneously belong to a category and an accessory type.

---

## Repository Methods

**File**: `db/accessory_type_repository.py`

**Class**: `AccessoryTypeRepository`

### Methods

| Method                          | Signature                                    | Returns                                    | Description                                     |
|---------------------------------|----------------------------------------------|--------------------------------------------|-------------------------------------------------|
| `get_accessory_type`            | `(accessory_type_id: int)`                   | `Optional[AccessoryType]`                  | Fetch by primary key                            |
| `get_accessory_type_by_slug`    | `(slug: str)`                                | `Optional[AccessoryType]`                  | Fetch by unique slug                            |
| `get_all_accessory_types`       | `(active_only: bool = True)`                 | `List[AccessoryType]`                      | List all, optionally filtering active only      |
| `create_accessory_type`         | `(data: dict)`                               | `AccessoryType`                            | Persist a new accessory type                    |
| `update_accessory_type`         | `(accessory_type_id: int, data: dict)`       | `Optional[AccessoryType]`                  | Mutate an existing accessory type in-place      |
| `delete_accessory_type`         | `(accessory_type_id: int)`                   | `bool`                                     | Remove by ID; returns `False` if not found      |
| `count_accessory_types`         | `()`                                         | `int`                                      | Total number of accessory types in the database |

### Usage Example

```python
from db.accessory_type_repository import AccessoryTypeRepository
from db.base import SessionLocal

session = SessionLocal()
repo = AccessoryTypeRepository(session)

# Create
mirror = repo.create_accessory_type({
    "name": "Bar End Mirror",
    "slug": "bar-end-mirror",
    "description": "Handlebar-mounted mirrors",
})

# Read
type_from_db = repo.get_accessory_type(mirror.id)

# Update
repo.update_accessory_type(mirror.id, {"description": "Updated description"})

# List all active
active_types = repo.get_all_accessory_types(active_only=True)

# Delete
repo.delete_accessory_type(mirror.id)
```

---

## Service Methods

**File**: `db/accessory_type_service.py`

**Class**: `AccessoryTypeService`

### Methods

| Method                          | Signature                                    | Returns                                    | Description                                        |
|---------------------------------|----------------------------------------------|--------------------------------------------|----------------------------------------------------|
| `get_accessory_type`            | `(accessory_type_id: int)`                   | `Optional[AccessoryType]`                  | Fetch by primary key                               |
| `get_accessory_type_by_slug`    | `(slug: str)`                                | `Optional[AccessoryType]`                  | Fetch by unique slug                               |
| `get_all_accessory_types`       | `(active_only: bool = True)`                 | `List[AccessoryType]`                      | List all, optionally filtering active only         |
| `create_accessory_type`         | `(data: dict)`                               | `AccessoryType`                            | Persist; auto-generates slug from name             |
| `update_accessory_type`         | `(accessory_type_id: int, data: dict)`       | `Optional[AccessoryType]`                  | Mutate; auto-regenerates slug when name changes    |
| `delete_accessory_type`         | `(accessory_type_id: int)`                   | `bool`                                     | Remove by ID                                       |
| `count_accessory_types`         | `()`                                         | `int`                                      | Total count                                        |
| `get_active_accessory_types`    | `()`                                         | `List[AccessoryType]`                      | Convenience wrapper for UI dropdowns               |
| `_generate_slug` (private)      | `(name: str)`                                | `str`                                      | Converts a human name to a URL-safe slug           |

### Service-Level Seed Data

The service module includes a predefined `ACCESSORY_TYPES_DATA` list with all 12 default accessory types:

1. Bar End Mirror
2. Visor
3. Crash Guard
4. Leg Guard
5. Tank Pad
6. Phone Mount
7. Seat Cover
8. Top Box
9. Saddle Stay
10. Lever Guard
11. Engine Guard
12. Mobile Holder

The `seed_accessory_types(session)` function populates the database with these defaults if the table is empty. The `seed_accessory_types_standalone()` convenience function opens its own session for quick one-off seeding.

---

## CRUD Operations — Complete Flow

### Create
1. `AccessoryTypeService.create_accessory_type(data)` auto-generates a slug from the name.
2. The repository persists the record and flushes the session.
3. Returns the created `AccessoryType` instance.

### Read (Single)
1. `get_accessory_type(id)` queries by primary key.
2. `get_accessory_type_by_slug(slug)` queries by unique slug field.

### Read (All)
1. `get_all_accessory_types(active_only=True)` returns all active types sorted alphabetically.
2. `get_active_accessory_types()` is a convenience alias for the same query.

### Update
1. Fetch the existing record by ID.
2. Mutate fields from the incoming `data` dict.
3. If `name` changes, the slug is regenerated automatically.
4. Session is committed; the updated instance is returned.

### Delete
1. Fetch the record by ID.
2. If found, delete and commit.
3. Returns `True` on success, `False` if the record does not exist.

---

## How Product References AccessoryType (Code Level)

### Writing the Association

```python
# Assign an accessory type when creating a product
product = Product(
    asin="B0ABCDEF",
    title="Example Mirror",
    accessory_type_id=mirror_type.id,  # ← foreign key assignment
    # ... other fields ...
)

# Or via ORM relationship
product.accessory_type = mirror_type
session.add(product)
session.commit()
```

### Reading the Association

```python
# From product to type
product = session.query(Product).get(1)
print(product.accessory_type.name)       # e.g., "Bar End Mirror"
print(product.accessory_type.slug)       # e.g., "bar-end-mirror"

# From type to products (one-to-many)
mirror = session.query(AccessoryType).filter_by(slug="bar-end-mirror").first()
for p in mirror.products:
    print(p.title)
```

### Querying by AccessoryType

```python
# All products of a given accessory type
products = session.query(Product).filter_by(accessory_type_id=mirror_type.id).all()

# Products that have no accessory type assigned (backward compat)
untyped = session.query(Product).filter(Product.accessory_type_id.is_(None)).all()

# Products with compatible_bikes set
compatible = session.query(Product).filter(
    Product.compatible_bikes.isnot(None)
).all()

# Universal products (appear on every bike page)
universal = session.query(Product).filter_by(universal=True).all()
```

---

## Product Loading Logic

The `product_library.py` loading pipeline populates the new fields from JSON source data:

- `compatible_bikes`: Defaults to `['*']` if not present in source data (backward compatible)
- `universal`: Defaults to `False` if not present in source data (backward compatible)

Both fields are optional in the JSON source. Existing products without these fields continue to work normally.

---

## Current Limitations

1. **No migration yet**: The `accessory_types` table has not been added via an Alembic migration. The `db/base.py` `init_db()` function (`Base.metadata.create_all`) will create the table on first run, but existing databases require a manual migration.

2. **No index on `accessory_type_id` in Product**: The foreign key column on the `products` table does not yet have a dedicated index. Queries filtering by `accessory_type_id` will perform full table scans on large datasets.

3. **No index on `compatible_bikes`**: The `compatible_bikes` JSON column does not have a GIN index. Queries filtering by specific bike slugs within the array will perform full table scans.

4. **No many-to-many accessory types per product**: A product can only reference a single accessory type. If future requirements demand multi-type tagging (e.g., a product is both "Visor" and "Crash Guard"), a many-to-many junction table would be needed.

5. **No API layer**: The repository and service are data-layer components. There is no REST or GraphQL API wrapper exposing these operations to front-end consumers yet.

6. **No dedicated test suite**: Tests for the `AccessoryTypeRepository` and `AccessoryTypeService` have not been created.

7. **Empty-icon by default**: The `icon` column defaults to `NULL` for all seeded accessory types. UI components that rely on icons will need a fallback.

8. **No cascade protection on delete**: If an `AccessoryType` is deleted while `Product` records still reference it via `accessory_type_id`, those products will have a dangling foreign key (the FK is nullable, so no integrity error occurs, but the link is silently severed).

3. **No many-to-many accessory types per product**: A product can only reference a single accessory type. If future requirements demand multi-type tagging (e.g., a product is both "Visor" and "Crash Guard"), a many-to-many junction table would be needed.

4. **No API layer**: The repository and service are data-layer components. There is no REST or GraphQL API wrapper exposing these operations to front-end consumers yet.

5. **No dedicated test suite**: Tests for the `AccessoryTypeRepository` and `AccessoryTypeService` have not been created.

6. **Empty-icon by default**: The `icon` column defaults to `NULL` for all seeded accessory types. UI components that rely on icons will need a fallback.

7. **No cascade protection on delete**: If an `AccessoryType` is deleted while `Product` records still reference it via `accessory_type_id`, those products will have a dangling foreign key (the FK is nullable, so no integrity error occurs, but the link is silently severed).

---

## Planned Extension Points

### 1. Alembic Migration
A migration script should be added to `alembic/versions/` to add the `accessory_types` table to existing databases, with appropriate `CREATE TABLE` and `CREATE INDEX` statements.

### 2. Index on `accessory_type_id`
```sql
CREATE INDEX ix_products_accessory_type_id ON products (accessory_type_id);
```

### 3. Inheritance Readiness
The `AccessoryType` model is structured to support future subtype inheritance:
- Add a `parent_id` self-referencing foreign key for hierarchical accessory type trees.
- Add a `type_class` column to discriminate between sub-models (e.g., "Protection", "Comfort", "Navigation").
- Use SQLAlchemy single-table inheritance (STI) or joined-table inheritance patterns.

### 4. Many-to-Many Product ↔ AccessoryType
If multi-type products are needed:
- Create a `product_accessory_types` junction table.
- Replace the `accessory_type_id` FK on `Product` with a relationship through the junction.

### 5. REST API Endpoints
Wrap repository/service calls in an API layer:
```
GET    /api/accessory-types          → list all
GET    /api/accessory-types/:id      → read one
POST   /api/accessory-types          → create
PUT    /api/accessory-types/:id      → update
DELETE /api/accessory-types/:id      → delete
```

### 6. Web UI Integration
- Add an "Accessory Type" dropdown in the product creation/edit forms.
- Filter products by accessory type in the catalog view.
- Manage accessory types in an admin panel (CRUD interface).

### 7. Seeding from Configuration File
- Move `ACCESSORY_TYPES_DATA` from the Python module to a JSON/YAML configuration file.
- Load at startup to allow non-code customisation of the default taxonomy.

### 8. Audit / History Tracking
- Add a `history` relationship or use SQLAlchemy event listeners to log changes to accessory types.
- Track who created/updated each record for compliance purposes.

---

## File Inventory

| File                                    | Purpose                                  |
|-----------------------------------------|------------------------------------------|
| `db/models.py`                          | SQLAlchemy ORM models (AccessoryType, Product, UpgradeSection) |
| `db/accessory_type_repository.py`       | Repository layer — raw database CRUD     |
| `db/accessory_type_service.py`          | Service layer — business logic + seeding |
| `db/compatibility_service.py`           | Centralized compatibility queries for all website pages |
| `db/repository.py`                      | Updated to include compatibility query methods |
| `db/product_service.py`                 | Updated to delegate compatibility queries to CompatibilityService |

---

## CompatibilityService — Centralized Query Layer

**File**: `db/compatibility_service.py`

**Class**: `CompatibilityService`

The CompatibilityService is the single source of truth for all compatibility queries used across the website. It reuses the existing `ProductMotorcycle` junction table and the `AccessoryType` → `Product` relationship. No duplicate logic is introduced.

### Methods for Product Pages

| Method                          | Signature                                    | Returns                          | Description                                     |
|---------------------------------|----------------------------------------------|----------------------------------|-------------------------------------------------|
| `get_compatible_bikes_for_product` | `(product_id: int)`                   | `List[dict]`                     | Compatible motorcycles with name, make, model, slug |

### Methods for Motorcycle Pages

| Method                          | Signature                                    | Returns                          | Description                                     |
|---------------------------------|----------------------------------------------|----------------------------------|-------------------------------------------------|
| `get_products_for_motorcycle_grouped` | `(motorcycle_id: int, active_only: bool = True)` | `Dict[str, List[dict]]` | Products grouped by AccessoryType name (e.g., "Bar End Mirrors") |
| `get_products_for_motorcycle_grouped_paginated` | `(motorcycle_id: int, group: str, offset: int, limit: int, active_only: bool = True)` | `Tuple[List[dict], int]` | Paginated slice of a group |
| `get_product_counts_by_accessory_type` | `(motorcycle_id: int)` | `Dict[str, int]` | Count of products per AccessoryType for a motorcycle |

### Methods for Accessory Type Pages

| Method                          | Signature                                    | Returns                          | Description                                     |
|---------------------------------|----------------------------------------------|----------------------------------|-------------------------------------------------|
| `get_products_for_motorcycle_by_accessory_type` | `(motorcycle_id: int, accessory_type_slug: str, offset: int, limit: int)` | `Tuple[List[dict], int]` | Products compatible with a motorcycle filtered by AccessoryType |

### Caching

The service maintains an in-memory `_product_cache` dict keyed by product ID. The `clear_cache()` method resets the cache. Cache entries are created on first access and reused within the same service instance.

### N+1 Prevention

All CompatibilityService methods use explicit join strategies (`.join()`, `.outerjoin()`) rather than lazy-loading relationships. This ensures each method executes at most 1–2 SQL queries regardless of result size.

---

## ProductPage: Compatible Bikes Section

The `ProductService.get_compatible_bikes_for_product(product_slug)` method returns a list of compatible motorcycles for a product page. The template displays:

- A "Compatible Bikes" section listing all compatible motorcycles
- If compatibility is empty, the template displays "Compatibility not yet verified."

### Usage

```python
bikes = product_service.get_compatible_bikes_for_product("honda-cb350")
# Returns: [{"id": 1, "make": "Honda", "model": "CB350", "slug": "honda-cb350", ...}, ...]
```

---

## MotorcyclePage: Products Grouped by AccessoryType

The `ProductService.get_motorcycle_products_grouped(bike_slug)` method returns products compatible with a motorcycle grouped by AccessoryType name.

### Display Logic

1. Iterate over groups (e.g., "Bar End Mirrors", "Visors", "Crash Guards", ...)
2. Each group shows the AccessoryType name and product count
3. Reuse existing product card components for each product
4. Pagination supported via `get_products_for_motorcycle_grouped_paginated()`

### Example groups returned

- **Bar End Mirrors** (N products)
- **Visors** (N products)
- **Crash Guards** (N products)
- **Tank Pads** (N products)
- **Phone Mounts** (N products)
- **Seat Covers** (N products)
- **Top Boxes** (N products)
- **Uncategorized** (any products with no AccessoryType assigned)

### Usage

```python
grouped = product_service.get_motorcycle_products_grouped("honda-cb350")
# Returns: {"Bar End Mirrors": [...], "Visors": [...], ...}

# Paginated within a group
products, total = product_service.get_products_by_accessory_type_for_motorcycle(
    bike_slug="honda-cb350",
    accessory_type_slug="bar-end-mirror",
    offset=0,
    limit=20,
)
```

---

## AccessoryTypePage: Motorcycle-Specific Products

The `ProductService.get_products_by_accessory_type_for_motorcycle(bike_slug, accessory_type_slug)` method returns only products of a given type that are compatible with the selected motorcycle.

### Usage

```python
products, total = product_service.get_products_by_accessory_type_for_motorcycle(
    bike_slug="honda-cb350",
    accessory_type_slug="crash-guard",
    offset=0,
    limit=20,
)
```

---

*Documentation generated for the AccessoryType first-class entity implementation.*
