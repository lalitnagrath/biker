"""
ProductService — provides product data to the website generator without
exposing SQLAlchemy or SQL.

All methods return flat dicts identical in structure to what
product_library.load_products() returns (the "flat product" format).
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, joinedload

from db.models import (
    AccessoryType, Brand, Category, EditorialScore, Image,
    Motorcycle, PriceHistory, Product, ProductCategory, ProductMotorcycle,
)
from db.compatibility_service import CompatibilityService

DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")
CURRENCY = "INR"
PRICING_SOURCE_DB = "database"

# Reverse status mapping: DB status -> JSON status
_REVERSE_STATUS = {
    "active": "approved",
    "draft": "draft",
    "review": "review",
    "hidden": "hidden",
    "out_of_stock": "out_of_stock",
    "discontinued": "discontinued",
}

CANONICAL_CATEGORIES = {
    "helmet", "phone-mount", "tyre-inflator", "engine-oil",
    "chain-lube", "chain-cleaner", "bike-cover", "jackets",
    "gloves", "saddle-bag", "tail-bag", "tank-bag", "knee-guard",
    "ear-plugs", "action-camera", "dash-cam", "seat-cover",
    "riding-pants", "handlebar-grip", "mirror", "windshield",
    "gps-tracker", "headlight", "indicator", "horn", "charger",
    "footrest", "chain-lock", "disc-lock", "alarm", "tool-kit",
    "polish", "crash-guard",
}


def _build_pricing(current=None, mrp=None, discount_percent=None,
                   currency=CURRENCY, last_updated=None, source=PRICING_SOURCE_DB):
    return {
        "current": current,
        "mrp": mrp or current,
        "discount_percent": discount_percent,
        "currency": currency,
        "last_updated": last_updated.isoformat() if isinstance(last_updated, datetime) else last_updated,
        "source": source,
    }


def _calc_discount(price, mrp):
    if price and mrp and mrp > price:
        return int(round((mrp - price) / mrp * 100))
    return None


def _slugify(text: str) -> str:
    return text.lower().replace(" ", "-").replace("/", "-").replace("&", "and")


def _maybe_int(val):
    """Convert float to int if it's a whole number (matches JSON behavior)."""
    if val is None:
        return None
    if isinstance(val, float) and val == int(val):
        return int(val)
    return val


