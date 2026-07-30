"""
MotorcycleKnowledgeRepository — full CRUD for the Motorcycle Knowledge Graph.

Manages motorcycles as first-class entities with:
  - Tags, FAQs, upgrade sections, recommended products, collections,
    related motorcycles
  - CRUD for all relationships
"""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from db.models import (
    Collection, Motorcycle, MotorcycleCollection, MotorcycleFAQ,
    MotorcycleRecommendedProduct, MotorcycleRelation, MotorcycleTag,
    Product, ProductUpgradeSection, UpgradeSection,
    MotorcycleUpgradeSection,
)


class MotorcycleKnowledgeRepository:

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Motorcycle CRUD
    # ------------------------------------------------------------------

    def _default_load(self, query):
        return query.options(
            joinedload(Motorcycle.tags),
            joinedload(Motorcycle.faqs),
            joinedload(Motorcycle.upgrade_sections),
            joinedload(Motorcycle.products),
            joinedload(Motorcycle.recommended_products),
            joinedload(Motorcycle.collections),
            joinedload(Motorcycle.related_motorcycles),
        )

    def get(self, motorcycle_id: int) -> Optional[Motorcycle]:
        return (
            self._default_load(
                self.session.query(Motorcycle)
            )
            .filter(Motorcycle.id == motorcycle_id)
            .first()
        )

    def get_by_slug(self, slug: str) -> Optional[Motorcycle]:
        return (
            self._default_load(
                self.session.query(Motorcycle)
            )
            .filter(Motorcycle.slug == slug)
            .first()
        )

    def search(
        self,
        *,
        query: str = "",
        make: Optional[str] = None,
        category: Optional[str] = None,
        bike_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "make",
        descending: bool = False,
    ) -> Tuple[List[Motorcycle], int]:
        q = self.session.query(Motorcycle)

        if query:
            like = f"%{query}%"
            q = q.filter(
                or_(
                    Motorcycle.make.ilike(like),
                    Motorcycle.model.ilike(like),
                    Motorcycle.description.ilike(like),
                )
            )
        if make is not None:
            q = q.filter(Motorcycle.make == make)
        if category is not None:
            q = q.filter(Motorcycle.category == category)
        if bike_type is not None:
            q = q.filter(Motorcycle.type == bike_type)

        total = q.count()
        col = getattr(Motorcycle, order_by, Motorcycle.make)
        direction = col.desc() if descending else col.asc()
        results = (
            q.options(joinedload(Motorcycle.tags))
            .order_by(direction)
            .offset(offset)
            .limit(limit)
            .all()
        )
        return results, total

    def create(self, data: Dict[str, Any]) -> Motorcycle:
        bike = Motorcycle(
            make=data.get("make", ""),
            model=data.get("model", ""),
            slug=data.get("slug", ""),
            year_start=data.get("year_start"),
            year_end=data.get("year_end"),
            category=data.get("category"),
            engine_cc=data.get("engine_cc"),
            type=data.get("type"),
            hero_image=data.get("hero_image"),
            description=data.get("description"),
        )
        self.session.add(bike)
        self.session.flush()
        return bike

    def update(
        self, motorcycle_id: int, data: Dict[str, Any]
    ) -> Optional[Motorcycle]:
        bike = self.session.query(Motorcycle).get(motorcycle_id)
        if not bike:
            return None
        scalar_fields = [
            "make", "model", "slug", "year_start", "year_end",
            "category", "engine_cc", "type", "hero_image", "description",
        ]
        for field in scalar_fields:
            if field in data:
                setattr(bike, field, data[field])
        return bike

    def delete(self, motorcycle_id: int) -> bool:
        bike = self.session.query(Motorcycle).get(motorcycle_id)
        if not bike:
            return False
        self.session.delete(bike)
        return True

    # ------------------------------------------------------------------
    # Tags
    # ------------------------------------------------------------------

    def set_tags(self, motorcycle_id: int, tags: List[str]) -> List[str]:
        self.session.query(MotorcycleTag).filter_by(
            motorcycle_id=motorcycle_id
        ).delete()
        created = []
        for tag in tags:
            mt = MotorcycleTag(motorcycle_id=motorcycle_id, tag=tag)
            self.session.add(mt)
            created.append(tag)
        return created

    def get_tags(self, motorcycle_id: int) -> List[str]:
        return [
            t.tag
            for t in self.session.query(MotorcycleTag)
            .filter_by(motorcycle_id=motorcycle_id)
            .all()
        ]

    # ------------------------------------------------------------------
    # FAQs
    # ------------------------------------------------------------------

    def set_faqs(
        self, motorcycle_id: int, faqs: List[Dict[str, Any]]
    ) -> List[MotorcycleFAQ]:
        self.session.query(MotorcycleFAQ).filter_by(
            motorcycle_id=motorcycle_id
        ).delete()
        created = []
        for idx, faq in enumerate(faqs):
            mf = MotorcycleFAQ(
                motorcycle_id=motorcycle_id,
                question=faq.get("question", ""),
                answer=faq.get("answer", ""),
                sort_order=idx,
            )
            self.session.add(mf)
            created.append(mf)
        return created

    def get_faqs(self, motorcycle_id: int) -> List[dict]:
        return [
            {"question": f.question, "answer": f.answer, "sort_order": f.sort_order}
            for f in self.session.query(MotorcycleFAQ)
            .filter_by(motorcycle_id=motorcycle_id)
            .order_by(MotorcycleFAQ.sort_order)
            .all()
        ]

    # ------------------------------------------------------------------
    # Upgrade Sections
    # ------------------------------------------------------------------

    def get_all_upgrade_sections(self) -> List[UpgradeSection]:
        return (
            self.session.query(UpgradeSection)
            .order_by(UpgradeSection.sort_order)
            .all()
        )

    def seed_upgrade_sections(self) -> List[UpgradeSection]:
        defaults = [
            {"name": "Protection", "slug": "protection",
             "description": "Crash guards, sliders, and protective gear",
             "icon": "shield", "sort_order": 1},
            {"name": "Style", "slug": "style",
             "description": "Jackets, gloves, decals, and aesthetic upgrades",
             "icon": "palette", "sort_order": 2},
            {"name": "Lighting", "slug": "lighting",
             "description": "Headlights, indicators, LED upgrades",
             "icon": "lightbulb", "sort_order": 3},
            {"name": "Touring", "slug": "touring",
             "description": "Luggage, GPS, comfort gear for long rides",
             "icon": "luggage", "sort_order": 4},
            {"name": "Comfort", "slug": "comfort",
             "description": "Seats, grips, backrests, windshields",
             "icon": "armchair", "sort_order": 5},
            {"name": "Maintenance", "slug": "maintenance",
             "description": "Oils, lubricants, cleaners, tools",
             "icon": "wrench", "sort_order": 6},
        ]
        created = []
        existing = {
            r.slug
            for r in self.session.query(UpgradeSection).all()
        }
        for d in defaults:
            if d["slug"] not in existing:
                us = UpgradeSection(**d)
                self.session.add(us)
                created.append(us)
        self.session.flush()
        return created

    def set_motorcycle_upgrade_sections(
        self, motorcycle_id: int, section_ids: List[int]
    ) -> List[int]:
        self.session.query(MotorcycleUpgradeSection).filter_by(
            motorcycle_id=motorcycle_id
        ).delete()
        for sid in section_ids:
            mus = MotorcycleUpgradeSection(
                motorcycle_id=motorcycle_id, upgrade_section_id=sid
            )
            self.session.add(mus)
        return section_ids

    # ------------------------------------------------------------------
    # Product Upgrade Sections
    # ------------------------------------------------------------------

    def set_product_upgrade_sections(
        self, product_id: int, section_ids: List[int]
    ) -> List[int]:
        self.session.query(ProductUpgradeSection).filter_by(
            product_id=product_id
        ).delete()
        for sid in section_ids:
            pus = ProductUpgradeSection(
                product_id=product_id, upgrade_section_id=sid
            )
            self.session.add(pus)
        return section_ids

    def get_products_by_upgrade_section(
        self, section_id: int
    ) -> List[Product]:
        return (
            self.session.query(Product)
            .join(ProductUpgradeSection)
            .filter(ProductUpgradeSection.upgrade_section_id == section_id)
            .all()
        )

    # ------------------------------------------------------------------
    # Recommended Products
    # ------------------------------------------------------------------

    def add_recommended_product(
        self, motorcycle_id: int, product_id: int
    ) -> bool:
        existing = (
            self.session.query(MotorcycleRecommendedProduct)
            .filter_by(
                motorcycle_id=motorcycle_id, product_id=product_id
            )
            .first()
        )
        if existing:
            return False
        mrp = MotorcycleRecommendedProduct(
            motorcycle_id=motorcycle_id, product_id=product_id
        )
        self.session.add(mrp)
        return True

    def remove_recommended_product(
        self, motorcycle_id: int, product_id: int
    ) -> bool:
        mrp = (
            self.session.query(MotorcycleRecommendedProduct)
            .filter_by(
                motorcycle_id=motorcycle_id, product_id=product_id
            )
            .first()
        )
        if not mrp:
            return False
        self.session.delete(mrp)
        return True

    def set_recommended_products(
        self, motorcycle_id: int, product_ids: List[int]
    ):
        self.session.query(MotorcycleRecommendedProduct).filter_by(
            motorcycle_id=motorcycle_id
        ).delete()
        for pid in product_ids:
            mrp = MotorcycleRecommendedProduct(
                motorcycle_id=motorcycle_id, product_id=pid
            )
            self.session.add(mrp)

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    def add_collection(
        self, motorcycle_id: int, collection_id: int
    ) -> bool:
        existing = (
            self.session.query(MotorcycleCollection)
            .filter_by(
                motorcycle_id=motorcycle_id, collection_id=collection_id
            )
            .first()
        )
        if existing:
            return False
        mc = MotorcycleCollection(
            motorcycle_id=motorcycle_id, collection_id=collection_id
        )
        self.session.add(mc)
        return True

    def remove_collection(
        self, motorcycle_id: int, collection_id: int
    ) -> bool:
        mc = (
            self.session.query(MotorcycleCollection)
            .filter_by(
                motorcycle_id=motorcycle_id, collection_id=collection_id
            )
            .first()
        )
        if not mc:
            return False
        self.session.delete(mc)
        return True

    def set_collections(
        self, motorcycle_id: int, collection_ids: List[int]
    ):
        self.session.query(MotorcycleCollection).filter_by(
            motorcycle_id=motorcycle_id
        ).delete()
        for cid in collection_ids:
            mc = MotorcycleCollection(
                motorcycle_id=motorcycle_id, collection_id=cid
            )
            self.session.add(mc)

    # ------------------------------------------------------------------
    # Related Motorcycles
    # ------------------------------------------------------------------

    def add_related(
        self, motorcycle_id: int, related_id: int
    ) -> bool:
        if motorcycle_id == related_id:
            return False
        existing = (
            self.session.query(MotorcycleRelation)
            .filter_by(
                motorcycle_id=motorcycle_id,
                related_motorcycle_id=related_id,
            )
            .first()
        )
        if existing:
            return False
        mr = MotorcycleRelation(
            motorcycle_id=motorcycle_id, related_motorcycle_id=related_id
        )
        self.session.add(mr)
        return True

    def remove_related(
        self, motorcycle_id: int, related_id: int
    ) -> bool:
        mr = (
            self.session.query(MotorcycleRelation)
            .filter_by(
                motorcycle_id=motorcycle_id,
                related_motorcycle_id=related_id,
            )
            .first()
        )
        if not mr:
            return False
        self.session.delete(mr)
        return True
