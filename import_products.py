"""
Import all existing JSON data into SQLite.

Reads from:
  - data/products/*.json        (curated product catalog)
  - data/editorial.json         (editorial picks / collections)
  - data/motorcycles/*.json     (motorcycle library)
  - data/brands/*.json          (brand profiles)

Upserts by ASIN — safe to run repeatedly.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.base import Base
from db.models import (
    Brand, Category, Collection, CollectionItem, EditorialScore,
    Image, Motorcycle, PriceHistory, Product, ProductCategory,
    ProductMotorcycle, ProductTag, Setting,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("import_products")

DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")
CURRENCY = "INR"

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


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    return text.lower().replace(" ", "-").replace("/", "-").replace("&", "and")


class DatabaseWriter:
    """Holds a session and handles upsert logic for all tables."""

    def __init__(self, session: Session):
        self.session = session
        self._brand_cache: Dict[str, int] = {}
        self._category_cache: Dict[Tuple[str, str], int] = {}
        self._motorcycle_cache: Dict[str, int] = {}

    def get_or_create_brand(self, name: str) -> Optional[int]:
        if not name or not name.strip():
            return None
        name = name.strip()
        if name in self._brand_cache:
            return self._brand_cache[name]
        brand = self.session.query(Brand).filter_by(name=name).first()
        if not brand:
            brand = Brand(name=name, slug=_slugify(name))
            self.session.add(brand)
            self.session.flush()
        self._brand_cache[name] = brand.id
        return brand.id

    def get_or_create_category(self, name: str, niche: str = "motorcycles") -> Optional[int]:
        if not name or not name.strip():
            return None
        name = name.strip()
        key = (name, niche)
        if key in self._category_cache:
            return self._category_cache[key]
        cat = self.session.query(Category).filter_by(name=name, niche=niche).first()
        if not cat:
            cat = Category(name=name, slug=_slugify(name), niche=niche)
            self.session.add(cat)
            self.session.flush()
        self._category_cache[key] = cat.id
        return cat.id

    def get_or_create_motorcycle(self, slug: str) -> Optional[int]:
        if not slug or not slug.strip() or slug == "*":
            return None
        key = slug.strip()
        if key in self._motorcycle_cache:
            return self._motorcycle_cache[key]
        bike = self.session.query(Motorcycle).filter_by(slug=key).first()
        if not bike:
            bike = Motorcycle(make="Unknown", model=key, slug=key)
            self.session.add(bike)
            self.session.flush()
        self._motorcycle_cache[key] = bike.id
        return bike.id

    def upsert_product(self, data: dict) -> Tuple[Product, bool]:
        asin = data.get("asin")
        if not asin:
            raise ValueError("Missing ASIN")

        product = self.session.query(Product).filter_by(asin=asin).first()

        if product:
            for field in ("slug", "title", "description", "url", "price", "mrp",
                          "currency", "rating", "review_count", "availability",
                          "score", "editorial_verdict", "status", "is_featured",
                          "image", "amazon_image_url"):
                val = data.get(field)
                if val is not None:
                    setattr(product, field, val)
            if data.get("last_sync_at") is not None:
                product.last_sync_at = data["last_sync_at"]
            if data.get("brand_id") is not None:
                product.brand_id = data["brand_id"]
            is_new = False
        else:
            product = Product(
                asin=asin,
                slug=data.get("slug"),
                title=data.get("title") or "",
                description=data.get("description"),
                niche=data.get("niche", "motorcycles"),
                url=data.get("url"),
                price=data.get("price"),
                mrp=data.get("mrp"),
                currency=data.get("currency", CURRENCY),
                rating=data.get("rating"),
                review_count=data.get("review_count"),
                    availability=data.get("availability"),
                    brand_id=data.get("brand_id"),
                    score=data.get("score") or 0.0,
                    editorial_verdict=data.get("editorial_verdict"),
                    last_sync_at=(
                        datetime.fromisoformat(data["last_updated"])
                        if data.get("last_updated")
                        else None
                    ),
                    status=data.get("status", "active"),
                    is_featured=bool(data.get("is_featured")),
                    image=data.get("image"),
                    amazon_image_url=data.get("amazon_image_url"),
            )
            self.session.add(product)
            is_new = True

        self.session.flush()
        return product, is_new

    def set_categories(self, product_id: int, category_names: List[str],
                       niche: str = "motorcycles"):
        self.session.query(ProductCategory).filter_by(product_id=product_id).delete()
        self.session.flush()
        for name in category_names:
            cat_id = self.get_or_create_category(name, niche)
            if cat_id:
                self.session.add(ProductCategory(product_id=product_id, category_id=cat_id))

    def set_tags(self, product_id: int, tags: List[str]):
        self.session.query(ProductTag).filter_by(product_id=product_id).delete()
        for tag in tags:
            tag = tag.strip().lower().replace(" ", "-")
            if tag:
                self.session.add(ProductTag(product_id=product_id, tag=tag))

    def set_images(self, product_id: int, images: List[Dict[str, Any]]):
        self.session.query(Image).filter_by(product_id=product_id).delete()
        for i, img in enumerate(images):
            self.session.add(Image(
                product_id=product_id,
                url=img.get("url", ""),
                local_path=img.get("local_path"),
                variant=img.get("variant", "full"),
                width=img.get("width"),
                height=img.get("height"),
                is_primary=bool(img.get("is_primary")),
                sort_order=img.get("sort_order", i),
            ))

    def upsert_editorial_score(self, product_id: int, data: dict):
        score = self.session.query(EditorialScore).filter_by(product_id=product_id).first()
        if not score:
            score = EditorialScore(product_id=product_id)
            self.session.add(score)

        for field in ("editor_score", "pros", "cons", "features", "picks",
                       "recommended_for", "editorial_notes", "editors_choice",
                       "override_rank"):
            if field in data:
                setattr(score, field, data[field])

    def add_price_history(self, product_id: int, price, mrp=None):
        if price is not None:
            self.session.add(PriceHistory(
                product_id=product_id,
                old_price=None,
                price=float(price),
                mrp=float(mrp) if mrp is not None else None,
            ))

    def set_compatibility(self, product_id: int, bike_slugs: List[str]):
        self.session.query(ProductMotorcycle).filter_by(product_id=product_id).delete()
        for slug in bike_slugs:
            bike_id = self.get_or_create_motorcycle(slug)
            if bike_id:
                self.session.add(ProductMotorcycle(
                    product_id=product_id,
                    motorcycle_id=bike_id,
                    match_strategy="json_import",
                ))

    def upsert_collection(self, category: str, niche: str,
                          data: dict) -> Optional[int]:
        slug = _slugify(f"{category}-editorial-picks")
        coll = self.session.query(Collection).filter_by(slug=slug).first()
        if not coll:
            coll = Collection(
                name=f"Best {category} Picks",
                slug=slug,
                niche=niche,
                description=f"Editor-curated picks for {category}",
            )
            self.session.add(coll)
            self.session.flush()

        # Clear existing items
        self.session.query(CollectionItem).filter_by(collection_id=coll.id).delete()
        self.session.flush()

        sort_order = 0
        added_asins = set()
        labels_map = {
            "editor_choice": "editor_choice",
            "best_value": "best_value",
            "premium_pick": "premium_pick",
            "budget_pick": "budget_pick",
        }
        for key, badge in labels_map.items():
            asin = data.get(key)
            if asin and asin not in added_asins:
                product = self.session.query(Product).filter_by(asin=asin).first()
                if product:
                    self.session.add(CollectionItem(
                        collection_id=coll.id,
                        product_id=product.id,
                        sort_order=sort_order,
                        badge=badge,
                    ))
                    added_asins.add(asin)
                    sort_order += 1

        for asin in data.get("manual_order", []):
            if asin not in added_asins:
                product = self.session.query(Product).filter_by(asin=asin).first()
                if product:
                    self.session.add(CollectionItem(
                        collection_id=coll.id,
                        product_id=product.id,
                        sort_order=sort_order,
                    ))
                    added_asins.add(asin)
                    sort_order += 1

        return coll.id


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_products_file(path: Path) -> List[dict]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    items = raw if isinstance(raw, list) else [raw]
    records = []
    for rec in items:
        amazon = rec.get("amazon") or {}
        editorial = rec.get("editorial") or {}
        records.append({
            "asin": rec.get("asin"),
            "slug": rec.get("slug"),
            "title": rec.get("title"),
            "brand": rec.get("brand"),
            "category": rec.get("category"),
            "type": rec.get("type"),
            "status": _normalize_status(rec.get("status")),
            "description": rec.get("description"),
            "price": amazon.get("price"),
            "mrp": amazon.get("mrp"),
            "currency": CURRENCY,
            "rating": amazon.get("rating"),
            "review_count": amazon.get("review_count"),
            "availability": amazon.get("availability"),
            "url": amazon.get("affiliate_url"),
            "image": amazon.get("image"),
            "amazon_image_url": amazon.get("image"),
            "last_updated": amazon.get("last_updated"),
            "score": editorial.get("score", 0),
            "editorial_verdict": editorial.get("verdict_label", ""),
            "best_for": rec.get("best_for"),
            "verdict": rec.get("verdict"),
            "fitment_notes": editorial.get("fitment_notes"),
            "pros": editorial.get("pros", []),
            "cons": editorial.get("cons", []),
            "features": editorial.get("features", []),
            "recommended_for": editorial.get("recommended_for", []),
            "editorial_notes": editorial.get("notes", ""),
            "editors_choice": editorial.get("editors_choice", False),
            "override_rank": editorial.get("override_rank", 0),
            "compatible_bikes": rec.get("compatible_bikes", ["*"]),
            "tags": rec.get("tags", []),
            "pricing": amazon.get("pricing"),
        })
    return records


def parse_motorcycle_file(path: Path) -> Optional[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_editorial_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_status(status: Optional[str]) -> str:
    if not status:
        return "active"
    mapping = {
        "approved": "active",
        "draft": "draft",
        "review": "review",
        "hidden": "hidden",
        "out_of_stock": "out_of_stock",
        "discontinued": "discontinued",
    }
    return mapping.get(status, "active")


def _reverse_status(db_status: str) -> str:
    mapping = {
        "active": "approved",
        "draft": "draft",
        "review": "review",
        "hidden": "hidden",
        "out_of_stock": "out_of_stock",
        "discontinued": "discontinued",
    }
    return mapping.get(db_status, "approved")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

class Importer:
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.stats = {
            "product_files": 0,
            "products_found": 0,
            "products_inserted": 0,
            "products_updated": 0,
            "brands_created": 0,
            "motorcycles_created": 0,
            "categories_created": 0,
            "collections_created": 0,
            "skipped": 0,
            "errors": 0,
            "error_details": [],
        }

    def run(self):
        engine = create_engine(DB_URL, echo=False)
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            writer = DatabaseWriter(session)

            self._import_motorcycles(session, writer)
            self._import_brands(session)
            self._import_products(session, writer)
            self._import_editorial(session, writer)

            session.commit()

        self._print_summary()

    def _import_motorcycles(self, session: Session, writer: DatabaseWriter):
        moto_dir = self.base_dir / "data" / "motorcycles"
        if not moto_dir.is_dir():
            return
        for fpath in sorted(moto_dir.glob("*.json")):
            try:
                data = parse_motorcycle_file(fpath)
                if not data:
                    continue
                slug = data.get("slug", fpath.stem)
                brand_name = data.get("brand", "Unknown")
                model = data.get("model", fpath.stem)
                engine_cc = data.get("engine", "")
                if engine_cc:
                    import re
                    m = re.search(r"(\d+)", str(engine_cc))
                    engine_cc = int(m.group(1)) if m else None
                writer.get_or_create_brand(brand_name)

                existing = session.query(Motorcycle).filter_by(slug=slug).first()
                if existing:
                    existing.make = brand_name
                    existing.model = model
                    existing.slug = slug
                    if data.get("type"):
                        existing.type = data["type"]
                    writer._motorcycle_cache[slug] = existing.id
                    continue

                bike = Motorcycle(
                    make=brand_name,
                    model=model,
                    slug=slug,
                    type=data.get("type"),
                    engine_cc=engine_cc,
                    category=data.get("category"),
                )
                session.add(bike)
                session.flush()
                writer._motorcycle_cache[slug] = bike.id
                self.stats["motorcycles_created"] += 1
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["error_details"].append(f"motorcycle {fpath.name}: {e}")

    def _import_brands(self, session: Session):
        brands_dir = self.base_dir / "data" / "brands"
        if not brands_dir.is_dir():
            return
        for fpath in sorted(brands_dir.glob("*.json")):
            try:
                data = parse_motorcycle_file(fpath)
                if not data:
                    continue
                name = data.get("name", fpath.stem)
                existing = session.query(Brand).filter_by(name=name).first()
                if existing:
                    continue
                brand = Brand(
                    name=name,
                    slug=data.get("slug", _slugify(name)),
                    description=data.get("description"),
                )
                session.add(brand)
                session.flush()
                self.stats["brands_created"] += 1
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["error_details"].append(f"brand {fpath.name}: {e}")

    def _import_products(self, session: Session, writer: DatabaseWriter):
        products_dir = self.base_dir / "data" / "products"
        if not products_dir.is_dir():
            logger.warning("No products directory found at %s", products_dir)
            return

        for fpath in sorted(products_dir.glob("*.json")):
            self.stats["product_files"] += 1
            try:
                records = parse_products_file(fpath)
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["error_details"].append(f"{fpath.name}: parse error — {e}")
                continue

            if not records:
                continue

            self.stats["products_found"] += len(records)

            for rec in records:
                try:
                    self._import_record(rec, writer)
                except Exception as e:
                    self.stats["errors"] += 1
                    asin = rec.get("asin", "?")
                    self.stats["error_details"].append(
                        f"{fpath.name} ASIN={asin}: {e}"
                    )
                    logger.error("  Error [%s]: %s", asin, e)

    def _import_record(self, rec: dict, writer: DatabaseWriter):
        asin = rec.get("asin")
        if not asin:
            self.stats["skipped"] += 1
            return

        brand_id = writer.get_or_create_brand(rec.get("brand"))
        rec["brand_id"] = brand_id
        rec["is_featured"] = rec.get("status") == "active" and rec.get("score", 0) >= 70

        product, is_new = writer.upsert_product(rec)
        if is_new:
            self.stats["products_inserted"] += 1
        else:
            self.stats["products_updated"] += 1

        pid = product.id

        build_categories(pid, rec, writer)

        build_tags(pid, rec, writer)

        build_images(pid, rec, writer)

        build_editorial(pid, rec, writer)

        build_price_history(pid, rec, writer)

        build_compatibility(pid, rec, writer)

    def _import_editorial(self, session: Session, writer: DatabaseWriter):
        path = self.base_dir / "data" / "editorial.json"
        if not path.is_file():
            logger.warning("No editorial.json found at %s", path)
            return
        try:
            data = parse_editorial_json(path)
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["error_details"].append(f"editorial.json: {e}")
            return

        for category, picks in data.items():
            try:
                writer.get_or_create_category(category)
                writer.upsert_collection(category, "motorcycles", picks)
                self.stats["collections_created"] += 1
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["error_details"].append(
                    f"editorial.json category={category}: {e}"
                )

    def _print_summary(self):
        s = self.stats
        sep = "=" * 52
        lines = [
            "",
            sep,
            "  IMPORT SUMMARY",
            sep,
            f"  Product files          {s['product_files']}",
            f"  Products found         {s['products_found']}",
            f"  Products inserted      {s['products_inserted']}",
            f"  Products updated       {s['products_updated']}",
            f"  Brands created         {s['brands_created']}",
            f"  Motorcycles created    {s['motorcycles_created']}",
            f"  Categories created     {s['categories_created']}",
            f"  Collections created    {s['collections_created']}",
            f"  Skipped (no ASIN)      {s['skipped']}",
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


# ---------------------------------------------------------------------------
# Build helpers (separated for clarity / reuse by export)
# ---------------------------------------------------------------------------

def build_categories(pid: int, rec: dict, writer: DatabaseWriter):
    cats = [rec.get("category")] if rec.get("category") else []
    if rec.get("type"):
        cats.append(rec["type"])
    if cats:
        writer.set_categories(pid, cats)


def build_tags(pid: int, rec: dict, writer: DatabaseWriter):
    tags = list(rec.get("tags", []))
    for r in rec.get("recommended_for", []):
        t = r.strip().lower().replace(" ", "-")
        if t and t not in tags:
            tags.append(t)
    writer.set_tags(pid, tags)


def build_images(pid: int, rec: dict, writer: DatabaseWriter):
    images = []
    img = rec.get("image")
    amazon_img = rec.get("amazon_image_url")
    all_urls = []
    if img:
        all_urls.append(img)
    if amazon_img and amazon_img not in all_urls:
        all_urls.append(amazon_img)
    for i, url in enumerate(all_urls):
        if not url:
            continue
        local_path = None
        if not url.startswith("http"):
            local_path = url
        else:
            local_path = _download_image(url, pid, i)
        images.append({
            "url": url,
            "local_path": local_path,
            "variant": "full",
            "is_primary": (i == 0),
            "sort_order": i,
        })
    if images:
        writer.set_images(pid, images)


def _download_image(url: str, product_id: int, index: int) -> str:
    import urllib.request
    import urllib.error
    products_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "images", "products")
    os.makedirs(products_dir, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        ext = ".jpg"
        content_type = resp.headers.get("Content-Type", "")
        if "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"
        filename = f"product-{product_id}-{index}{ext}"
        filepath = os.path.join(products_dir, filename)
        with open(filepath, "wb") as f:
            f.write(data)
        return f"images/products/{filename}"
    except Exception:
        return ""


def build_editorial(pid: int, rec: dict, writer: DatabaseWriter):
    editorial_data = {
        "editor_score": rec.get("score", 0),
        "pros": rec.get("pros", []),
        "cons": rec.get("cons", []),
        "features": rec.get("features", []),
        "recommended_for": rec.get("recommended_for", []),
        "editorial_notes": rec.get("editorial_notes", ""),
        "editors_choice": rec.get("editors_choice", False),
        "override_rank": rec.get("override_rank", 0),
    }
    picks = {}
    if rec.get("best_for"):
        picks["best_for"] = rec["best_for"]
    if rec.get("verdict"):
        picks["verdict"] = rec["verdict"]
    if rec.get("fitment_notes"):
        picks["fitment_notes"] = rec["fitment_notes"]
    if picks:
        editorial_data["picks"] = picks
    writer.upsert_editorial_score(pid, editorial_data)


def build_price_history(pid: int, rec: dict, writer: DatabaseWriter):
    if rec.get("price") is not None:
        writer.add_price_history(pid, rec["price"], rec.get("mrp"))


def build_compatibility(pid: int, rec: dict, writer: DatabaseWriter):
    bikes = rec.get("compatible_bikes", [])
    if bikes and bikes != ["*"]:
        writer.set_compatibility(pid, bikes)


if __name__ == "__main__":
    Importer(base_dir=".").run()
