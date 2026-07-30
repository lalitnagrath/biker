"""
MotorcycleKnowledgeGraphService — produces flat dicts for the
Motorcycle Knowledge Graph.

Follows the same Service -> Repository pattern as SmartCollectionService.
All public methods return flat dicts, never SQLAlchemy models.
"""

import os
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.motorcycle_repository import MotorcycleKnowledgeRepository
from db.models import (
    Collection, Motorcycle, Product, UpgradeSection,
)

DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")


def _motorcycle_to_dict(bike, *, include_full: bool = False) -> dict:
    result = {
        "id": bike.id,
        "make": bike.make,
        "model": bike.model,
        "slug": bike.slug or "",
        "year_start": bike.year_start,
        "year_end": bike.year_end,
        "category": bike.category or "",
        "engine_cc": bike.engine_cc,
        "type": bike.type or "",
        "hero_image": bike.hero_image or "",
        "description": bike.description or "",
        "tags": [t.tag for t in bike.tags] if (include_full and bike.tags) else [],
    }
    if include_full and bike.faqs:
        result["faqs"] = [
            {
                "question": f.question,
                "answer": f.answer,
                "sort_order": f.sort_order,
            }
            for f in bike.faqs
        ]
    else:
        result["faqs"] = []

    if include_full and bike.upgrade_sections:
        result["upgrade_sections"] = [
            {
                "id": s.id,
                "name": s.name,
                "slug": s.slug,
                "description": s.description or "",
                "icon": s.icon or "",
            }
            for s in bike.upgrade_sections
        ]
    else:
        result["upgrade_sections"] = []

    if include_full and bike.products:
        result["compatible_product_ids"] = [p.id for p in bike.products]
    else:
        result["compatible_product_ids"] = []

    if include_full and bike.recommended_products:
        result["recommended_product_ids"] = [
            p.id for p in bike.recommended_products
        ]
    else:
        result["recommended_product_ids"] = []

    if include_full and bike.collections:
        result["collection_ids"] = [c.id for c in bike.collections]
    else:
        result["collection_ids"] = []

    if include_full and bike.related_motorcycles:
        result["related_motorcycles"] = [
            {
                "id": r.id,
                "make": r.make,
                "model": r.model,
                "slug": r.slug,
                "hero_image": r.hero_image or "",
            }
            for r in bike.related_motorcycles
        ]
    else:
        result["related_motorcycles"] = []

    return result


def _upgrade_section_to_dict(section) -> dict:
    return {
        "id": section.id,
        "name": section.name,
        "slug": section.slug,
        "description": section.description or "",
        "icon": section.icon or "",
        "sort_order": section.sort_order,
    }


