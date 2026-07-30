"""
SmartCollectionService — manages collections with rule evaluation,
product membership, and metadata.

Layers on top of CollectionRepository.
All public methods return flat dicts.
"""

import os
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, joinedload

from db.collection_repository import CollectionRepository
from db.models import Collection, Product

DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")


def _collection_to_dict(
    collection,
    *,
    include_products: bool = True,
    include_related: bool = True,
) -> dict:
    result = {
        "id": collection.id,
        "name": collection.name,
        "slug": collection.slug,
        "niche": collection.niche or "",
        "description": collection.description or "",
        "hero_image": collection.hero_image or "",
        "seo_title": collection.seo_title or "",
        "seo_description": collection.seo_description or "",
        "is_visible": bool(collection.is_visible),
        "is_featured": bool(collection.is_featured),
        "rule_type": collection.rule_type or "manual",
        "rule_definition": collection.rule_definition,
        "sort_order": collection.sort_order or 0,
        "created_at": (
            collection.created_at.isoformat()
            if collection.created_at
            else ""
        ),
        "item_count": len(collection.items) if collection.items else 0,
        "products": [],
        "related": [],
        "featured_product_ids": [],
    }

    if include_products and collection.items:
        products = []
        featured_ids = []
        for item in collection.items:
            p = item.product
            if p:
                products.append(
                    {
                        "id": p.id,
                        "asin": p.asin,
                        "slug": p.slug,
                        "title": p.title,
                        "price": p.price,
                        "mrp": p.mrp,
                        "rating": p.rating,
                        "review_count": p.review_count,
                        "score": p.score,
                        "status": p.status,
                        "image_url": (
                            p.images[0].url
                            if p.images
                            else ""
                        ),
                        "badge": item.badge or "",
                        "notes": item.notes or "",
                        "sort_order": item.sort_order or 0,
                        "is_featured": bool(item.is_featured),
                    }
                )
                if item.is_featured:
                    featured_ids.append(p.id)
        result["products"] = products
        result["featured_product_ids"] = featured_ids

    if include_related and collection.related:
        result["related"] = [
            {
                "id": r.id,
                "name": r.name,
                "slug": r.slug,
                "description": r.description or "",
                "hero_image": r.hero_image or "",
                "item_count": len(r.items) if r.items else 0,
            }
            for r in collection.related
        ]

    return result


