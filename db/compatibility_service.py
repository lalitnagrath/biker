from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from db.models import (
    AccessoryType, Motorcycle, Product, ProductMotorcycle,
)


class CompatibilityService:
    """Centralized compatibility queries for motorcycles and products.

    Reuses the existing ProductMotorcycle junction table and the
    AccessoryType / Product relationship.  No duplicate logic.
    """

    def __init__(self, session: Session):
        self.session = session
        self._product_cache: Dict[int, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Product → compatible motorcycles
    # ------------------------------------------------------------------

    def get_compatible_motorcycles(
        self,
        product_id: int,
    ) -> List[Dict[str, Any]]:
        """Return the list of motorcycles compatible with a product.

        Uses a single joined query to avoid N+1 database queries.
        """
        rows = (
            self.session.query(ProductMotorcycle, Motorcycle)
            .join(Motorcycle, ProductMotorcycle.motorcycle_id == Motorcycle.id)
            .filter(ProductMotorcycle.product_id == product_id)
            .all()
        )
        return [
            {
                "id": m.id,
                "make": m.make,
                "model": m.model,
                "slug": m.slug or "",
                "confidence": pm.confidence or 0.0,
                "match_strategy": pm.match_strategy,
            }
            for pm, m in rows
        ]

    def get_compatible_motorcycle_ids(
        self,
        product_id: int,
    ) -> List[int]:
        """Return only motorcycle IDs for a product (lightweight query)."""
        return [
            pm.motorcycle_id
            for pm in self.session.query(ProductMotorcycle)
            .filter(ProductMotorcycle.product_id == product_id)
            .all()
        ]

    def get_compatible_bike_slugs(
        self,
        product_id: int,
    ) -> List[str]:
        """Return slugs for the compatible bikes of a product."""
        rows = (
            self.session.query(Motorcycle.slug)
            .join(ProductMotorcycle, Motorcycle.id == ProductMotorcycle.motorcycle_id)
            .filter(ProductMotorcycle.product_id == product_id)
            .all()
        )
        return [r[0] for r in rows if r[0]]

    # ------------------------------------------------------------------
    # Motorcycle → compatible products grouped by AccessoryType
    # ------------------------------------------------------------------

    def get_products_for_motorcycle_grouped(
        self,
        motorcycle_id: int,
        active_only: bool = True,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Return products compatible with the motorcycle grouped by AccessoryType.

        Groups by AccessoryType name (e.g. "Bar End Mirrors").
        Products with no AccessoryType go under the "" key.
        Results are cached to avoid repeated queries.
        """
        product_ids = [
            r[0]
            for r in self.session.query(ProductMotorcycle.product_id)
            .filter(ProductMotorcycle.motorcycle_id == motorcycle_id)
            .distinct()
            .all()
        ]
        if not product_ids:
            return {}

        q = (
            self.session.query(Product, AccessoryType)
            .outerjoin(
                AccessoryType, Product.accessory_type_id == AccessoryType.id
            )
            .filter(Product.id.in_(product_ids))
        )
        if active_only:
            q = q.filter(Product.status == "active")

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for product, atype in q.all():
            key = atype.name if atype else "Uncategorized"
            grouped.setdefault(key, []).append(self._product_to_dict(product))

        return grouped

    def get_products_for_motorcycle_grouped_paginated(
        self,
        motorcycle_id: int,
        group: str,
        offset: int = 0,
        limit: int = 20,
        active_only: bool = True,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Return a paginated slice of products for a motorcycle filtered by group."""
        product_ids = [
            r[0]
            for r in self.session.query(ProductMotorcycle.product_id)
            .filter(ProductMotorcycle.motorcycle_id == motorcycle_id)
            .distinct()
            .all()
        ]
        if not product_ids:
            return [], 0

        q = (
            self.session.query(Product)
            .outerjoin(
                AccessoryType, Product.accessory_type_id == AccessoryType.id
            )
            .filter(Product.id.in_(product_ids))
        )
        if active_only:
            q = q.filter(Product.status == "active")
        if group:
            q = q.filter(
                (AccessoryType.name == group)
                | (AccessoryType.id.is_(None) if group == "Uncategorized" else False)
            )

        total = q.count()
        products = (
            q.order_by(Product.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._product_to_dict(p) for p in products], total

    # ------------------------------------------------------------------
    # AccessoryType page — products compatible with a motorcycle
    # ------------------------------------------------------------------

    def get_products_for_motorcycle_by_accessory_type(
        self,
        motorcycle_id: int,
        accessory_type_slug: str,
        offset: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Return products for a motorcycle filtered by AccessoryType slug."""
        atype = (
            self.session.query(AccessoryType)
            .filter_by(slug=accessory_type_slug)
            .first()
        )
        if not atype:
            return [], 0

        product_ids = [
            r[0]
            for r in self.session.query(ProductMotorcycle.product_id)
            .filter(ProductMotorcycle.motorcycle_id == motorcycle_id)
            .distinct()
            .all()
        ]
        if not product_ids:
            return [], 0

        q = (
            self.session.query(Product)
            .filter(Product.accessory_type_id == atype.id)
            .filter(Product.id.in_(product_ids))
        )

        total = q.count()
        products = (
            q.order_by(Product.updated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [self._product_to_dict(p) for p in products], total

    # ------------------------------------------------------------------
    # Product-page compatible bikes
    # ------------------------------------------------------------------

    def get_compatible_bikes_for_product(
        self,
        product_id: int,
    ) -> List[Dict[str, Any]]:
        """Return compatible motorcycles for a product with slug and name."""
        rows = (
            self.session.query(Motorcycle)
            .join(ProductMotorcycle, Motorcycle.id == ProductMotorcycle.motorcycle_id)
            .filter(ProductMotorcycle.product_id == product_id)
            .all()
        )
        return [
            {
                "id": m.id,
                "make": m.make,
                "model": m.model,
                "slug": m.slug or "",
                "year_start": m.year_start,
                "year_end": m.year_end,
                "type": m.type,
            }
            for m in rows
        ]

    # ------------------------------------------------------------------
    # Product serialization (with caching)
    # ------------------------------------------------------------------

    def _product_to_dict(self, product: Product) -> Dict[str, Any]:
        """Serialize a product to a flat dict."""
        pid = product.id
        if pid in self._product_cache:
            return self._product_cache[pid]

        atype_name = product.accessory_type.name if product.accessory_type else ""
        atype_slug = product.accessory_type.slug if product.accessory_type else ""

        result: Dict[str, Any] = {
            "id": product.id,
            "asin": product.asin or "",
            "slug": product.slug or "",
            "title": product.title or "",
            "price": product.price,
            "mrp": product.mrp,
            "rating": product.rating or 0,
            "review_count": product.review_count or 0,
            "brand_name": product.brand.name if product.brand else "",
            "category": product.categories[0].name if product.categories else "",
            "accessory_type": atype_name,
            "accessory_type_slug": atype_slug,
            "image_url": "",
            "status": product.status,
        }
        for img in product.images:
            if img.is_primary or not result["image_url"]:
                result["image_url"] = img.url or ""

        self._product_cache[pid] = result
        return result

    def clear_cache(self):
        """Clear the in-memory product cache."""
        self._product_cache.clear()

    # ------------------------------------------------------------------
    # Aggregate counts
    # ------------------------------------------------------------------

    def get_product_counts_by_accessory_type(
        self,
        motorcycle_id: int,
    ) -> Dict[str, int]:
        """Return {accessory_type_name: count} for products compatible with the motorcycle."""
        product_ids = [
            r[0]
            for r in self.session.query(ProductMotorcycle.product_id)
            .filter(ProductMotorcycle.motorcycle_id == motorcycle_id)
            .distinct()
            .all()
        ]
        if not product_ids:
            return {}

        rows = (
            self.session.query(AccessoryType.name, Product.id)
            .outerjoin(Product, AccessoryType.id == Product.accessory_type_id)
            .filter(Product.id.in_(product_ids))
            .all()
        )
        counts: Dict[str, int] = {}
        for name, _ in rows:
            key = name or "Uncategorized"
            counts[key] = counts.get(key, 0) + 1
        return counts