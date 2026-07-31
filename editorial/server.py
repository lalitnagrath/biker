"""
Editorial Control Center Server
================================
FastAPI server serving the multi-page editorial dashboard + API endpoints.

Usage:
    cd biker
    python editorial/server.py
    # Opens at http://localhost:8765
"""

import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.product_service import ProductService
from db.motorcycle_service import MotorcycleService
from db.collection_service import CollectionService
from db.amazon_search_service import AmazonSearchError, AmazonSearchService
from db.import_service import ProductImportService
from db.models import Motorcycle

HERE = Path(__file__).parent
PROJECT = HERE.parent
DB_PATH = PROJECT / "bikereview.db"

app = FastAPI(title="BikeReview Control Center", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ---- Static files ----
app.mount("/editorial", StaticFiles(directory=str(HERE), html=True), name="editorial")
app.mount("/data/products", StaticFiles(directory=str(PROJECT / "data" / "products"), html=True), name="products_data")
app.mount("/static", StaticFiles(directory=str(PROJECT / "static"), html=True), name="static")


# ---- Helpers ----
def _get_service():
    svc = ProductService()
    svc.load_all()
    return svc


# ---- API: Dashboard KPI ----
@app.get("/api/dashboard")
def api_dashboard():
    svc = _get_service()
    products = svc.get_all()

    return {
        "total": len(products),
        "active": sum(1 for p in products if p.get("status") == "approved"),
        "hidden": sum(1 for p in products if p.get("status") == "hidden"),
        "review": sum(1 for p in products if p.get("status") in ("review",)),
        "rejected": sum(1 for p in products if p.get("status") == "rejected"),
        "draft": sum(1 for p in products if p.get("status") == "draft"),
        "editors_choice": sum(1 for p in products if p.get("editors_choice")),
        "missing_images": svc.get_missing_image_count(),
        "price_drops": svc.get_price_drop_count(days=7),
        "categories_with_products": len({p.get("category") for p in products if p.get("status") in ("approved", "review")}),
        "total_in_db": svc.get_total_in_db(),
        "updated_at": datetime.now().isoformat(),
    }


# ---- API: Products Summary ----
@app.get("/api/products")
def api_products(category: Optional[str] = Query(None)):
    svc = _get_service()
    if category:
        prods = svc.get_products_by_category(category)
    else:
        prods = svc.get_all()
    return {"total": len(prods), "products": prods}


# ---- Helpers for motorcycle compatibility ----

def _active_product(p: dict) -> bool:
    """Products that are visible on the generated site (approved or review)."""
    return p.get("status") in ("approved", "review")


def _bike_specific_count(products: List[dict], slug: str) -> int:
    slug_l = slug.lower()
    return sum(
        1
        for p in products
        if not p.get("universal")
        and _active_product(p)
        and slug_l in [c.lower() for c in (p.get("compatible_bikes") or [])]
    )


def _universal_count(products: List[dict]) -> int:
    return sum(1 for p in products if p.get("universal") and _active_product(p))


# ---- API: Motorcycles ----
@app.get("/api/motorcycles")
def api_motorcycles():
    svc = MotorcycleService()
    products = _get_service().get_all()
    universal_count = _universal_count(products)
    bikes = svc.load_all()
    for b in bikes:
        bs = _bike_specific_count(products, b.get("slug") or "")
        b["bike_specific"] = bs
        b["universal"] = universal_count
        b["total"] = bs + universal_count
    return {"total": len(bikes), "motorcycles": bikes}


# ---- API: Motorcycle compatibility management ----
@app.get("/api/motorcycles/{slug}")
def api_motorcycle_detail(slug: str):
    moto_svc = MotorcycleService()
    bikes = moto_svc.load_all()
    bike = next((b for b in bikes if b.get("slug") == slug), None)
    if not bike:
        return JSONResponse({"error": "Motorcycle not found"}, status_code=404)

    products = _get_service().get_all()
    slug_l = slug.lower()
    bike_specific: List[dict] = []
    universal: List[dict] = []
    unassigned: List[dict] = []
    for p in products:
        if not _active_product(p):
            continue
        if p.get("universal"):
            universal.append(p)
        elif slug_l in [c.lower() for c in (p.get("compatible_bikes") or [])]:
            bike_specific.append(p)
        else:
            unassigned.append(p)

    def _summ(p: dict) -> dict:
        return {
            "asin": p.get("asin"),
            "slug": p.get("slug"),
            "title": p.get("title"),
            "brand": p.get("brand"),
            "category": p.get("category"),
            "image": p.get("image"),
            "universal": bool(p.get("universal")),
            "compatible_bikes": p.get("compatible_bikes") or [],
            "editors_choice": bool(p.get("editors_choice")),
            "status": p.get("status"),
        }

    def _sort_key(p: dict):
        return (p.get("category") or "", p.get("title") or "")

    bike_specific.sort(key=_sort_key)
    universal.sort(key=_sort_key)
    unassigned.sort(key=_sort_key)

    categories = sorted({p.get("category") for p in products if p.get("category")})

    return {
        "bike": bike,
        "bike_specific": [_summ(p) for p in bike_specific],
        "universal": [_summ(p) for p in universal],
        "unassigned": [_summ(p) for p in unassigned],
        "categories": categories,
        "counts": {
            "bike_specific": len(bike_specific),
            "universal": len(universal),
            "total": len(bike_specific) + len(universal),
        },
    }


@app.put("/api/motorcycles/{slug}/products/{asin}")
def api_moto_assign_product(slug: str, asin: str):
    from sqlalchemy.orm import Session
    from db.base import engine
    from db.models import Product, ProductMotorcycle

    with Session(engine) as session:
        bike = session.query(Motorcycle).filter_by(slug=slug).first()
        if not bike:
            return JSONResponse({"error": "Motorcycle not found"}, status_code=404)
        product = session.query(Product).filter_by(asin=asin).first()
        if not product:
            return JSONResponse({"error": "Product not found"}, status_code=404)

        cb = list(product.compatible_bikes or [])
        if product.universal:
            # Restricting a universal product makes it bike-specific only.
            product.universal = False
            cb = [slug]
        else:
            if slug not in cb:
                cb.append(slug)
        product.compatible_bikes = cb or None

        session.query(ProductMotorcycle).filter_by(product_id=product.id).delete()
        for s in cb:
            b = session.query(Motorcycle).filter_by(slug=s).first()
            if b:
                session.add(ProductMotorcycle(
                    product_id=product.id,
                    motorcycle_id=b.id,
                    match_strategy="editorial",
                ))
        session.commit()
    return {"success": True, "asin": asin, "slug": slug, "compatible_bikes": cb}


@app.delete("/api/motorcycles/{slug}/products/{asin}")
def api_moto_remove_product(slug: str, asin: str):
    from sqlalchemy.orm import Session
    from db.base import engine
    from db.models import Product, ProductMotorcycle

    with Session(engine) as session:
        bike = session.query(Motorcycle).filter_by(slug=slug).first()
        if not bike:
            return JSONResponse({"error": "Motorcycle not found"}, status_code=404)
        product = session.query(Product).filter_by(asin=asin).first()
        if not product:
            return JSONResponse({"error": "Product not found"}, status_code=404)
        if product.universal:
            return JSONResponse(
                {"error": "Universal product cannot be removed from a specific bike; disable Universal on the product instead"},
                status_code=400,
            )

        cb = list(product.compatible_bikes or [])
        if slug in cb:
            cb.remove(slug)
        product.compatible_bikes = cb or None

        session.query(ProductMotorcycle).filter_by(product_id=product.id).delete()
        for s in cb:
            b = session.query(Motorcycle).filter_by(slug=s).first()
            if b:
                session.add(ProductMotorcycle(
                    product_id=product.id,
                    motorcycle_id=b.id,
                    match_strategy="editorial",
                ))
        session.commit()
    return {"success": True, "asin": asin, "slug": slug, "compatible_bikes": cb}


# ---- API: Compatibility ----
@app.get("/api/compatibility")
def api_compatibility():
    moto_svc = MotorcycleService()
    products_svc = ProductService()
    
    motorcycles = moto_svc.load_all()
    all_products = products_svc.get_all()
    
    # Build compatibility mapping
    compatibility_map = {}
    for bike in motorcycles:
        compatible_products = []
        bike_categories = []
        
        # Get bike's compatible product categories from engine size/rating filters
        # This is a simplified compatibility logic - in real implementation,
        # this would check actual fitment data
        for product in all_products:
            compatible = False
            
            # Example compatibility logic based on product category and bike
            # This can be expanded with real fitment rules
            if bike.category == 'all-terrain' and product.category in ['off-road', 'dual-sport']:
                compatible = True
            elif bike.category == 'commuter' and product.category == 'accessory':
                compatible = True
            elif bike.category == 'touring' and product.category in ['luggage', 'accessory']:
                compatible = True
            
            if compatible:
                compatible_products.append(product)
        
        compatibility_map[bike.id] = {
            "bike": bike,
            "products": compatible_products[:10],  # Limit for performance
            "total_count": len(compatible_products)
        }
    
    # Extract unique brands and categories
    all_brands = set()
    all_categories = set()
    for bike_data in compatibility_map.values():
        bike = bike_data['bike']
        for product in bike_data['products']:
            all_brands.add(product.get('brand') or '')
            all_categories.add(product.get('category') or '')
    
    return {
        "total_motorcycles": len(motorcycles),
        "total_products": len(all_products),
        "motorcycles": motorcycles,
        "motorcycle_products": compatibility_map,
        "brands": sorted([b for b in all_brands if b]),
        "categories": sorted([c for c in all_categories if c])
    }


# ---- API: Collections ----
@app.get("/api/collections")
def api_collections():
    svc = CollectionService()
    return {"total": len(colls := svc.load_all()), "collections": colls}


# ---- API: Upgrade Collections (Pimp My Ride) ----
from sqlalchemy.orm import Session as _Session, joinedload as _joinedload
from db.base import engine as _db_engine
from db.models import Product as _Product, UpgradeCollection as _UpgradeCollection
from db.models import ProductMotorcycle as _ProductMotorcycle


def _uc_image(p) -> str:
    for img in p.images:
        return img.url or ""
    return ""


def _uc_product_summary(p) -> dict:
    return {
        "asin": p.asin or "",
        "slug": p.slug or "",
        "title": p.title or "",
        "brand": p.brand.name if p.brand else "",
        "category": (p.categories[0].name if p.categories else ""),
        "image": _uc_image(p),
        "universal": bool(p.universal),
        "compatible_bikes": p.compatible_bikes or [],
        "status": p.status or "",
        "collections": [c.slug for c in p.upgrade_collections],
    }


def _uc_collection_summary(c, products: List[dict]) -> dict:
    total = len(products)
    universal = sum(1 for p in products if p.get("universal"))
    return {
        "slug": c.slug,
        "name": c.name,
        "description": c.description or "",
        "icon": c.icon or "",
        "sort_order": c.sort_order or 0,
        "enabled": bool(c.enabled),
        "product_count": total,
        "universal_count": universal,
        "bike_specific_count": total - universal,
    }


def _uc_load_products(session) -> List[_Product]:
    return (
        session.query(_Product)
        .options(
            _joinedload(_Product.upgrade_collections),
            _joinedload(_Product.brand),
            _joinedload(_Product.categories),
            _joinedload(_Product.images),
        )
        .order_by(_Product.id)
        .all()
    )


@app.get("/api/upgrade-collections")
def api_uc_list():
    with _Session(_db_engine) as session:
        collections = (
            session.query(_UpgradeCollection)
            .order_by(_UpgradeCollection.sort_order, _UpgradeCollection.name)
            .all()
        )
        products = _uc_load_products(session)
        by_slug: Dict[str, List[dict]] = {}
        for p in products:
            summ = _uc_product_summary(p)
            for c in p.upgrade_collections:
                by_slug.setdefault(c.slug, []).append(summ)
        return {
            "total": len(collections),
            "products_total": len(products),
            "collections": [
                _uc_collection_summary(c, by_slug.get(c.slug, []))
                for c in collections
            ],
        }


@app.get("/api/upgrade-collections/{slug}")
def api_uc_detail(slug: str):
    with _Session(_db_engine) as session:
        coll = session.query(_UpgradeCollection).filter_by(slug=slug).first()
        if not coll:
            return JSONResponse({"error": "Upgrade collection not found"}, status_code=404)

        products = [
            _uc_product_summary(p)
            for p in _uc_load_products(session)
            if any(c.slug == slug for c in p.upgrade_collections)
        ]
        products.sort(key=lambda p: ((p.get("category") or ""), (p.get("title") or "")))

        all_colls = (
            session.query(_UpgradeCollection)
            .order_by(_UpgradeCollection.sort_order, _UpgradeCollection.name)
            .all()
        )

    moto_svc = MotorcycleService()
    bikes = moto_svc.load_all()
    motorcycles = [
        {
            "slug": b.get("slug"),
            "make": b.get("make"),
            "model": b.get("model"),
            "year": b.get("year"),
            "category": b.get("category"),
        }
        for b in bikes
    ]

    universal = sum(1 for p in products if p.get("universal"))
    return {
        "collection": _uc_collection_summary(coll, products),
        "products": products,
        "collections": [
            {"slug": c.slug, "name": c.name, "icon": c.icon or ""}
            for c in all_colls
        ],
        "motorcycles": motorcycles,
        "categories": sorted({p.get("category") for p in products if p.get("category")}),
        "counts": {
            "total": len(products),
            "universal": universal,
            "bike_specific": len(products) - universal,
        },
    }


@app.put("/api/upgrade-collections/{slug}/products/{asin}")
def api_uc_add_product(slug: str, asin: str):
    with _Session(_db_engine) as session:
        coll = session.query(_UpgradeCollection).filter_by(slug=slug).first()
        if not coll:
            return JSONResponse({"error": "Upgrade collection not found"}, status_code=404)
        product = session.query(_Product).filter_by(asin=asin).first()
        if not product:
            return JSONResponse({"error": "Product not found"}, status_code=404)
        if product not in coll.products:
            coll.products.append(product)
        session.commit()
    return {"success": True, "slug": slug, "asin": asin}


@app.delete("/api/upgrade-collections/{slug}/products/{asin}")
def api_uc_remove_product(slug: str, asin: str):
    with _Session(_db_engine) as session:
        coll = session.query(_UpgradeCollection).filter_by(slug=slug).first()
        if not coll:
            return JSONResponse({"error": "Upgrade collection not found"}, status_code=404)
        product = session.query(_Product).filter_by(asin=asin).first()
        if not product:
            return JSONResponse({"error": "Product not found"}, status_code=404)
        if product in coll.products:
            coll.products.remove(product)
        session.commit()
    return {"success": True, "slug": slug, "asin": asin}


@app.put("/api/upgrade-collections/{slug}/products/{asin}/collections")
def api_uc_change_collections(slug: str, asin: str, payload: Dict[str, Any]):
    wanted = payload.get("collections") or []
    if not isinstance(wanted, list):
        return JSONResponse({"error": "collections must be a list"}, status_code=400)
    with _Session(_db_engine) as session:
        product = session.query(_Product).filter_by(asin=asin).first()
        if not product:
            return JSONResponse({"error": "Product not found"}, status_code=404)
        colls = (
            session.query(_UpgradeCollection)
            .filter(_UpgradeCollection.slug.in_([str(s).strip() for s in wanted]))
            .all()
        )
        valid_slugs = sorted({c.slug for c in colls})
        product.upgrade_collections = colls
        session.commit()
    return {"success": True, "asin": asin, "collections": valid_slugs}


@app.put("/api/upgrade-collections/{slug}/products/{asin}/motorcycles")
def api_uc_set_motorcycles(slug: str, asin: str, payload: Dict[str, Any]):
    bikes = payload.get("compatible_bikes") or []
    if not isinstance(bikes, list):
        return JSONResponse({"error": "compatible_bikes must be a list"}, status_code=400)
    bikes = [str(b).strip() for b in bikes if str(b).strip()]
    with _Session(_db_engine) as session:
        product = session.query(_Product).filter_by(asin=asin).first()
        if not product:
            return JSONResponse({"error": "Product not found"}, status_code=404)
        if bikes:
            product.universal = False
        product.compatible_bikes = bikes or None
        session.query(_ProductMotorcycle).filter_by(product_id=product.id).delete()
        for s in bikes:
            bike = session.query(Motorcycle).filter_by(slug=s).first()
            if bike:
                session.add(_ProductMotorcycle(
                    product_id=product.id,
                    motorcycle_id=bike.id,
                    match_strategy="editorial",
                ))
        session.commit()
    return {"success": True, "asin": asin, "compatible_bikes": bikes}


@app.delete("/api/upgrade-collections/{slug}/products/{asin}/motorcycles/{moto_slug}")
def api_uc_remove_motorcycle(slug: str, asin: str, moto_slug: str):
    with _Session(_db_engine) as session:
        product = session.query(_Product).filter_by(asin=asin).first()
        if not product:
            return JSONResponse({"error": "Product not found"}, status_code=404)
        cb = list(product.compatible_bikes or [])
        if moto_slug in cb:
            cb.remove(moto_slug)
        product.compatible_bikes = cb or None
        session.query(_ProductMotorcycle).filter_by(product_id=product.id).delete()
        for s in cb:
            bike = session.query(Motorcycle).filter_by(slug=s).first()
            if bike:
                session.add(_ProductMotorcycle(
                    product_id=product.id,
                    motorcycle_id=bike.id,
                    match_strategy="editorial",
                ))
        session.commit()
    return {"success": True, "asin": asin, "compatible_bikes": cb}


@app.post("/api/upgrade-collections/products/bulk-collections")
def api_uc_bulk_collections(payload: Dict[str, Any]):
    asins = payload.get("asins") or []
    wanted = payload.get("collections") or []
    if not isinstance(asins, list) or not asins:
        return JSONResponse({"error": "asins must be a non-empty list"}, status_code=400)
    if not isinstance(wanted, list):
        return JSONResponse({"error": "collections must be a list"}, status_code=400)
    with _Session(_db_engine) as session:
        colls = (
            session.query(_UpgradeCollection)
            .filter(_UpgradeCollection.slug.in_([str(s).strip() for s in wanted]))
            .all()
        )
        products = session.query(_Product).filter(_Product.asin.in_(asins)).all()
        for p in products:
            p.upgrade_collections = list(colls)
        session.commit()
        return {"success": True, "updated": len(products),
                "collections": sorted({c.slug for c in colls})}


@app.post("/api/upgrade-collections/products/bulk-motorcycles")
def api_uc_bulk_motorcycles(payload: Dict[str, Any]):
    asins = payload.get("asins") or []
    bikes = payload.get("compatible_bikes") or []
    if not isinstance(asins, list) or not asins:
        return JSONResponse({"error": "asins must be a non-empty list"}, status_code=400)
    if not isinstance(bikes, list):
        return JSONResponse({"error": "compatible_bikes must be a list"}, status_code=400)
    bikes = [str(b).strip() for b in bikes if str(b).strip()]
    with _Session(_db_engine) as session:
        products = session.query(_Product).filter(_Product.asin.in_(asins)).all()
        for p in products:
            if bikes:
                p.universal = False
            p.compatible_bikes = bikes or None
            session.query(_ProductMotorcycle).filter_by(product_id=p.id).delete()
            for s in bikes:
                bike = session.query(Motorcycle).filter_by(slug=s).first()
                if bike:
                    session.add(_ProductMotorcycle(
                        product_id=p.id,
                        motorcycle_id=bike.id,
                        match_strategy="editorial",
                    ))
        session.commit()
        return {"success": True, "updated": len(products), "compatible_bikes": bikes}


@app.post("/api/upgrade-collections/{slug}/products/bulk-remove")
def api_uc_bulk_remove(slug: str, payload: Dict[str, Any]):
    asins = payload.get("asins") or []
    if not isinstance(asins, list) or not asins:
        return JSONResponse({"error": "asins must be a non-empty list"}, status_code=400)
    with _Session(_db_engine) as session:
        coll = session.query(_UpgradeCollection).filter_by(slug=slug).first()
        if not coll:
            return JSONResponse({"error": "Upgrade collection not found"}, status_code=404)
        products = session.query(_Product).filter(_Product.asin.in_(asins)).all()
        for p in products:
            if p in coll.products:
                coll.products.remove(p)
        session.commit()
        return {"success": True, "removed": len(products)}


# ---- API: Amazon product discovery (Phase 8.1 + 8.2) ----
@app.get("/api/amazon/search")
def api_amazon_search(keyword: Optional[str] = Query(None),
                      item_count: int = Query(20, ge=1, le=50),
                      page: int = Query(1, ge=1),
                      category: Optional[str] = Query(None),
                      brand: Optional[str] = Query(None)):
    if not keyword or not keyword.strip():
        return JSONResponse({"error": "Keyword is required"}, status_code=400)
    try:
        search_svc = AmazonSearchService()
        import_svc = ProductImportService()
        result = search_svc.search(
            keyword=keyword,
            item_count=item_count,
            page=page,
            known_asins=import_svc.existing_asins(),
            category=category,
            brand=brand,
        )
        return result
    except AmazonSearchError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)


