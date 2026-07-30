"""
CollectionService — read-only service for collection/grouping data.

All methods return flat dicts, never SQLAlchemy model instances.
"""

import os
from typing import List, Optional

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session

from db.models import Collection, CollectionItem

DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")


class CollectionService:

    def __init__(self, db_url: Optional[str] = None):
        self._engine = create_engine(db_url or DB_URL, echo=False)

    def load_all(self) -> List[dict]:
        """Return all collections with item counts."""
        with Session(self._engine) as session:
            collections = (
                session.query(Collection)
                .order_by(Collection.name)
                .all()
            )
            counts = dict(
                session.query(
                    CollectionItem.collection_id,
                    func.count(CollectionItem.id),
                )
                .group_by(CollectionItem.collection_id)
                .all()
            )
            return [
                {
                    "id": c.id,
                    "name": c.name,
                    "slug": c.slug,
                    "description": c.description or "",
                    "item_count": counts.get(c.id, 0),
                    "is_visible": c.is_visible,
                }
                for c in collections
            ]
