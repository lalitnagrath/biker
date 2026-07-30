"""
Export SQLite data back to JSON files matching the original structure.

Writes to:
  - data/products/*.json        (curated product catalog, grouped by category)
  - data/editorial.json         (editorial picks reconstructed from collections)

The output is designed to be byte-for-byte compatible with the original
JSON format consumed by generate.py / product_library.py.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, joinedload

from db.base import Base
from db.models import (
    Brand, Category, Collection, CollectionItem, EditorialScore,
    Image, Motorcycle, PriceHistory, Product, ProductCategory,
    ProductTag, ProductMotorcycle, Setting,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("export_products")

DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")
CURRENCY = "INR"
PRICING_SOURCE_SYNC = "amazon_sync"

CATEGORY_FILE_MAP = {
    "Helmet": "helmets.json",
    "Phone Mount": "accessories.json",
    "Tyre Inflator": "accessories.json",
    "Engine Oil": "maintenance.json",
    "Chain Lube": "maintenance.json",
    "Chain Cleaner": "maintenance.json",
    "Bike Cover": "bike-covers.json",
    "Jackets": "jackets.json",
    "Gloves": "gloves.json",
    "Saddle Bag": "luggage.json",
    "Tail Bag": "luggage.json",
    "Tank Bag": "luggage.json",
    "Knee Guard": "protection.json",
    "Ear Plugs": "ear-plugs.json",
    "Action Camera": "cameras.json",
    "Dash Cam": "cameras.json",
    "Seat Cover": "seat-covers.json",
    "Riding Pants": "riding-pants.json",
    "Handlebar Grip": "handlebar-accessories.json",
    "Mirror": "mirrors.json",
    "Windshield": "windshields.json",
    "GPS Tracker": "gps-trackers.json",
    "Headlight": "lighting.json",
    "Indicator": "lighting.json",
    "Horn": "horns.json",
    "Charger": "chargers.json",
    "Footrest": "footrests.json",
    "Chain Lock": "locks.json",
    "Disc Lock": "locks.json",
    "Alarm": "alarms.json",
    "Tool Kit": "tools.json",
    "Polish": "care.json",
    "Crash Guard": "protection.json",
}

STATUS_TO_JSON = {
    "active": "approved",
    "draft": "draft",
    "review": "review",
    "hidden": "hidden",
    "out_of_stock": "out_of_stock",
    "discontinued": "discontinued",
}


def _intify(v):
    """Convert to int if it's a whole number, preserving None."""
    if v is None:
        return None
    if isinstance(v, float) and v == int(v):
        return int(v)
    return v


def _category_to_file(category: str) -> str:
    return CATEGORY_FILE_MAP.get(category, "other-accessories.json")


def _reverse_status(db_status: str) -> str:
    return STATUS_TO_JSON.get(db_status, "approved")


def build_pricing(
    current=None, mrp=None, discount_percent=None,
    currency="INR", last_updated=None, source=PRICING_SOURCE_SYNC,
) -> dict:
    return {
        "current": current,
        "mrp": mrp,
        "discount_percent": discount_percent,
        "currency": currency,
        "last_updated": last_updated,
        "source": source,
    }


def product_to_json(product: Product) -> dict:
    """Convert a DB Product row + relations back to the nested JSON format."""
    brand_name = product.brand.name if product.brand else ""
    category = ""
    product_type = ""
    if product.categories:
        category = product.categories[0].name or ""
        if len(product.categories) > 1:
            product_type = product.categories[1].name or ""

    recommended_for = []
    picks = {}
    fitment_notes = ""
    editorial_notes = ""
    pros = []
    cons = []
    features = []
    score = 0
    if product.editorial_score:
        es = product.editorial_score
        score = _intify(es.editor_score) or 0
        pros = es.pros or []
        cons = es.cons or []
        features = es.features or []
        recommended_for = es.recommended_for or []
        editorial_notes = es.editorial_notes or ""
        picks = es.picks or {}

    fitment_notes = picks.get("fitment_notes", "")

    image_path = ""
    if product.images:
        for img in product.images:
            if img.is_primary:
                image_path = img.local_path or img.url
                break
        if not image_path:
            image_path = product.images[0].local_path or product.images[0].url

    if image_path and image_path.startswith(("http://", "https://")):
        pass
    elif image_path and not image_path.startswith("images/"):
        image_path = f"images/products/{image_path}"

    compatible_bikes = ["*"]
    if product.motorcycles:
        bike_slugs = [m.slug for m in product.motorcycles if m.slug]
        if bike_slugs:
            compatible_bikes = bike_slugs

    price = _intify(product.price)
    mrp = _intify(product.mrp)
    rating = _intify(product.rating)
    review_count = _intify(product.review_count)

    editorial = {
        "score": score,
        "pros": pros,
        "cons": cons,
        "features": features,
        "fitment_notes": fitment_notes,
        "recommended_for": recommended_for,
        "notes": editorial_notes,
    }

    last_updated = None
    if product.last_sync_at:
        last_updated = product.last_sync_at.isoformat()

    amazon = {
        "price": price,
        "mrp": mrp,
        "discount": None,
        "rating": rating if rating is not None else 0,
        "review_count": review_count if review_count is not None else 0,
        "availability": product.availability or "",
        "affiliate_url": product.url or "",
        "image": image_path,
        "last_updated": last_updated,
    }

    result = {
        "asin": product.asin,
        "slug": product.slug or "",
        "title": product.title,
        "brand": brand_name,
        "category": category,
        "type": product_type,
        "status": _reverse_status(product.status),
        "editorial": editorial,
        "amazon": amazon,
        "compatible_bikes": compatible_bikes,
        "best_for": picks.get("best_for", "") if isinstance(picks, dict) else "",
        "verdict": picks.get("verdict", "") if isinstance(picks, dict) else "",
    }

    return result


