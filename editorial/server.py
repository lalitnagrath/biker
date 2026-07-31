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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.product_service import ProductService
from db.motorcycle_service import MotorcycleService
from db.collection_service import CollectionService
from db.amazon_search_service import AmazonSearchError, AmazonSearchService
from db.import_service import ProductImportService

HERE = Path(__file__).parent
PROJECT = HERE.parent
DB_PATH = PROJECT / "bikereview.db"

app = FastAPI(title="BikeReview Control Center", version="1.0")

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


# ---- API: Motorcycles ----
@app.get("/api/motorcycles")
def api_motorcycles():
    svc = MotorcycleService()
    return {"total": len(bikes := svc.load_all()), "motorcycles": bikes}


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
