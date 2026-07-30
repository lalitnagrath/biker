"""
CollectionRepository — full CRUD for collections, product membership,
related collections, and rule evaluation engine.

Follows the same pattern as ProductRepository in db/repository.py.
"""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from db.models import (
    Collection, CollectionItem, CollectionRelation, Product,
    ProductCategory, ProductTag,
)


def _evaluate_condition(condition: dict, product: Product) -> bool:
    """Evaluate a single condition against a Product model."""
    field = condition.get("field", "")
    op = condition.get("op", "==")
    value = condition.get("value")

    # Resolve field value from product
    field_map = {
        "score": product.score,
        "price": product.price,
        "mrp": product.mrp,
        "rating": product.rating,
        "review_count": product.review_count,
        "status": product.status,
        "brand": product.brand.name if product.brand else "",
    }
    if field == "category":
        field_val = [c.name for c in product.categories] if product.categories else []
    elif field == "tag":
        field_val = [t.tag for t in product.tags] if product.tags else []
    else:
        field_val = field_map.get(field)

    if op in ("==", "!="):
        fv = field_val
        if isinstance(fv, list):
            return (value in fv) if op == "==" else (value not in fv)
        if fv is None:
            return False
        try:
            return (str(fv).lower() == str(value).lower()) if op == "==" else (str(fv).lower() != str(value).lower())
        except (ValueError, TypeError):
            return False

    if op in (">", ">=", "<", "<="):
        if field_val is None:
            return False
        try:
            fv = float(field_val)
            cv = float(value)
        except (ValueError, TypeError):
            return False
        if op == ">":
            return fv > cv
        if op == ">=":
            return fv >= cv
        if op == "<":
            return fv < cv
        if op == "<=":
            return fv <= cv

    if op == "in":
        if isinstance(field_val, list):
            return any(v in field_val for v in (value if isinstance(value, list) else [value]))
        return field_val in (value if isinstance(value, list) else [value])

    if op == "not_in":
        if isinstance(field_val, list):
            return not any(v in field_val for v in (value if isinstance(value, list) else [value]))
        return field_val not in (value if isinstance(value, list) else [value])

    if op == "contains":
        if field_val is None:
            return False
        return str(value).lower() in str(field_val).lower()

    return False


