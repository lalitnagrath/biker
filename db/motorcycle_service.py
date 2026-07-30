"""
MotorcycleService — read-only service for motorcycle data.

All methods return flat dicts, never SQLAlchemy model instances.
"""

import os
from typing import List, Optional

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session

from db.models import Motorcycle, ProductMotorcycle

DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")


class MotorcycleService:

    def __init__(self, db_url: Optional[str] = None):
        self._engine = create_engine(db_url or DB_URL, echo=False)

    def load_all(self) -> List[dict]:
        """Return all motorcycles with their product counts."""
        with Session(self._engine) as session:
            bikes = (
                session.query(Motorcycle)
                .order_by(Motorcycle.make, Motorcycle.model)
                .all()
            )
            counts = dict(
                session.query(
                    ProductMotorcycle.motorcycle_id,
                    func.count(ProductMotorcycle.product_id),
                )
                .group_by(ProductMotorcycle.motorcycle_id)
                .all()
            )
            return [
                {
                    "id": b.id,
                    "make": b.make,
                    "model": b.model,
                    "year": (
                        f"{b.year_start or ''}-{b.year_end or ''}"
                        if b.year_start or b.year_end
                        else ""
                    ),
                    "slug": b.slug or "",
                    "product_count": counts.get(b.id, 0),
                }
                for b in bikes
            ]