class MotorcycleKnowledgeGraphService:

    def __init__(self, db_url: Optional[str] = None):
        self._engine = create_engine(db_url or DB_URL, echo=False)

    def _repo(self, session: Session) -> MotorcycleKnowledgeRepository:
        return MotorcycleKnowledgeRepository(session)

    # ------------------------------------------------------------------
    # Motorcycle CRUD
    # ------------------------------------------------------------------

    def get_motorcycle(
        self, motorcycle_id: int, *, include_full: bool = True
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            bike = self._repo(session).get(motorcycle_id)
            if not bike:
                return None
            return _motorcycle_to_dict(bike, include_full=include_full)

    def get_motorcycle_by_slug(
        self, slug: str, *, include_full: bool = True
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            bike = self._repo(session).get_by_slug(slug)
            if not bike:
                return None
            return _motorcycle_to_dict(bike, include_full=include_full)

    def search_motorcycles(
        self,
        *,
        query: str = "",
        make: Optional[str] = None,
        category: Optional[str] = None,
        bike_type: Optional[str] = None,
    ) -> List[dict]:
        with Session(self._engine) as session:
            results, _ = self._repo(session).search(
                query=query,
                make=make,
                category=category,
                bike_type=bike_type,
                limit=10_000,
            )
            return [
                _motorcycle_to_dict(b, include_full=False) for b in results
            ]

    def create_motorcycle(self, data: Dict[str, Any]) -> dict:
        with Session(self._engine) as session:
            repo = self._repo(session)
            bike = repo.create(data)
            if data.get("tags"):
                repo.set_tags(bike.id, data["tags"])
            if data.get("faqs"):
                repo.set_faqs(bike.id, data["faqs"])
            session.commit()
            return _motorcycle_to_dict(
                repo.get(bike.id), include_full=True
            )

    def update_motorcycle(
        self, motorcycle_id: int, data: Dict[str, Any]
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            bike = repo.update(motorcycle_id, data)
            if not bike:
                return None
            if "tags" in data:
                repo.set_tags(motorcycle_id, data["tags"])
            if "faqs" in data:
                repo.set_faqs(motorcycle_id, data["faqs"])
            session.commit()
            return _motorcycle_to_dict(
                repo.get(motorcycle_id), include_full=True
            )

    def delete_motorcycle(self, motorcycle_id: int) -> bool:
        with Session(self._engine) as session:
            ok = self._repo(session).delete(motorcycle_id)
            session.commit()
            return ok

    # ------------------------------------------------------------------
    # Upgrade Sections
    # ------------------------------------------------------------------

    def seed_upgrade_sections(self) -> List[dict]:
        with Session(self._engine) as session:
            created = self._repo(session).seed_upgrade_sections()
            session.commit()
            return [
                _upgrade_section_to_dict(s) for s in created
            ]

    def get_all_upgrade_sections(self) -> List[dict]:
        with Session(self._engine) as session:
            return [
                _upgrade_section_to_dict(s)
                for s in self._repo(session).get_all_upgrade_sections()
            ]

    def set_motorcycle_upgrade_sections(
        self, motorcycle_id: int, section_ids: List[int]
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.set_motorcycle_upgrade_sections(motorcycle_id, section_ids)
            session.commit()
            bike = repo.get(motorcycle_id)
            return _motorcycle_to_dict(bike, include_full=True) if bike else None

    def set_product_upgrade_sections(
        self, product_id: int, section_ids: List[int]
    ) -> bool:
        with Session(self._engine) as session:
            self._repo(session).set_product_upgrade_sections(
                product_id, section_ids
            )
            session.commit()
            return True

    # ------------------------------------------------------------------
    # Recommended Products
    # ------------------------------------------------------------------

    def add_recommended_product(
        self, motorcycle_id: int, product_id: int
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.add_recommended_product(motorcycle_id, product_id)
            session.commit()
            bike = repo.get(motorcycle_id)
            return _motorcycle_to_dict(bike, include_full=True) if bike else None

    def remove_recommended_product(
        self, motorcycle_id: int, product_id: int
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.remove_recommended_product(motorcycle_id, product_id)
            session.commit()
            bike = repo.get(motorcycle_id)
            return _motorcycle_to_dict(bike, include_full=True) if bike else None

    def set_recommended_products(
        self, motorcycle_id: int, product_ids: List[int]
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.set_recommended_products(motorcycle_id, product_ids)
            session.commit()
            bike = repo.get(motorcycle_id)
            return _motorcycle_to_dict(bike, include_full=True) if bike else None

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    def add_collection(
        self, motorcycle_id: int, collection_id: int
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.add_collection(motorcycle_id, collection_id)
            session.commit()
            bike = repo.get(motorcycle_id)
            return _motorcycle_to_dict(bike, include_full=True) if bike else None

    def remove_collection(
        self, motorcycle_id: int, collection_id: int
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.remove_collection(motorcycle_id, collection_id)
            session.commit()
            bike = repo.get(motorcycle_id)
            return _motorcycle_to_dict(bike, include_full=True) if bike else None

    # ------------------------------------------------------------------
    # Related Motorcycles
    # ------------------------------------------------------------------

    def add_related(
        self, motorcycle_id: int, related_id: int
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.add_related(motorcycle_id, related_id)
            session.commit()
            bike = repo.get(motorcycle_id)
            return _motorcycle_to_dict(bike, include_full=True) if bike else None

    def remove_related(
        self, motorcycle_id: int, related_id: int
    ) -> Optional[dict]:
        with Session(self._engine) as session:
            repo = self._repo(session)
            repo.remove_related(motorcycle_id, related_id)
            session.commit()
            bike = repo.get(motorcycle_id)
            return _motorcycle_to_dict(bike, include_full=True) if bike else None
