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
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.product_service import ProductService
from db.motorcycle_service import MotorcycleService
from db.collection_service import CollectionService

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


# ---- API: Collections ----
@app.get("/api/collections")
def api_collections():
    svc = CollectionService()
    return {"total": len(colls := svc.load_all()), "collections": colls}


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