def _clean_none_values(obj: Any) -> Any:
    """Remove keys with None values at the top level for clean JSON output."""
    if isinstance(obj, dict):
        return {k: _clean_none_values(v) for k, v in obj.items() if k is not None}
    if isinstance(obj, list):
        return [_clean_none_values(item) for item in obj]
    return obj


def editorial_to_json(session: Session) -> dict:
    """Reconstruct editorial.json from collections."""
    collections = session.query(Collection).all()
    result = {}
    for coll in collections:
        category_name = coll.name.replace("Best ", "").replace(" Picks", "")
        key = re.sub(r"[^a-z0-9_]", "", category_name.lower().replace(" ", "_"))
        if not key:
            key = coll.slug

        items = (
            session.query(CollectionItem)
            .filter_by(collection_id=coll.id)
            .order_by(CollectionItem.sort_order)
            .all()
        )

        editor_choice = None
        best_value = None
        premium_pick = None
        budget_pick = None
        manual_order = []
        excluded = []
        excluded_reasons = {}

        for item in items:
            prod = session.query(Product).filter_by(id=item.product_id).first()
            if not prod:
                continue
            asin = prod.asin
            badge = item.badge or ""
            if badge == "editor_choice":
                editor_choice = asin
            elif badge == "best_value":
                best_value = asin
            elif badge == "premium_pick":
                premium_pick = asin
            elif badge == "budget_pick":
                budget_pick = asin
            else:
                manual_order.append(asin)

        result[key] = {
            "editor_choice": editor_choice,
            "best_value": best_value,
            "premium_pick": premium_pick,
            "budget_pick": budget_pick,
            "manual_order": manual_order,
            "excluded": excluded,
            "excluded_reasons": excluded_reasons,
        }

    return result


# ---------------------------------------------------------------------------
# Main export orchestrator
# ---------------------------------------------------------------------------

class Exporter:
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.stats = {
            "products_exported": 0,
            "files_written": 0,
            "editorial_written": False,
            "errors": 0,
            "error_details": [],
        }

    def run(self):
        engine = create_engine(DB_URL, echo=False)

        with Session(engine) as session:
            products = (
                session.query(Product)
                .options(
                    joinedload(Product.brand),
                    joinedload(Product.categories),
                    joinedload(Product.tags),
                    joinedload(Product.images),
                    joinedload(Product.editorial_score),
                    joinedload(Product.price_history),
                    joinedload(Product.motorcycles),
                )
                .order_by(Product.asin)
                .all()
            )

            self._write_product_files(session, products)
            self._write_editorial(session)

        self._print_summary()

    def _write_product_files(self, session: Session, products: List[Product]):
        products_dir = self.base_dir / "data" / "products"
        products_dir.mkdir(parents=True, exist_ok=True)
        self._products_dir = products_dir

        by_file: Dict[str, list] = {}
        for product in products:
            category = ""
            if product.categories:
                category = product.categories[0].name
            filename = _category_to_file(category)
            if filename not in by_file:
                by_file[filename] = []
            try:
                json_obj = product_to_json(product)
                by_file[filename].append(json_obj)
                self.stats["products_exported"] += 1
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["error_details"].append(
                    f"ASIN={product.asin}: {e}"
                )

        for filename, items in by_file.items():
            filepath = products_dir / filename
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(items, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                self.stats["files_written"] += 1
                logger.info("  Wrote %s (%d products)", filename, len(items))
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["error_details"].append(
                    f"Writing {filename}: {e}"
                )

    def _write_editorial(self, session: Session):
        filepath = self.base_dir / "data" / "editorial.json"
        try:
            data = editorial_to_json(session)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            self.stats["editorial_written"] = True
            logger.info("  Wrote editorial.json (%d categories)", len(data))
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["error_details"].append(f"editorial.json: {e}")

    def _print_summary(self):
        s = self.stats
        sep = "=" * 52
        lines = [
            "",
            sep,
            "  EXPORT SUMMARY",
            sep,
            f"  Products exported      {s['products_exported']}",
            f"  Product files written  {s['files_written']}",
            f"  Editorial written      {'yes' if s['editorial_written'] else 'no'}",
            f"  Errors                 {s['errors']}",
        ]
        if s["error_details"]:
            lines.append(f"  {'-' * 48}")
            for err in s["error_details"][:10]:
                lines.append(f"  x {err}")
            if len(s["error_details"]) > 10:
                lines.append(f"  ... and {len(s['error_details']) - 10} more")
        lines.append(sep)
        print("\n".join(lines))


if __name__ == "__main__":
    Exporter(base_dir=".").run()
