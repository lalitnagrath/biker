"""
Import all product JSON files into SQLite (bikereview.db).

Handles 3 formats:
  - Curated products (data/products/*.json) — nested editorial + amazon objects
  - Amazon deals (bike-deals.json, honda-cb350-deals.json) — PAAPI response
  - Simple import (helmets_new.json, product_importer_final.json) — flat fields

Upserts by ASIN. Creates brand, category, tag, price_history, image,
and editorial_score records alongside the product.
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import (
    Base, Brand, Category, Product, ProductCategory, ProductTag,
    PriceHistory, Image, EditorialScore,
)
from repository import ProductRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("importer")


DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")
PRODUCTS_DIR = Path("data/products")
DEAL_FILES = ["bike-deals.json", "honda-cb350-deals.json"]
SIMPLE_FILES = ["helmets_new.json", "product_importer_final.json"]
CURRENCY = "INR"


# ---------------------------------------------------------------------------
# Format adapters — each returns a list of flat dicts keyed to product fields
# ---------------------------------------------------------------------------

def parse_curated_products(path: Path) -> List[dict]:
    """data/products/*.json — nested editorial + amazon objects."""
    raw = _load_json_array(path)
    out = []
    for rec in raw:
        amazon = rec.get("amazon") or {}
        editorial = rec.get("editorial") or {}
        score_raw = editorial.get("score")
        out.append({
            "asin": rec.get("asin"),
            "title": rec.get("title"),
            "slug": rec.get("slug"),
            "brand": rec.get("brand"),
            "category": rec.get("category"),
            "type": rec.get("type"),
            "status": rec.get("status"),
            "description": rec.get("description"),
            "price": amazon.get("price"),
            "mrp": amazon.get("mrp"),
            "currency": CURRENCY,
            "rating": amazon.get("rating"),
            "review_count": amazon.get("review_count"),
            "availability": amazon.get("availability"),
            "url": amazon.get("affiliate_url"),
            "image": amazon.get("image"),
            "last_updated": amazon.get("last_updated"),
            "score": _normalize_score(score_raw),
            "editorial_verdict": rec.get("verdict"),
            "best_for": rec.get("best_for"),
            "fitment_notes": editorial.get("fitment_notes"),
            "pros": editorial.get("pros"),
            "cons": editorial.get("cons"),
            "features": editorial.get("features"),
            "recommended_for": editorial.get("recommended_for"),
            "editorial_notes": editorial.get("notes"),
            "compatible_bikes": rec.get("compatible_bikes"),
            "tags": rec.get("tags"),
        })
    return out


def parse_amazon_deal(path: Path) -> List[dict]:
    """bike-deals.json / honda-cb350-deals.json — Amazon PAAPI response."""
    raw = _load_json_array(path)
    out = []
    for rec in raw:
        item_info = rec.get("itemInfo") or {}
        title_info = item_info.get("title") or {}
        offers = rec.get("offersV2") or {}
        listings = offers.get("listings") or []
        listing = listings[0] if listings else {}
        price_info = listing.get("price") or {}
        money = price_info.get("money") or {}
        savings = price_info.get("savings") or {}
        saving_basis = price_info.get("savingBasis") or {}
        basis_money = saving_basis.get("money") or {}
        savings_money = savings.get("money") or {}
        images_data = rec.get("images") or {}
        primary_img = images_data.get("primary") or {}
        large = primary_img.get("large") or {}

        out.append({
            "asin": rec.get("asin"),
            "title": title_info.get("displayValue"),
            "url": rec.get("detailPageURL"),
            "price": money.get("amount"),
            "mrp": basis_money.get("amount"),
            "savings_amount": savings_money.get("amount"),
            "savings_pct": rec.get("_savings_pct") or savings.get("percentage"),
            "deal_quality": _infer_deal_quality(rec.get("_quality_score")),
            "score": rec.get("_quality_score"),
            "currency": money.get("currency", CURRENCY),
            "image_url": large.get("url"),
            "image_width": large.get("width"),
            "image_height": large.get("height"),
            "search_keyword": rec.get("_search_keyword"),
            "found_in_category": rec.get("_found_in_category"),
        })
    return out


def parse_simple_import(path: Path) -> List[dict]:
    """helmets_new.json / product_importer_final.json — flat fields."""
    raw = _load_json_array(path)
    out = []
    for rec in raw:
        out.append({
            "asin": rec.get("asin"),
            "title": rec.get("title"),
            "slug": rec.get("slug"),
            "brand": rec.get("brand"),
            "category": rec.get("category"),
            "type": rec.get("type"),
            "status": rec.get("status"),
            "price": rec.get("price"),
            "currency": CURRENCY,
            "score": _normalize_score(rec.get("editor_rating")),
            "editorial_verdict": rec.get("verdict"),
            "best_for": rec.get("best_for"),
            "fitment_notes": rec.get("fitment_notes"),
            "pros": rec.get("pros"),
            "cons": rec.get("cons"),
            "features": rec.get("features"),
            "compatible_bikes": rec.get("compatible_bikes"),
        })
    return out


def parse_product_importer_final(path: Path) -> List[dict]:
    """Handles the comment-separated double-array format of product_importer_final.json."""
    text = path.read_text(encoding="utf-8")
    chunks = re.split(r"^\s*#.*$", text, flags=re.MULTILINE)
    records = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            data = json.loads(chunk)
            if isinstance(data, list):
                for rec in data:
                    records.append({
                        "asin": rec.get("asin"),
                        "title": rec.get("title"),
                        "slug": rec.get("slug"),
                        "brand": rec.get("brand"),
                        "category": rec.get("category"),
                        "type": rec.get("type"),
                        "status": rec.get("status"),
                        "price": rec.get("price"),
                        "currency": CURRENCY,
                        "score": _normalize_score(rec.get("editor_rating")),
                        "editorial_verdict": rec.get("verdict"),
                        "best_for": rec.get("best_for"),
                        "fitment_notes": rec.get("fitment_notes"),
                        "pros": rec.get("pros"),
                        "cons": rec.get("cons"),
                        "features": rec.get("features"),
                        "compatible_bikes": rec.get("compatible_bikes"),
                    })
        except json.JSONDecodeError:
            logger.warning("  Skipping unparseable chunk in %s", path.name)
    return records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json_array(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return []


def _normalize_score(score) -> Optional[float]:
    if score is None:
        return None
    try:
        s = float(score)
        if s > 10:
            return s
        return round(s * 10, 1)
    except (ValueError, TypeError):
        return None


def _infer_deal_quality(qs) -> Optional[str]:
    if qs is None:
        return None
    try:
        q = float(qs)
        if q >= 4.0:
            return "excellent"
        if q >= 3.0:
            return "good"
        return "average"
    except (ValueError, TypeError):
        return None


def _slugify(text: str) -> str:
    return text.lower().replace(" ", "-").replace("/", "-").replace("&", "and")


# ---------------------------------------------------------------------------
# Database writer
# ---------------------------------------------------------------------------

class DatabaseWriter:
    """Holds a session and handles upsert logic for all tables."""

    def __init__(self, session: Session):
        self.session = session
        self._brand_cache: Dict[str, int] = {}
        self._category_cache: Dict[Tuple[str, str], int] = {}

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

    def upsert_product(self, data: dict) -> Product:
        asin = data.get("asin")
        if not asin:
            raise ValueError("Missing ASIN")

        product = self.session.query(Product).filter_by(asin=asin).first()

        if product:
            # Update mutable fields only when new value is not None
            _update_if(data, product, "title")
            _update_if(data, product, "description")
            _update_if(data, product, "url")
            _update_if(data, product, "price")
            _update_if(data, product, "mrp")
            _update_if(data, product, "currency")
            _update_if(data, product, "rating")
            _update_if(data, product, "review_count")
            _update_if(data, product, "bestseller_rank")
            _update_if(data, product, "availability")
            _update_if(data, product, "score")
            _update_if(data, product, "price_tier")
            _update_if(data, product, "deal_quality")
            _update_if(data, product, "editorial_verdict")
            if data.get("brand_id"):
                product.brand_id = data["brand_id"]
            is_new = False
        else:
            product = Product(
                asin=asin,
                title=data.get("title") or "",
                description=data.get("description"),
                url=data.get("url"),
                price=data.get("price"),
                mrp=data.get("mrp"),
                currency=data.get("currency", CURRENCY),
                rating=data.get("rating"),
                review_count=data.get("review_count"),
                bestseller_rank=data.get("bestseller_rank"),
                availability=data.get("availability"),
                brand_id=data.get("brand_id"),
                score=data.get("score") or 0.0,
                price_tier=data.get("price_tier"),
                deal_quality=data.get("deal_quality"),
                editorial_verdict=data.get("editorial_verdict"),
            )
            self.session.add(product)
            is_new = True

        self.session.flush()
        return product, is_new

    def set_categories(self, product_id: int, category_names: List[str],
                       niche: str = "motorcycles"):
        """Replace all categories on a product."""
        self.session.query(ProductCategory).filter_by(product_id=product_id).delete()
        self.session.flush()
        self.add_categories(product_id, category_names, niche)

    def add_categories(self, product_id: int, category_names: List[str],
                       niche: str = "motorcycles"):
        """Add categories without removing existing ones."""
        if not category_names:
            return
        existing = {
            row[0] for row in
            self.session.query(ProductCategory.category_id)
            .filter_by(product_id=product_id)
        }
        for name in category_names:
            cat_id = self.get_or_create_category(name, niche)
            if cat_id and cat_id not in existing:
                self.session.add(ProductCategory(product_id=product_id, category_id=cat_id))

    def add_price_history(self, product_id: int, price, mrp=None,
                          timestamp: Optional[datetime] = None):
        if price is None:
            return
        self.session.add(PriceHistory(
            product_id=product_id,
            old_price=None,
            price=float(price),
            mrp=float(mrp) if mrp is not None else None,
            timestamp=timestamp or datetime.utcnow(),
        ))

    def upsert_editorial_score(self, product_id: int, data: dict):
        score = self.session.query(EditorialScore).filter_by(product_id=product_id).first()
        kwargs = {}
        if data.get("editor_score") is not None:
            kwargs["editor_score"] = data["editor_score"]
        if data.get("pros"):
            kwargs["pros"] = data["pros"]
        if data.get("cons"):
            kwargs["cons"] = data["cons"]
        if data.get("picks"):
            kwargs["picks"] = data["picks"]
        if data.get("featured_in"):
            kwargs["featured_in"] = data["featured_in"]
        if data.get("editorial_notes"):
            kwargs["editorial_notes"] = data["editorial_notes"]

        if not kwargs:
            return

        if score:
            for k, v in kwargs.items():
                setattr(score, k, v)
        else:
            self.session.add(EditorialScore(product_id=product_id, **kwargs))

    def add_image(self, product_id: int, url: str, variant: str = "full",
                  is_primary: bool = False, local_path: Optional[str] = None,
                  width: Optional[int] = None, height: Optional[int] = None):
        if not url:
            return
        self.session.add(Image(
            product_id=product_id,
            url=url,
            variant=variant,
            is_primary=is_primary,
            local_path=local_path,
            width=width,
            height=height,
        ))

    def add_tags(self, product_id: int, tags: List[str]):
        if not tags:
            return
        existing = {
            pt.tag
            for pt in self.session.query(ProductTag).filter_by(product_id=product_id)
        }
        for tag in tags:
            tag = tag.strip().lower().replace(" ", "-")
            if tag and tag not in existing:
                self.session.add(ProductTag(product_id=product_id, tag=tag))
                existing.add(tag)


def _update_if(src: dict, dest: Product, field: str):
    val = src.get(field)
    if val is not None:
        setattr(dest, field, val)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Importer:
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.stats = {
            "files": 0,
            "records": 0,
            "inserted": 0,
            "updated": 0,
            "skipped_no_asin": 0,
            "errors": 0,
            "error_details": [],
        }

    def run(self):
        engine = create_engine(DB_URL, echo=False)
        Base.metadata.create_all(engine)

        tasks = []

        # 1. Curated product files
        products_dir = self.base_dir / PRODUCTS_DIR
        if products_dir.is_dir():
            for fpath in sorted(products_dir.glob("*.json")):
                tasks.append((fpath, parse_curated_products))

        # 2. Amazon deal files
        for name in DEAL_FILES:
            fpath = self.base_dir / name
            if fpath.is_file():
                tasks.append((fpath, parse_amazon_deal))

        # 3. Simple import files
        for name in SIMPLE_FILES:
            fpath = self.base_dir / name
            if fpath.is_file():
                parser = parse_product_importer_final if name == "product_importer_final.json" else parse_simple_import
                tasks.append((fpath, parser))

        logger.info("Found %d files to import", len(tasks))

        with Session(engine) as session:
            writer = DatabaseWriter(session)
            for fpath, parser in tasks:
                self._import_file(fpath, parser, writer)
            session.commit()

        self._print_summary()

    def _import_file(self, fpath: Path, parser, writer: DatabaseWriter):
        self.stats["files"] += 1
        logger.info("[%s] Reading …", fpath.name)
        try:
            records = parser(fpath)
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["error_details"].append(f"{fpath.name}: parse failed — {e}")
            logger.error("  Parse error: %s", e)
            return

        if not records:
            logger.info("  No records found.")
            return

        self.stats["records"] += len(records)
        imported = 0

        for rec in records:
            try:
                self._import_record(rec, writer)
                imported += 1
            except Exception as e:
                self.stats["errors"] += 1
                asin = rec.get("asin", "?")
                self.stats["error_details"].append(f"{fpath.name}  ASIN={asin}: {e}")
                logger.error("  Error [%s]: %s", asin, e)

        logger.info("  Imported %d / %d records", imported, len(records))

    def _import_record(self, rec: dict, writer: DatabaseWriter):
        asin = rec.get("asin")
        if not asin or not asin.strip():
            self.stats["skipped_no_asin"] += 1
            return

        # Brand
        brand_id = writer.get_or_create_brand(rec.get("brand"))
        rec["brand_id"] = brand_id

        # Product (upsert)
        product, is_new = writer.upsert_product(rec)
        if is_new:
            self.stats["inserted"] += 1
        else:
            self.stats["updated"] += 1

        pid = product.id

        # Categories — derive from primary type, subtype, and metadata signals
        cats = ProductRepository.derive_category_names(
            primary=rec.get("category"),
            subtype=rec.get("type"),
            recommended=rec.get("recommended_for"),
            extra_tags=rec.get("tags"),
        )
        if is_new:
            writer.set_categories(pid, cats)
        else:
            writer.add_categories(pid, cats)

        # Tags from recommended_for
        tags = rec.get("tags") or []
        if rec.get("recommended_for"):
            tags.extend(rec["recommended_for"])
        if rec.get("search_keyword"):
            tags.append(rec["search_keyword"])
        if tags:
            writer.add_tags(pid, tags)

        # Price history
        if rec.get("price") is not None:
            writer.add_price_history(pid, rec["price"], rec.get("mrp"))

        # Image
        if rec.get("image_url"):
            writer.add_image(pid, rec["image_url"], variant="full", is_primary=True)
        if rec.get("image"):
            img_path = rec["image"]
            if not img_path.startswith("http"):
                img_path = str(self.base_dir / img_path)
            writer.add_image(pid, img_path, variant="full", is_primary=True,
                             local_path=rec.get("image"))

        # Editorial score
        editorial_data = {
            "editor_score": rec.get("score"),
            "pros": rec.get("pros"),
            "cons": rec.get("cons"),
            "editorial_notes": rec.get("editorial_notes") or rec.get("fitment_notes"),
        }
        picks = {}
        if rec.get("best_for"):
            picks["best_for"] = rec["best_for"]
        if picks:
            editorial_data["picks"] = picks
        writer.upsert_editorial_score(pid, editorial_data)

    def _print_summary(self):
        s = self.stats
        sep = "=" * 52
        lines = [
            "",
            sep,
            "  IMPORT SUMMARY",
            sep,
            f"  Files processed       {s['files']}",
            f"  Records found         {s['records']}",
            f"  Inserted              {s['inserted']}",
            f"  Updated               {s['updated']}",
            f"  Skipped (no ASIN)     {s['skipped_no_asin']}",
            f"  Errors                {s['errors']}",
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
    Importer(base_dir=".").run()
