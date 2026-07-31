# ARCHITECTURE.md

## Overview

This repository contains a motorcycle recommendation platform that generates static HTML sites for motorcycle reviews, buying guides, and maintenance tips.

## Core Components

### Database Layer
- **SQLite** (`bikereview.db`) - Main storage, managed through SQLAlchemy ORM
- **Models** (`db/models.py`) - Database tables for products, motorcycles, brands, categories, etc.

### Service Layer (Repository Pattern)
- **ProductService** (`db/product_service.py`) - Provides flat dicts for product catalog
- **MotorcycleKnowledgeGraphService** (`db/knowledge_graph_service.py`) - Manages motorcycle Knowledge Graph
- **SmartCollectionService** (`db/smart_collections.py`) - Handles smart collections with rule evaluation

### Product Management
- **Product** (`product_model.py`) - Defines immutable identity + mutable commerce fields (`class Product`)
- **product_library** (`product_library.py`) - Loads, filters, validates, and manages products (function module)
- **ProductMatcher** (`product_matcher.py`) - Deterministic product matching from commerce feeds
- **sync_engine** (`sync_engine.py`) - Daily sync from Amazon data into product library (function module)

### Site Generation
- **GeneratorEngine** (`db/generator_engine.py`) - Data-driven page data provider
- **Site Generator** (`generate.py`) - Static site generator

### Control Center (Phase 8.1 + 8.2)
- **AmazonSearchService** (`db/amazon_search_service.py`) - Keyword search against Amazon with optional category/brand filters, pagination total, and facet lists; returns import-ready flat dicts
- **ProductImportService** (`db/import_service.py`) - Writes selected products to SQLite, downloads images
- **Control Center API** (`editorial/server.py`) - FastAPI endpoints `/api/amazon/search` and `/api/import`
- **Control Center UI** (`editorial/index.html`) - "Amazon Import" page with keyword search, filters, pagination, preview-before-import, and multi-select import

### Amazon Credentials (single source of truth)
- **amazon_credentials** (`amazon_credentials.py`) - Shared by `bike.py`, `honda-cb350.py`
  and `db/amazon_search_service.py`. Resolves CreatorsAPI credentials (explicit
  args, then `AMAZON_CREATOR_CREDENTIAL_ID` / `AMAZON_CREATOR_CREDENTIAL_SECRET`
  env vars, then built-in defaults) and the affiliate partner tag. Secrets live
  here only — never duplicated elsewhere.

### Recommendation & Filtering
- **product_engine** (`product_engine.py`) - Product selection, ranking, and filtering (function module)

## Data Flow

1. **Product Input**: JSON files or Amazon feeds
2. **Product Library**: Loads/ validates/ filters products by status
3. **Database Sync**: Writes flat dicts to SQLite via `DatabaseWriter`
4. **Website Generation**: GeneratorEngine reads from services, produce static HTML
5. **Daily Sync**: `sync_engine` updates Amazon data, writes to DB

## Architecture Patterns

- **Repository Pattern**: DB access abstraction with caching
- **Service Pattern**: Returns flat dicts (never SQLAlchemy models)
- **Event Sourcing**: Price history, sync logs
- **Immutable Identity**: Product identity never changes
- **Data-Driven**: Generator uses database, not hardcoded data

## Files by Layer

### Database
- `db/base.py` - SQLAlchemy setup
- `db/models.py` - All database tables
- `db/repository.py` - Product repository
- `db/collection_repository.py` - Collection CRUD
- `db/motorcycle_repository.py` - Motorcycle repository
- `db/collection_service.py` - Collection service
- `db/motorcycle_service.py` - Motorcycle service
- `db/product_service.py` - Product service
- `db/knowledge_graph_service.py` - Knowledge Graph service
- `db/smart_collections.py` - Smart collections service
- `db/generator_engine.py` - Generator engine
- `db/writer.py` - Database writer
- `db/amazon_search_service.py` - Amazon keyword search (Phase 8.1)
- `db/import_service.py` - Product import into SQLite (Phase 8.1)

### Control Center
- `editorial/server.py` - FastAPI server (Phase 8.1 API endpoints)
- `editorial/index.html` - Control Center UI, incl. Amazon Import page (Phase 8.1)

### Application
- `amazon_credentials.py` - Amazon CreatorsAPI credentials (single source of truth)
- `product_model.py` - Product data model
- `product_library.py` - Product library
- `product_matcher.py` - Product matcher
- `product_engine.py` - Recommendation engine
- `sync_engine.py` - Sync engine
- `generate.py` - Site generator

## Test Coverage

- `test_generator_engine.py` - 24 tests for GeneratorEngine
- `test_smart_collections.py` - 21 tests for SmartCollections
- `test_recommendation_engine.py` - 8 tests for `product_engine`
- `test_knowledge_graph.py` - 24 tests for KnowledgeGraph
- `test_amazon_search_service.py` - 18 tests for AmazonSearchService (Phase 8.1 + 8.2)
- `test_product_import_service.py` - 9 tests for ProductImportService (Phase 8.1)
- `test_control_center_api.py` - 6 tests for Control Center API (Phase 8.1 + 8.2)

Total: 110 tests (run test files individually with system `python3`; a single
`pytest test_*.py` invocation hits a pre-existing `sys.modules` stub collision
between `test_recommendation_engine.py` and `test_smart_collections.py`).