# ---- API: Product import (Phase 8.1) ----
@app.post("/api/import")
def api_import(payload: Dict[str, Any]):
    products = payload.get("products") or []
    download_images = bool(payload.get("download_images", True))
    if not isinstance(products, list) or not products:
        return JSONResponse({"error": "No products to import"}, status_code=400)
    svc = ProductImportService()
    report = svc.import_products(products, download_images=download_images)
    return report


# ---- API: Product compatibility update ----
@app.put("/api/products/{asin}/compatibility")
def api_update_compatibility(asin: str, payload: Dict[str, Any]):
    universal = bool(payload.get("universal", False))
    compatible_bikes = payload.get("compatible_bikes", [])
    if not isinstance(compatible_bikes, list):
        return JSONResponse({"error": "compatible_bikes must be a list"}, status_code=400)
    for i, slug in enumerate(compatible_bikes):
        compatible_bikes[i] = str(slug).strip()
    compatible_bikes = [s for s in compatible_bikes if s]

    # Validation: universal products must not list specific bikes,
    # and non-universal products require at least one compatible bike.
    if universal:
        compatible_bikes = []
    elif not compatible_bikes:
        return JSONResponse(
            {"error": "At least one compatible bike must be selected when Universal is off"},
            status_code=400,
        )

    from sqlalchemy.orm import Session
    from db.base import engine
    from db.models import Product, ProductMotorcycle

    with Session(engine) as session:
        product = session.query(Product).filter_by(asin=asin).first()
        if not product:
            return JSONResponse({"error": "Product not found"}, status_code=404)

        product.universal = universal
        product.compatible_bikes = compatible_bikes if compatible_bikes else None

        # Update junction table
        session.query(ProductMotorcycle).filter_by(product_id=product.id).delete()
        for slug in compatible_bikes:
            bike = session.query(Motorcycle).filter_by(slug=slug).first()
            if bike:
                session.add(ProductMotorcycle(
                    product_id=product.id,
                    motorcycle_id=bike.id,
                    match_strategy="editorial",
                ))

        session.commit()

    return {"success": True, "asin": asin, "universal": universal, "compatible_bikes": compatible_bikes}


