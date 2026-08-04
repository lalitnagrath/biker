"""
Classification service: applies the heuristic ProductClassifier to the
products database.

Responsibilities:
  * ensure_taxonomy()  - create the 17 Upgrade Collections and 24 Accessory
                         Types (idempotent; reuses existing rows by slug).
  * classify_all()     - classify every imported Amazon product and persist:
                         accessory_type (category), upgrade_collections,
                         universal / compatible_bikes / compatibility_type
                         and classification_confidence.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from db.models import (
    AccessoryType,
    Motorcycle,
    Product,
    ProductMotorcycle,
    UpgradeCollection,
)
from db.product_classifier import (
    CATEGORIES,
    COLLECTIONS,
    ProductClassifier,
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(name: str) -> str:
    return _SLUG_RE.sub("-", (name or "").strip().lower()).strip("-")


class ClassificationService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Taxonomy setup
    # ------------------------------------------------------------------

    def ensure_taxonomy(self) -> Dict[str, int]:
        """Create the 24 accessory types + 17 upgrade collections if missing."""
        created_types = 0
        by_slug = {
            _slug(a.name): a
            for a in self.session.query(AccessoryType).all()
        }
        for name in CATEGORIES:
            slug = _slug(name)
            if slug not in by_slug:
                self.session.add(AccessoryType(name=name, slug=slug, is_active=True))
                by_slug[slug] = None  # mark as scheduled
                created_types += 1

        created_colls = 0
        coll_by_slug = {
            c.slug: c
            for c in self.session.query(UpgradeCollection).all()
        }
        for name in COLLECTIONS:
            slug = _slug(name)
            if slug not in coll_by_slug:
                self.session.add(UpgradeCollection(
                    name=name, slug=slug,
                    description=f"AI-classified {name} collection.",
                ))
                coll_by_slug[slug] = None
                created_colls += 1
        self.session.flush()

        return {"accessory_types_created": created_types,
                "collections_created": created_colls}

    def _load_taxonomy(self):
        return {
            "accessory_types": {
                _slug(a.name): a
                for a in self.session.query(AccessoryType).all()
            },
            "collections": {
                c.slug: c
                for c in self.session.query(UpgradeCollection).all()
            },
        }

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify_all(
        self,
        asins: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        bikes = [
            {"make": m.make or "", "model": m.model or "", "slug": m.slug or ""}
            for m in self.session.query(Motorcycle).all()
        ]
        classifier = ProductClassifier(bikes)
        taxonomy = self._load_taxonomy()

        query = (
            self.session.query(Product)
            .options(joinedload(Product.editorial_score))
            .filter(Product.asin.isnot(None))
            .filter(Product.asin != "")
        )
        if asins:
            query = query.filter(Product.asin.in_(asins))
        products = query.order_by(Product.id).all()

        records: List[Dict[str, Any]] = []
        for p in products:
            rec = self._classify_product(p, classifier, taxonomy)
            records.append(rec)

        if not dry_run:
            self._write_records(records)
            self.session.commit()

        return self._report(records)

    def _classify_product(
        self,
        p: Product,
        classifier: ProductClassifier,
        taxonomy: Dict[str, Any],
    ) -> Dict[str, Any]:
        bullets = []
        ed = p.editorial_score
        if ed and ed.features:
            if isinstance(ed.features, list):
                bullets = [str(f) for f in ed.features if str(f).strip()]

        result = classifier.classify(
            title=p.title,
            description=p.description,
            bullets=bullets,
        )
        category = result["category"]
        atypes = taxonomy["accessory_types"]
        colls = taxonomy["collections"]

        # Resolve collections against the DB (only known slugs are kept).
        collection_slugs = [_slug(c) for c in result["collections"]]
        coll_objs = [colls[s] for s in collection_slugs if s in colls]

        return {
            "asin": p.asin,
            "id": p.id,
            "title": p.title or "",
            "category": category,
            "accessory_type_id": atypes[_slug(category)].id if category and _slug(category) in atypes else None,
            "collections": [c.name for c in coll_objs],
            "collection_objs": coll_objs,
            "type": result["type"],
            "compatible_motorcycles": result["compatible_motorcycles"],
            "compatible_motorcycle_slugs": result.get("compatible_motorcycle_slugs", []),
            "confidence": result["confidence"],
        }

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def _write_records(self, records: List[Dict[str, Any]]) -> None:
        ids = [r["id"] for r in records if r["id"]]
        if ids:
            self.session.query(ProductMotorcycle).filter(
                ProductMotorcycle.product_id.in_(ids)
            ).delete(synchronize_session=False)

        for rec in records:
            p = self.session.get(Product, rec["id"])
            if p is None:
                continue
            p.accessory_type_id = rec["accessory_type_id"]
            p.upgrade_collections = list(rec["collection_objs"])
            if rec["type"] == "Universal":
                p.universal = True
                p.compatible_bikes = None
            elif rec["type"] == "Bike Specific":
                p.universal = False
                p.compatible_bikes = [
                    slug for slug in rec["compatible_motorcycle_slugs"]
                    if slug
                ]
                for slug in p.compatible_bikes:
                    bike = self.session.query(Motorcycle).filter_by(slug=slug).first()
                    if bike:
                        self.session.add(ProductMotorcycle(
                            product_id=p.id,
                            motorcycle_id=bike.id,
                            confidence=1.0,
                            match_strategy="product_classifier",
                        ))
            else:  # Unknown
                p.universal = False
                p.compatible_bikes = None
            p.compatibility_type = {
                "Universal": "universal",
                "Bike Specific": "specific",
                "Unknown": "unknown",
            }.get(rec["type"], "unknown")
            p.classification_confidence = rec["confidence"]

    def _resolve_bike_slugs(self, names: List[str]) -> List[str]:
        return []

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _report(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_category: Counter = Counter()
        by_type: Counter = Counter()
        by_confidence: Counter = Counter()
        by_collection: Counter = Counter()
        no_category: List[Dict[str, Any]] = []
        unknown: List[Dict[str, Any]] = []

        for r in records:
            cat = r["category"] or "(none)"
            by_category[cat] += 1
            by_type[r["type"]] += 1
            by_confidence[r["confidence"]] += 1
            for c in r["collections"]:
                by_collection[c] += 1
            if not r["category"]:
                no_category.append(r)
            if r["type"] == "Unknown":
                unknown.append(r)

        return {
            "total": len(records),
            "by_category": dict(by_category),
            "by_type": dict(by_type),
            "by_confidence": dict(by_confidence),
            "by_collection": dict(by_collection),
            "no_category": no_category,
            "unknown": unknown,
            "records": records,
        }
