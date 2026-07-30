"""
GeneratorEngine — fully data-driven page data provider.

Reads from MotorcycleKnowledgeGraphService, SmartCollectionService,
and ProductService. Never hardcodes sections, categories, or content.

Every method returns flat dicts — never SQLAlchemy models.
The engine works for any future niche without code changes.
"""

import os
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.knowledge_graph_service import (
    MotorcycleKnowledgeGraphService,
    _motorcycle_to_dict,
    _upgrade_section_to_dict,
)
from db.models import Motorcycle, Product, UpgradeSection
from db.motorcycle_repository import MotorcycleKnowledgeRepository
from db.smart_collections import SmartCollectionService

DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")


def _product_to_dict(p) -> dict:
    return {
        "id": p.id,
        "asin": p.asin,
        "slug": p.slug or "",
        "title": p.title,
        "brand": p.brand.name if p.brand else "",
        "price": p.price,
        "mrp": p.mrp,
        "rating": p.rating,
        "review_count": p.review_count,
        "category": (p.categories[0].name if p.categories else ""),
        "image": "",
        "affiliate_url": p.url or "",
        "verdict": "",
    }


class GeneratorEngine:
    """Fully data-driven page data provider.

    Usage::

        engine = GeneratorEngine()
        bike = engine.get_motorcycle("honda-cb350")
        sections = engine.build_page_sections(bike)
    """

    def __init__(self, db_url: Optional[str] = None):
        self._db_url = db_url or DB_URL
        self._engine = create_engine(self._db_url, echo=False)
        self._kg = MotorcycleKnowledgeGraphService(self._db_url)
        self._collections = SmartCollectionService(self._db_url)

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _session(self):
        return Session(self._engine)

    def _kg_repo(self, session: Session) -> MotorcycleKnowledgeRepository:
        return MotorcycleKnowledgeRepository(session)

    def _product_dict(self, product) -> dict:
        return _product_to_dict(product)

    def _get_products_by_ids(self, session: Session, ids: List[int]) -> List[dict]:
        if not ids:
            return []
        products = (
            session.query(Product)
            .filter(Product.id.in_(ids))
            .all()
        )
        return [self._product_dict(p) for p in products]

    def _get_section_products(
        self, session: Session, section_id: int
    ) -> List[dict]:
        section = (
            session.query(UpgradeSection)
            .filter(UpgradeSection.id == section_id)
            .first()
        )
        if not section or not section.products:
            return []
        return [self._product_dict(p) for p in section.products]

    # ==================================================================
    # Motorcycle page data
    # ==================================================================

    def get_all_motorcycles(self) -> List[dict]:
        """Return all motorcycles (lightweight, no relationships loaded)."""
        return self._kg.search_motorcycles()

    def get_motorcycle(self, slug: str) -> Optional[dict]:
        """Return a single motorcycle with all relationships (include_full)."""
        return self._kg.get_motorcycle_by_slug(slug, include_full=True)

    def build_page_sections(
        self, bike: dict, max_products_per_section: int = 6
    ) -> List[dict]:
        """Build dynamic page sections from UpgradeSection on the motorcycle.

        Each section maps to an UpgradeSection. Serves as the "Must Have"
        / "Accessories" dynamic grid on motorcycle pages.
        """
        sections = []
        with self._session() as session:
            for us in bike.get("upgrade_sections", []):
                products = self._get_section_products(session, us["id"])
                sections.append(
                    {
                        "id": us["slug"],
                        "title": us["name"],
                        "description": us.get("description", ""),
                        "icon": us.get("icon", ""),
                        "products": products[:max_products_per_section],
                        "total_products": len(products),
                    }
                )
        return sections

    def build_comparison_table(
        self, motorcycle_ids: List[int]
    ) -> List[dict]:
        """Build a comparison table for multiple motorcycles.

        Returns a list of dicts, one per motorcycle, with normalized spec
        fields. Works for any set of motorcycles — no hardcoded fields.
        """
        if not motorcycle_ids:
            return []
        with self._session() as session:
            repo = self._kg_repo(session)
            results = []
            for mid in motorcycle_ids:
                bike = repo.get(mid)
                if not bike:
                    continue
                results.append(
                    {
                        "id": bike.id,
                        "make": bike.make,
                        "model": bike.model,
                        "slug": bike.slug,
                        "hero_image": bike.hero_image or "",
                        "category": bike.category or "",
                        "type": bike.type or "",
                        "engine_cc": bike.engine_cc,
                        "year_start": bike.year_start,
                        "year_end": bike.year_end,
                        "description": bike.description or "",
                    }
                )
            return results

    def build_breadcrumbs(
        self, page_type: str, **kwargs
    ) -> List[Dict[str, str]]:
        """Build breadcrumbs for any page type.

        Supported page_type values: 'motorcycle', 'motorcycles_index',
        'collection', 'collections_index', 'product', 'category'.

        Extra kwargs supply the slug/name for the current page.
        """
        home = {"name": "Home", "url": "./index.html"}
        crumbs = [home]

        if page_type == "motorcycles_index":
            crumbs.append({"name": "Motorcycles"})
        elif page_type == "motorcycle":
            brand = kwargs.get("brand", "")
            model = kwargs.get("model", "")
            slug = kwargs.get("slug", "")
            crumbs.append(
                {
                    "name": "Motorcycles",
                    "url": f"../motorcycles/index.html",
                }
            )
            crumbs.append({"name": f"{brand} {model}" if brand else model or slug})
        elif page_type == "collections_index":
            crumbs.append({"name": "Collections"})
        elif page_type == "collection":
            name = kwargs.get("name", "")
            crumbs.append(
                {
                    "name": "Collections",
                    "url": f"../collections/index.html",
                }
            )
            crumbs.append({"name": name})
        elif page_type == "category":
            name = kwargs.get("name", "")
            crumbs.append(
                {"name": "Products", "url": f"../categories/index.html"}
            )
            crumbs.append({"name": name})

        return crumbs

    # ==================================================================
    # Collection page data
    # ==================================================================

    def get_all_collections(self) -> List[dict]:
        """Return all visible collections from SmartCollectionService."""
        return self._collections.get_visible_collections()

    def get_featured_collections(self) -> List[dict]:
        return self._collections.get_featured_collections()

    def get_motorcycle_collections(
        self, motorcycle_id: int
    ) -> List[dict]:
        """Return collections that a motorcycle belongs to (from KG)."""
        bike = self._kg.get_motorcycle(motorcycle_id, include_full=False)
        if not bike:
            return []
        ids = bike.get("collection_ids", [])
        all_cols = self.get_all_collections()
        return [c for c in all_cols if c.get("id") in ids]

    # ==================================================================
    # Related entity data
    # ==================================================================

    def get_related_motorcycles(
        self, slug: str, max_count: int = 6
    ) -> List[dict]:
        """Return related motorcycles from KG."""
        bike = self.get_motorcycle(slug)
        if not bike:
            return []
        return bike.get("related_motorcycles", [])[:max_count]

    def get_recommended_products(
        self, slug: str, max_count: int = 12
    ) -> List[dict]:
        """Return recommended products for a motorcycle from KG."""
        bike = self.get_motorcycle(slug)
        if not bike:
            return []
        with self._session() as session:
            pids = bike.get("recommended_product_ids", [])
            return self._get_products_by_ids(session, pids)[:max_count]

    # ==================================================================
    # Editorial / FAQ data
    # ==================================================================

    def get_faqs(self, slug: str) -> List[dict]:
        """Return FAQs for a motorcycle from KG."""
        bike = self.get_motorcycle(slug)
        if not bike:
            return []
        return bike.get("faqs", [])

    def get_tags(self, slug: str) -> List[str]:
        """Return tags for a motorcycle from KG."""
        bike = self.get_motorcycle(slug)
        if not bike:
            return []
        return bike.get("tags", [])

    # ==================================================================
    # Index / listing data
    # ==================================================================

    def build_motorcycle_index_data(self) -> dict:
        """Build context dict for the motorcycles listing page.

        Returns grouped motorcycles, brand counts, type counts.
        """
        all_bikes = self.get_all_motorcycles()
        brands = {}
        types = {}
        for b in all_bikes:
            make = b.get("make", "Other")
            brands.setdefault(make, []).append(b)
            bt = b.get("type", "Unknown")
            types[bt] = types.get(bt, 0) + 1

        return {
            "motorcycles": all_bikes,
            "brands_grouped": dict(sorted(brands.items())),
            "type_counts": dict(sorted(types.items())),
            "total_count": len(all_bikes),
        }

    # ==================================================================
    # Seed test data (for tests and development)
    # ==================================================================

    def seed_motorcycle(
        self,
        make: str,
        model: str,
        slug: str,
        category: str = "Standard",
        engine_cc: int = 350,
        bike_type: str = "Naked",
        tags: Optional[List[str]] = None,
        faqs: Optional[List[dict]] = None,
    ) -> dict:
        """Create a test motorcycle with optional tags and FAQs."""
        data = {
            "make": make,
            "model": model,
            "slug": slug,
            "category": category,
            "engine_cc": engine_cc,
            "type": bike_type,
        }
        if tags:
            data["tags"] = tags
        if faqs:
            data["faqs"] = faqs
        return self._kg.create_motorcycle(data)

    def seed_upgrade_sections(self) -> List[dict]:
        """Seed default upgrade sections (Protection, Style, etc.)."""
        return self._kg.seed_upgrade_sections()

    def add_motorcycle_to_section(
        self, motorcycle_id: int, section_ids: List[int]
    ) -> Optional[dict]:
        return self._kg.set_motorcycle_upgrade_sections(
            motorcycle_id, section_ids
        )

    def add_recommended_product(
        self, motorcycle_id: int, product_id: int
    ) -> Optional[dict]:
        return self._kg.add_recommended_product(motorcycle_id, product_id)