# ---- API: Website stats ----
@app.get("/api/website")
def api_website():
    svc = _get_service()
    products = svc.get_all()
    by_cat = {}
    for p in products:
        cat = p.get("category", "Uncategorized")
        by_cat.setdefault(cat, {"total": 0, "approved": 0, "hidden": 0})
        by_cat[cat]["total"] += 1
        status = p.get("status", "draft")
        if status == "approved":
            by_cat[cat]["approved"] += 1
        elif status == "hidden":
            by_cat[cat]["hidden"] += 1
    return {
        "total_products": len(products),
        "categories": len(by_cat),
        "pages_generated": len(by_cat) * 2 + 10,
        "by_category": by_cat,
    }


# ---- API: Settings ----
@app.get("/api/settings")
def api_settings():
    return {
        "db_path": str(DB_PATH),
        "db_size_mb": round(DB_PATH.stat().st_size / (1024 * 1024), 1) if DB_PATH.exists() else 0,
        "product_files_count": len(list((PROJECT / "data" / "products").glob("*.json"))),
        "editorial_json_exists": (PROJECT / "editorial.json").exists(),
    }


# ---- Serve project root files needed by the editorial page ----
_EDITORIAL_JSON = PROJECT / "editorial.json"


@app.get("/editorial.json")
def get_editorial_json():
    if _EDITORIAL_JSON.exists():
        return FileResponse(str(_EDITORIAL_JSON))
    return JSONResponse({"error": "Not found"}, status_code=404)


# ---- Root: serve editorial index ----
@app.get("/")
def root():
    return FileResponse(str(HERE / "index.html"))


# ---- Main ----
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8765"))
    print(f"  BikeReview Control Center -> http://localhost:{port}")
    print(f"  Dashboard                  http://localhost:{port}/#dashboard")
    print(f"  Products (Editorial)       http://localhost:{port}/#products")
    webbrowser.open(f"http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