class SmartCollectionService:

    def __init__(self, db_url: Optional[str] = None):
        self._engine = create_engine(db_url or DB_URL, echo=False)

    def _repo(self, session: Session) -> CollectionRepository:
        return CollectionRepository(session)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_collections(
        self,
        *,
        query: str = "",
        niche: Optional[str] = None,
        is_visible: Optional[bool] = None,
        is_featured: Optional[bool] = None,
        rule_type: Optional[str] = None,
        include_products: bool = True,
        include_related: bool = True,
    ) -> List[dict]:
        with Session(self._engine) as session:
            results, _ = self._repo(session).search_collections(
                query=query,
                niche=niche,
                is_visible=is_visible,
                is_featured=is_featured,
                rule_type=rule_type,
                limit=10_000,
            )
            return [
                _collection_to_dict(
                    c,
                    include_products=include_products,
                    include_related=include_related,
                )
                for c in results
            ]

    def get_collection(
        self,
        collection_id: int,
        *,
        include_products: bool = True,
        include_related: bool = True,
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            c = self._repo(session).get_collection(collection_id)
            if not c:
                return None
            return _collection_to_dict(
                c,
                include_products=include_products,
                include_related=include_related,
            )

    def get_collection_by_slug(
        self,
        slug: str,
        *,
        include_products: bool = True,
        include_related: bool = True,
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            c = self._repo(session).get_by_slug(slug)
            if not c:
                return None
            return _collection_to_dict(
                c,
                include_products=include_products,
                include_related=include_related,
            )

    def get_visible_collections(self) -> List[dict]:
        with Session(self._engine) as session:
            return [
                _collection_to_dict(c)
                for c in self._repo(session).get_visible_collections()
            ]

    def get_featured_collections(self) -> List[dict]:
        with Session(self._engine) as session:
            return [
                _collection_to_dict(c)
                for c in self._repo(session).get_featured_collections()
            ]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_collection(self, data: Dict[str, Any]) -> dict:
        with Session(self._engine) as session:
            c = self._repo(session).create_collection(data)
            session.commit()
            return _collection_to_dict(
                self._repo(session).get_collection(c.id)
            )

    def update_collection(
        self, collection_id: int, data: Dict[str, Any]
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            c = self._repo(session).update_collection(collection_id, data)
            if not c:
                return None
            session.commit()
            return _collection_to_dict(
                self._repo(session).get_collection(collection_id)
            )

    def delete_collection(self, collection_id: int) -> bool:
        with Session(self._engine) as session:
            ok = self._repo(session).delete_collection(collection_id)
            session.commit()
            return ok

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
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.add_product(
                collection_id,
                product_id,
                sort_order=sort_order,
                badge=badge,
                notes=notes,
                is_featured=is_featured,
            )
            session.commit()
            c = repo.get_collection(collection_id)
            return _collection_to_dict(c) if c else None

    def remove_product(
        self, collection_id: int, product_id: int
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.remove_product(collection_id, product_id)
            session.commit()
            c = repo.get_collection(collection_id)
            return _collection_to_dict(c) if c else None

    def reorder_products(
        self, collection_id: int, product_ids: List[int]
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.set_product_order(collection_id, product_ids)
            session.commit()
            c = repo.get_collection(collection_id)
            return _collection_to_dict(c) if c else None

    def set_product_featured(
        self, collection_id: int, product_id: int, featured: bool
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            if not repo.set_product_featured(
                collection_id, product_id, featured
            ):
                return None
            session.commit()
            c = repo.get_collection(collection_id)
            return _collection_to_dict(c) if c else None

    # ------------------------------------------------------------------
    # Related collections
    # ------------------------------------------------------------------

    def add_related(
        self, collection_id: int, related_id: int
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.add_related(collection_id, related_id)
            session.commit()
            c = repo.get_collection(collection_id)
            return _collection_to_dict(c) if c else None

    def remove_related(
        self, collection_id: int, related_id: int
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.remove_related(collection_id, related_id)
            session.commit()
            c = repo.get_collection(collection_id)
            return _collection_to_dict(c) if c else None

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    def refresh_rule_collections(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {"collections": [], "total_added": 0}

        with Session(self._engine) as session:
            repo = self._repo(session)
            rule_collections = repo.get_rule_collections()
            products = (
                session.query(Product)
                .options(
                    joinedload(Product.brand),
                    joinedload(Product.categories),
                    joinedload(Product.tags),
                )
                .all()
            )

            for col in rule_collections:
                rule = col.rule_definition
                if not rule:
                    continue

                matched_ids = {
                    p.id
                    for p in products
                    if CollectionRepository.evaluate_rule(rule, p)
                }
                current_ids = {
                    item.product_id for item in col.items
                }

                to_add = matched_ids - current_ids
                to_remove = current_ids - matched_ids

                for pid in to_remove:
                    repo.remove_product(col.id, pid)

                for pid in to_add:
                    repo.add_product(col.id, pid)

                session.flush()

                col_info = {
                    "id": col.id,
                    "name": col.name,
                    "slug": col.slug,
                    "added": len(to_add),
                    "removed": len(to_remove),
                    "total": len(matched_ids),
                }
                summary["collections"].append(col_info)
                summary["total_added"] += len(to_add)

            session.commit()

        return summary

    def evaluate_product(
        self, product_id: int
    ) -> List[Dict[str, Any]]:
        results = []
        with Session(self._engine) as session:
            repo = self._repo(session)
            product = (
                session.query(Product)
                .options(
                    joinedload(Product.brand),
                    joinedload(Product.categories),
                    joinedload(Product.tags),
                )
                .filter(Product.id == product_id)
                .first()
            )
            if not product:
                return results

            for col in repo.get_rule_collections():
                rule = col.rule_definition
                if rule and CollectionRepository.evaluate_rule(
                    rule, product
                ):
                    results.append(
                        {
                            "id": col.id,
                            "name": col.name,
                            "slug": col.slug,
                        }
                    )
        return results

    # ------------------------------------------------------------------
    # Default rule collections
    # ------------------------------------------------------------------

    DEFAULT_RULE_COLLECTIONS = [
        {
            "name": "Premium Helmets",
            "slug": "premium-helmets",
            "description": (
                "Top-rated helmets with outstanding safety scores"
            ),
            "niche": "motorcycles",
            "rule_type": "rule",
            "rule_definition": {
                "conditions": [
                    {"field": "score", "op": ">=", "value": 85},
                    {"field": "category", "op": "==", "value": "Helmet"},
                ],
                "logic": "and",
            },
            "is_featured": True,
        },
        {
            "name": "Budget Friendly",
            "slug": "budget-friendly",
            "description": (
                "Great products under Rs. 2,000"
            ),
            "niche": "motorcycles",
            "rule_type": "rule",
            "rule_definition": {
                "conditions": [
                    {"field": "price", "op": "<=", "value": 2000},
                ],
                "logic": "and",
            },
            "is_featured": True,
        },
        {
            "name": "Top Rated",
            "slug": "top-rated",
            "description": "Products with the highest user ratings",
            "niche": "motorcycles",
            "rule_type": "rule",
            "rule_definition": {
                "conditions": [
                    {"field": "rating", "op": ">=", "value": 4.0},
                    {"field": "review_count", "op": ">=", "value": 100},
                ],
                "logic": "and",
            },
        },
        {
            "name": "Best Value Picks",
            "slug": "best-value-picks",
            "description": (
                "Editor-approved products with great price-to-quality ratio"
            ),
            "niche": "motorcycles",
            "rule_type": "rule",
            "rule_definition": {
                "conditions": [
                    {"field": "score", "op": ">=", "value": 75},
                    {"field": "price", "op": "<=", "value": 5000},
                ],
                "logic": "and",
            },
            "is_featured": True,
        },
        {
            "name": "Premium Riding Gear",
            "slug": "premium-riding-gear",
            "description": (
                "High-end jackets, gloves, and riding pants"
            ),
            "niche": "motorcycles",
            "rule_type": "rule",
            "rule_definition": {
                "conditions": [
                    {"field": "price", "op": ">=", "value": 5000},
                    {
                        "field": "category",
                        "op": "in",
                        "value": [
                            "Jackets",
                            "Gloves",
                            "Riding Pants",
                            "Helmet",
                        ],
                    },
                ],
                "logic": "and",
            },
        },
        {
            "name": "Touring Essentials",
            "slug": "touring-essentials",
            "description": "Must-have gear for long-distance rides",
            "niche": "motorcycles",
            "rule_type": "rule",
            "rule_definition": {
                "conditions": [
                    {
                        "field": "category",
                        "op": "in",
                        "value": [
                            "Saddle Bag",
                            "Tail Bag",
                            "Tank Bag",
                            "GPS Tracker",
                            "Tyre Inflator",
                        ],
                    },
                ],
                "logic": "and",
            },
        },
        {
            "name": "Safety First",
            "slug": "safety-first",
            "description": "Protection and security gear for peace of mind",
            "niche": "motorcycles",
            "rule_type": "rule",
            "rule_definition": {
                "conditions": [
                    {
                        "field": "category",
                        "op": "in",
                        "value": [
                            "Helmet",
                            "Disc Lock",
                            "Chain Lock",
                            "Alarm",
                            "GPS Tracker",
                            "Crash Guard",
                        ],
                    },
                ],
                "logic": "and",
            },
        },
    ]

    def seed_default_collections(self) -> List[dict]:
        created = []
        with Session(self._engine) as session:
            repo = self._repo(session)
            existing_slugs = {
                r.slug
                for r in session.query(Collection.slug).all()
            }
            for data in self.DEFAULT_RULE_COLLECTIONS:
                if data["slug"] not in existing_slugs:
                    c = repo.create_collection(data)
                    created.append(c)
            session.commit()

        if created:
            self.refresh_rule_collections()

        return [
            _collection_to_dict(c) for c in created
        ]