class ProductService:
    """Read-only product service for the static site generator.

    All methods return flat dicts matching the format consumed by
    product_engine and Jinja2 templates.
    """

    def __init__(self, db_url: Optional[str] = None):
        self._engine = create_engine(db_url or DB_URL, echo=False)
        self._products: List[dict] = []
        self._by_asin: Dict[str, dict] = {}
        self._by_slug: Dict[str, dict] = {}
        self._by_category: Dict[str, List[dict]] = {}
        self._quality_dashboard: Optional[dict] = None
        self._compat_service: Optional[CompatibilityService] = None

    @property
    def _compat(self) -> CompatibilityService:
        if self._compat_service is None:
            self._compat_service = CompatibilityService(
                Session(self._engine)
            )
        return self._compat_service

    # ------------------------------------------------------------------
    # Public API matching generator needs
    # ------------------------------------------------------------------

    def load_all(self) -> List[dict]:
        """Load all products from DB, returning flat dicts.

        Call this once at startup.  Subsequent calls return cached data.
        """
        if self._products:
            return self._products

        products = self._fetch_from_db()
        self._normalize_categories(products)
        self._apply_quality_pipeline(products)
        self._regenerate_slugs(products)
        self._index_products(products)
        self._products = products
        return products

    def get_quality_dashboard(self) -> Optional[dict]:
        return self._quality_dashboard

    def get_product(self, slug: str) -> Optional[dict]:
        return self._by_slug.get(slug)

    def get_products_by_category(self, category: str) -> List[dict]:
        return list(self._by_category.get(category, []))

    def get_products_by_collection(self, collection_slug: str) -> List[dict]:
        """Return products in a collection (editorial picks)."""
        from db.models import Collection, CollectionItem
        with Session(self._engine) as session:
            coll = (
                session.query(Collection)
                .filter_by(slug=collection_slug)
                .first()
            )
            if not coll:
                return []
            items = (
                session.query(CollectionItem)
                .filter_by(collection_id=coll.id)
                .order_by(CollectionItem.sort_order)
                .all()
            )
            return [self._by_asin.get(i.product.asin, {}) for i in items if i.product and i.product.asin in self._by_asin]

    def get_related_products(self, product_slug: str, max_results: int = 6) -> List[dict]:
        """Find products in the same category, excluding the given product."""
        product = self._by_slug.get(product_slug)
        if not product:
            return []
        category = product.get("category", "")
        same_cat = self._by_category.get(category, [])
        return [p for p in same_cat if p.get("slug") != product_slug][:max_results]

    def get_motorcycle_products(self, bike_slug: str) -> List[dict]:
        """Return products compatible with a given motorcycle."""
        with Session(self._engine) as session:
            bike = session.query(Motorcycle).filter_by(slug=bike_slug).first()
            if not bike:
                return []
            pm_rows = (
                session.query(ProductMotorcycle.product_id)
                .filter_by(motorcycle_id=bike.id)
                .all()
            )
            product_ids = [r[0] for r in pm_rows]
            if not product_ids:
                return []
            products_in_db = (
                session.query(Product)
                .filter(Product.id.in_(product_ids))
                .all()
            )
            asins = [p.asin for p in products_in_db if p.asin]
            return [self._by_asin.get(a, {}) for a in asins if a in self._by_asin]

    def get_compatible_bikes_for_product(self, product_slug: str) -> List[dict]:
        """Return compatible motorcycles for a product (used on product pages)."""
        product = self._by_slug.get(product_slug)
        if not product:
            return []
        asin = product.get("asin", "")
        if not asin:
            return []
        product_row = self._fetch_product_by_asin(asin)
        if not product_row:
            return []
        bikes = self._compat.get_compatible_bikes_for_product(product_row.id)
        return [
            {
                "id": b["id"],
                "make": b["make"],
                "model": b["model"],
                "slug": b["slug"],
                "year_start": b.get("year_start"),
                "year_end": b.get("year_end"),
                "type": b.get("type"),
            }
            for b in bikes
        ]

    def get_motorcycle_products_grouped(
        self, bike_slug: str,
    ) -> Dict[str, List[dict]]:
        """Return products compatible with a motorcycle grouped by AccessoryType."""
        with Session(self._engine) as session:
            bike = session.query(Motorcycle).filter_by(slug=bike_slug).first()
            if not bike:
                return {}
            return self._compat.get_products_for_motorcycle_grouped(bike.id)

    def get_products_by_accessory_type_for_motorcycle(
        self,
        bike_slug: str,
        accessory_type_slug: str,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[List[dict], int]:
        """Return products for a motorcycle filtered by AccessoryType slug."""
        with Session(self._engine) as session:
            bike = session.query(Motorcycle).filter_by(slug=bike_slug).first()
            if not bike:
                return [], 0
            return self._compat.get_products_for_motorcycle_by_accessory_type(
                bike.id, accessory_type_slug, offset, limit
            )

    def _fetch_product_by_asin(self, asin: str) -> Optional[Product]:
        with Session(self._engine) as session:
            return (
                session.query(Product)
                .options(
                    joinedload(Product.brand),
                    joinedload(Product.accessory_type),
                    joinedload(Product.categories),
                    joinedload(Product.images),
                )
                .filter(Product.asin == asin)
                .first()
            )

    def get_budget_products(self, max_price: float = 2000) -> List[dict]:
        return [p for p in self._products if (p.get("price") or 0) <= max_price]

    def get_premium_products(self, min_price: float = 5000) -> List[dict]:
        return [p for p in self._products if (p.get("price") or 0) >= min_price]

    def get_price_drop_count(self, days: int = 7) -> int:
        """Count of products whose price dropped in the last N days."""
        from datetime import datetime, timedelta
        from db.models import PriceHistory
        with Session(self._engine) as session:
            week_ago = datetime.now() - timedelta(days=days)
            rows = (
                session.query(PriceHistory.product_id)
                .filter(PriceHistory.timestamp >= week_ago)
                .filter(PriceHistory.old_price.isnot(None))
                .filter(PriceHistory.price < PriceHistory.old_price)
                .distinct()
                .count()
            )
            return rows

    def get_missing_image_count(self) -> int:
        """Number of products with no image rows in the images table."""
        from db.models import Image, Product
        with Session(self._engine) as session:
            total = session.query(Product).count()
            with_images = session.query(Image.product_id).distinct().count()
            return total - with_images

    def get_total_in_db(self) -> int:
        """Total product rows in the database."""
        from db.models import Product
        with Session(self._engine) as session:
            return session.query(Product).count()

    def get_all(self) -> List[dict]:
        return list(self._products)

    def get_by_asin(self, asin: str) -> Optional[dict]:
        return self._by_asin.get(asin)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_from_db(self) -> List[dict]:
        with Session(self._engine) as session:
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
                .order_by(Product.id)
                .all()
            )
            return [self._model_to_flat(p) for p in products]

    def _model_to_flat(self, product: Product) -> dict:
        """Convert a SQLAlchemy Product model to a flat dict."""
        asin = product.asin or ""
        slug = product.slug or ""
        title = product.title or ""

        brand_name = product.brand.name if product.brand else ""

        cat_names = [c.name for c in product.categories]
        category = cat_names[0] if cat_names else ""
        ptype = cat_names[1] if len(cat_names) > 1 else ""

        ed = product.editorial_score
        if ed:
            pros = ed.pros or []
            cons = ed.cons or []
            features = ed.features or []
            recommended_for = ed.recommended_for or []
            editorial_notes = ed.editorial_notes or ""
            editors_choice = bool(ed.editors_choice)
            override_rank = ed.override_rank or 0
            picks = ed.picks or {}
            best_for = picks.get("best_for", "")
            verdict = picks.get("verdict", "")
            fitment_notes = picks.get("fitment_notes", "")
            editor_score = ed.editor_score or 0
        else:
            pros = cons = features = []
            recommended_for = []
            editorial_notes = ""
            editors_choice = False
            override_rank = 0
            best_for = verdict = fitment_notes = ""
            editor_score = 0

        image_url = ""
        for img in product.images:
            if img.is_primary or not image_url:
                image_url = img.url or ""

        last_updated_str = None
        if product.last_sync_at:
            last_updated_str = product.last_sync_at.isoformat()

        flat = {
            "asin": asin,
            "slug": slug,
            "title": title,
            "brand": brand_name,
            "category": category,
            "type": ptype,
            "status": _REVERSE_STATUS.get(product.status, "approved"),
            "compatible_bikes": product.compatible_bikes or ([m.slug for m in product.motorcycles] if product.motorcycles else []),
            "universal": bool(product.universal),
            "best_for": best_for,
            "verdict": verdict,
            "editor_rating": _maybe_int(editor_score),
            "editorial_verdict": product.editorial_verdict or "",
            "pros": pros,
            "cons": cons,
            "features": features,
            "fitment_notes": fitment_notes,
            "recommended_for": recommended_for,
            "editorial_notes": editorial_notes,
            "editors_choice": editors_choice,
            "override_rank": override_rank,
            "price": _maybe_int(product.price),
            "mrp": _maybe_int(product.mrp),
            "discount": _maybe_int(_calc_discount(product.price, product.mrp)),
            "rating": _maybe_int(product.rating) or 0,
            "review_count": product.review_count or 0,
            "reviews": product.review_count or 0,
            "availability": product.availability or "",
            "affiliate_url": product.url or "",
            "image": image_url,
            "amazon_image_url": image_url,
            "last_updated": last_updated_str,
            "pricing": _build_pricing(
                current=_maybe_int(product.price),
                mrp=_maybe_int(product.mrp),
                discount_percent=_maybe_int(_calc_discount(product.price, product.mrp)),
                last_updated=product.last_sync_at,
            ),
        }
        return flat

    def _normalize_categories(self, products: List[dict]):
        """Call product_library's normalize_product_category on every product."""
        from product_library import normalize_product_category
        for p in products:
            normalize_product_category(p)

    def _apply_quality_pipeline(self, products: List[dict]):
        """Replicate product_library.run_quality_pipeline inline."""
        from product_library import run_quality_pipeline
        products, dashboard = run_quality_pipeline(products)
        self._quality_dashboard = dashboard

    def _regenerate_slugs(self, products: List[dict]):
        """Replicate product_library.regenerate_all_slugs inline."""
        from product_library import regenerate_all_slugs
        regenerate_all_slugs(products)

    def _index_products(self, products: List[dict]):
        self._by_asin = {}
        self._by_slug = {}
        self._by_category = {}
        for p in products:
            asin = p.get("asin", "")
            slug = p.get("slug", "")
            cat = p.get("category", "")
            if asin:
                self._by_asin[asin] = p
            if slug:
                self._by_slug[slug] = p
            if cat:
                self._by_category.setdefault(cat, []).append(p)