class CollectionRepository:

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_collection(self, collection_id: int) -> Optional[Collection]:
        return (
            self.session.query(Collection)
            .options(
                joinedload(Collection.items).joinedload(CollectionItem.product).joinedload(Product.images),
                joinedload(Collection.related),
            )
            .filter(Collection.id == collection_id)
            .first()
        )

    def get_by_slug(self, slug: str) -> Optional[Collection]:
        return (
            self.session.query(Collection)
            .options(
                joinedload(Collection.items).joinedload(CollectionItem.product).joinedload(Product.images),
                joinedload(Collection.related),
            )
            .filter(Collection.slug == slug)
            .first()
        )

    def search_collections(
        self,
        *,
        query: str = "",
        niche: Optional[str] = None,
        is_visible: Optional[bool] = None,
        is_featured: Optional[bool] = None,
        rule_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "sort_order",
        descending: bool = False,
    ) -> Tuple[List[Collection], int]:
        q = self.session.query(Collection)

        if query:
            like = f"%{query}%"
            q = q.filter(
                or_(
                    Collection.name.ilike(like),
                    Collection.description.ilike(like),
                )
            )
        if niche is not None:
            q = q.filter(Collection.niche == niche)
        if is_visible is not None:
            q = q.filter(Collection.is_visible == is_visible)
        if is_featured is not None:
            q = q.filter(Collection.is_featured == is_featured)
        if rule_type is not None:
            q = q.filter(Collection.rule_type == rule_type)

        total = q.count()
        col = getattr(Collection, order_by, Collection.sort_order)
        direction = col.desc() if descending else col.asc()
        results = (
            q.options(
                joinedload(Collection.items),
                joinedload(Collection.related),
            )
            .order_by(direction)
            .offset(offset)
            .limit(limit)
            .all()
        )
        return results, total

    def get_visible_collections(self) -> List[Collection]:
        return (
            self.session.query(Collection)
            .options(
                joinedload(Collection.items).joinedload(CollectionItem.product).joinedload(Product.images),
                joinedload(Collection.related),
            )
            .filter(Collection.is_visible == True)
            .order_by(Collection.sort_order)
            .all()
        )

    def get_featured_collections(self) -> List[Collection]:
        return (
            self.session.query(Collection)
            .options(
                joinedload(Collection.items).joinedload(CollectionItem.product).joinedload(Product.images),
                joinedload(Collection.related),
            )
            .filter(Collection.is_featured == True)
            .filter(Collection.is_visible == True)
            .order_by(Collection.sort_order)
            .all()
        )

    def get_rule_collections(self) -> List[Collection]:
        return (
            self.session.query(Collection)
            .options(
                joinedload(Collection.items),
            )
            .filter(Collection.rule_type == "rule")
            .all()
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_collection(self, data: Dict[str, Any]) -> Collection:
        from datetime import datetime
        slug = data.get("slug", "")
        if not slug:
            from slugify import slugify
            slug = slugify(data.get("name", ""))
        c = Collection(
            name=data.get("name", ""),
            slug=slug,
            niche=data.get("niche"),
            description=data.get("description"),
            hero_image=data.get("hero_image"),
            seo_title=data.get("seo_title"),
            seo_description=data.get("seo_description"),
            is_visible=data.get("is_visible", True),
            is_featured=data.get("is_featured", False),
            rule_type=data.get("rule_type", "manual"),
            rule_definition=data.get("rule_definition"),
            sort_order=data.get("sort_order", 0),
        )
        self.session.add(c)
        self.session.flush()
        return c

    def update_collection(
        self, collection_id: int, data: Dict[str, Any]
    ) -> Optional[Collection]:
        c = self.session.query(Collection).get(collection_id)
        if not c:
            return None
        scalar_fields = [
            "name", "slug", "niche", "description", "hero_image",
            "seo_title", "seo_description", "is_visible", "is_featured",
            "rule_type", "rule_definition", "sort_order",
        ]
        for field in scalar_fields:
            if field in data:
                setattr(c, field, data[field])
        return c

    def delete_collection(self, collection_id: int) -> bool:
        c = self.session.query(Collection).get(collection_id)
        if not c:
            return False
        self.session.delete(c)
        return True

    # ------------------------------------------------------------------
    # Product membership
    # ------------------------------------------------------------------

    def add_product(
        self,
        collection_id: int,
        product_id: int,
        *,
        sort_order: int = 0,
        badge: Optional[str] = None,
        notes: Optional[str] = None,
        is_featured: bool = False,
    ) -> CollectionItem:
        existing = (
            self.session.query(CollectionItem)
            .filter_by(collection_id=collection_id, product_id=product_id)
            .first()
        )
        if existing:
            existing.sort_order = sort_order
            existing.badge = badge
            existing.notes = notes
            existing.is_featured = is_featured
            return existing

        item = CollectionItem(
            collection_id=collection_id,
            product_id=product_id,
            sort_order=sort_order,
            badge=badge,
            notes=notes,
            is_featured=is_featured,
        )
        self.session.add(item)
        self.session.flush()
        return item

    def remove_product(self, collection_id: int, product_id: int) -> bool:
        item = (
            self.session.query(CollectionItem)
            .filter_by(collection_id=collection_id, product_id=product_id)
            .first()
        )
        if not item:
            return False
        self.session.delete(item)
        return True

    def set_product_order(
        self, collection_id: int, product_ids: List[int]
    ) -> bool:
        c = self.session.query(Collection).get(collection_id)
        if not c:
            return False
        for idx, pid in enumerate(product_ids):
            item = (
                self.session.query(CollectionItem)
                .filter_by(collection_id=collection_id, product_id=pid)
                .first()
            )
            if item:
                item.sort_order = idx
        return True

    def set_product_featured(
        self, collection_id: int, product_id: int, featured: bool
    ) -> bool:
        item = (
            self.session.query(CollectionItem)
            .filter_by(collection_id=collection_id, product_id=product_id)
            .first()
        )
        if not item:
            return False
        item.is_featured = featured
        return True

    # ------------------------------------------------------------------
    # Related collections
    # ------------------------------------------------------------------

    def add_related(self, collection_id: int, related_id: int) -> CollectionRelation:
        existing = (
            self.session.query(CollectionRelation)
            .filter_by(
                collection_id=collection_id,
                related_collection_id=related_id,
            )
            .first()
        )
        if existing:
            return existing
        rel = CollectionRelation(
            collection_id=collection_id,
            related_collection_id=related_id,
        )
        self.session.add(rel)
        self.session.flush()
        return rel

    def remove_related(self, collection_id: int, related_id: int) -> bool:
        rel = (
            self.session.query(CollectionRelation)
            .filter_by(
                collection_id=collection_id,
                related_collection_id=related_id,
            )
            .first()
        )
        if not rel:
            return False
        self.session.delete(rel)
        return True

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate_rule(rule: dict, product: Product) -> bool:
        """Evaluate a product against a rule definition.

        Rule format:
            {
                "conditions": [
                    {"field": "score", "op": ">=", "value": 85},
                    {"field": "category", "op": "==", "value": "Helmet"},
                ],
                "logic": "and",       # "and" | "or"
            }
        """
        conditions = rule.get("conditions", [])
        logic = rule.get("logic", "and")

        if not conditions:
            return True

        results = [_evaluate_condition(c, product) for c in conditions]

        if logic == "or":
            return any(results)
        return all(results)
