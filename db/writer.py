"""
DatabaseWriter — writes flat product dicts (from sync_engine / product_importer)
directly to SQLite, bypassing JSON file I/O.

Usage:
    with DatabaseWriter() as w:
        for product in flat_products:
            w.save_product(product)
        w.commit()
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.base import Base
from db.models import (
    EditorialScore, Image, PriceHistory, Product,
    ProductCategory, ProductMotorcycle, ProductTag,
)

DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")
CURRENCY = "INR"

# Map JSON statuses to DB statuses
_STATUS_MAP = {
    "approved": "active",
    "draft": "draft",
    "review": "review",
    "hidden": "hidden",
    "out_of_stock": "out_of_stock",
    "discontinued": "discontinued",
}


def _slugify(text: str) -> str:
    return text.lower().replace(" ", "-").replace("/", "-").replace("&", "and")


class DatabaseWriter:
    """Context manager wrapping a DB session for bulk product writes.

    Usage:
        with DatabaseWriter() as w:
            for product in flat_products:
                w.save_product(product)
            w.commit()
    """

    def __init__(self, db_url: Optional[str] = None):
        self.engine = create_engine(db_url or DB_URL, echo=False)
        self.session: Optional[Session] = None

    def __enter__(self):
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self._brand_cache: Dict[str, int] = {}
        self._category_cache: Dict[Tuple[str, str], int] = {}
        self._motorcycle_cache: Dict[str, int] = {}
        return self

    def __exit__(self, *args):
        if self.session:
            try:
                self.session.commit()
            finally:
                self.session.close()

    def commit(self):
        self.session.commit()

    # ------------------------------------------------------------------
    # Cached lookups
    # ------------------------------------------------------------------

    def _get_or_create_brand(self, name: Optional[str]) -> Optional[int]:
        from db.models import Brand
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

    def _get_or_create_category(self, name: str, niche: str = "motorcycles") -> Optional[int]:
        from db.models import Category
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

    def _get_or_create_motorcycle(self, slug: str) -> Optional[int]:
        from db.models import Motorcycle
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

    # ------------------------------------------------------------------
    # Main upsert
    # ------------------------------------------------------------------

    def save_product(self, flat: dict) -> Tuple[Optional[Product], bool]:
        """Upsert a single product from a flat dict.

        Returns (Product, is_new) or (None, False) if missing ASIN.
        Handles: brand, categories, editorial, images, compatibility,
        price_history, and tags.
        """
        asin = flat.get("asin")
        if not asin:
            return None, False

        brand_id = self._get_or_create_brand(flat.get("brand"))

        status = _STATUS_MAP.get(flat.get("status", "approved"), "active")
        last_updated_raw = flat.get("last_updated")
        last_sync_at = None
        if last_updated_raw:
            try:
                last_sync_at = datetime.fromisoformat(last_updated_raw)
            except (ValueError, TypeError):
                pass

        product = self.session.query(Product).filter_by(asin=asin).first()

        if product:
            product.slug = flat.get("slug", product.slug)
            product.title = flat.get("title", product.title)
            if brand_id is not None:
                product.brand_id = brand_id
            product.niche = "motorcycles"
            if flat.get("price") is not None:
                product.price = flat["price"]
            if flat.get("mrp") is not None:
                product.mrp = flat["mrp"]
            if flat.get("rating") is not None:
                product.rating = flat["rating"]
            if flat.get("review_count") is not None:
                product.review_count = flat["review_count"]
            if flat.get("availability") is not None:
                product.availability = flat["availability"]
            product.status = status
            if last_sync_at is not None:
                product.last_sync_at = last_sync_at
            product.url = flat.get("affiliate_url", product.url)
            product.editorial_verdict = flat.get("editorial_verdict", product.editorial_verdict)
            is_new = False
        else:
            product = Product(
                asin=asin,
                slug=flat.get("slug"),
                title=flat.get("title") or "",
                url=flat.get("affiliate_url"),
                brand_id=brand_id,
                niche="motorcycles",
                price=flat.get("price"),
                mrp=flat.get("mrp"),
                currency=CURRENCY,
                rating=flat.get("rating"),
                review_count=flat.get("review_count"),
                availability=flat.get("availability"),
                status=status,
                editorial_verdict=flat.get("editorial_verdict"),
                last_sync_at=last_sync_at,
                score=0.0,
                is_featured=False,
            )
            self.session.add(product)
            is_new = True

        self.session.flush()
        pid = product.id

        if is_new:
            self._set_categories(pid, flat.get("category"), flat.get("type"))
            self._set_images(pid, flat.get("image"))
            self._set_compatibility(pid, flat.get("compatible_bikes", []))
            self._set_tags(pid, flat)

        self._upsert_editorial(pid, flat)
        self._add_price_history(pid, flat.get("price"), flat.get("mrp"))
        self._set_images(pid, flat.get("image"))

        return product, is_new

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_categories(self, product_id: int, category: Optional[str],
                        type_: Optional[str]):
        self.session.query(ProductCategory).filter_by(
            product_id=product_id).delete()
        self.session.flush()
        names = []
        if category:
            names.append(category)
        if type_:
            names.append(type_)
        for name in names:
            cat_id = self._get_or_create_category(name)
            if cat_id:
                self.session.add(
                    ProductCategory(product_id=product_id, category_id=cat_id))

    def _set_images(self, product_id: int, image_url: Optional[str]):
        self.session.query(Image).filter_by(product_id=product_id).delete()
        if image_url:
            self.session.add(Image(
                product_id=product_id,
                url=image_url,
                variant="full",
                is_primary=True,
                local_path=image_url if not image_url.startswith("http") else None,
            ))

    def _upsert_editorial(self, product_id: int, flat: dict):
        score = self.session.query(EditorialScore).filter_by(
            product_id=product_id).first()
        if not score:
            score = EditorialScore(product_id=product_id)
            self.session.add(score)

        if flat.get("editor_rating") is not None:
            score.editor_score = flat["editor_rating"]
        if "pros" in flat:
            score.pros = flat["pros"] or []
        if "cons" in flat:
            score.cons = flat["cons"] or []
        if "features" in flat:
            score.features = flat["features"] or []
        if "recommended_for" in flat:
            score.recommended_for = flat["recommended_for"] or []
        if "editorial_notes" in flat:
            score.editorial_notes = flat["editorial_notes"] or ""
        if "editors_choice" in flat:
            score.editors_choice = bool(flat["editors_choice"])
        if "override_rank" in flat:
            score.override_rank = flat["override_rank"] or 0

        picks = {}
        if flat.get("best_for"):
            picks["best_for"] = flat["best_for"]
        if flat.get("verdict"):
            picks["verdict"] = flat["verdict"]
        if flat.get("fitment_notes"):
            picks["fitment_notes"] = flat["fitment_notes"]
        if picks:
            score.picks = picks

    def _add_price_history(self, product_id: int, price, mrp=None):
        if price is not None:
            self.session.add(PriceHistory(
                product_id=product_id,
                old_price=None,
                price=float(price),
                mrp=float(mrp) if mrp is not None else None,
            ))

    def _set_compatibility(self, product_id: int, bike_slugs: List[str]):
        self.session.query(ProductMotorcycle).filter_by(
            product_id=product_id).delete()
        for slug in bike_slugs:
            bike_id = self._get_or_create_motorcycle(slug)
            if bike_id:
                self.session.add(ProductMotorcycle(
                    product_id=product_id,
                    motorcycle_id=bike_id,
                    match_strategy="sync_engine",
                ))

    def _set_tags(self, product_id: int, flat: dict):
        self.session.query(ProductTag).filter_by(product_id=product_id).delete()
        tags = set()
        for r in flat.get("recommended_for", []):
            t = r.strip().lower().replace(" ", "-")
            if t:
                tags.add(t)
        for tag in tags:
            self.session.add(ProductTag(product_id=product_id, tag=tag))

    # ------------------------------------------------------------------
    # Batch convenience
    # ------------------------------------------------------------------

    def save_products(self, products: List[dict]) -> int:
        """Upsert multiple products. Returns count."""
        count = 0
        for p in products:
            try:
                self.save_product(p)
                count += 1
            except (ValueError, Exception):
                pass
        self.commit()
        return count
