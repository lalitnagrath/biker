"""
Seed the default Pimp My Ride Upgrade Collections.

Idempotent: collections are matched by slug. Missing ones are created and
existing ones are updated to the latest name/description/icon/order, so
re-running always converges to the canonical set below. Old collection slugs
that were renamed are migrated in place (product links are preserved).

Usage:
    cd biker
    python seed_upgrade_collections.py
    python seed_upgrade_collections.py --db "sqlite:///other.db"
"""

import argparse
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import UpgradeCollection

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

DB_URL_DEFAULT = os.getenv("DB_URL", "sqlite:///bikereview.db")

DEFAULT_COLLECTIONS = [
    {
        "name": "Bike Styling",
        "slug": "bike-styling",
        "description": "Transform the appearance of your motorcycle with stylish accessories and visual upgrades.",
        "icon": "🔥",
        "sort_order": 1,
        "enabled": True,
    },
    {
        "name": "Protection",
        "slug": "protection",
        "description": "Protect your motorcycle and rider.",
        "icon": "🛡",
        "sort_order": 2,
        "enabled": True,
    },
    {
        "name": "Lighting",
        "slug": "lighting",
        "description": "Improve visibility and styling.",
        "icon": "💡",
        "sort_order": 3,
        "enabled": True,
    },
    {
        "name": "Smart Rider",
        "slug": "smart-rider",
        "description": "Navigation, charging and smart gadgets.",
        "icon": "📱",
        "sort_order": 4,
        "enabled": True,
    },
    {
        "name": "Touring Gear",
        "slug": "touring-gear",
        "description": "Everything for long rides and luggage.",
        "icon": "🎒",
        "sort_order": 5,
        "enabled": True,
    },
    {
        "name": "Performance",
        "slug": "performance",
        "description": "Performance upgrades and better components.",
        "icon": "⚙️",
        "sort_order": 6,
        "enabled": True,
    },
    {
        "name": "Rider Comfort",
        "slug": "rider-comfort",
        "description": "Seats, grips and touring comfort.",
        "icon": "💺",
        "sort_order": 7,
        "enabled": True,
    },
    {
        "name": "Bike Care",
        "slug": "bike-care",
        "description": "Keep your motorcycle running smoothly.",
        "icon": "🧰",
        "sort_order": 8,
        "enabled": True,
    },
    {
        "name": "Security",
        "slug": "security",
        "description": "Prevent theft and improve safety.",
        "icon": "🔒",
        "sort_order": 9,
        "enabled": True,
    },
    {
        "name": "Detailing",
        "slug": "detailing",
        "description": "Cleaning and detailing products.",
        "icon": "🧼",
        "sort_order": 10,
        "enabled": True,
    },
]

# Old slugs that were renamed to a new slug in the canonical set above.
# Renaming in place keeps the DB row (and every product link) intact.
RENAME_SLUGS = {
    "styling": "bike-styling",
    "technology": "smart-rider",
    "touring": "touring-gear",
    "comfort": "rider-comfort",
    "maintenance": "bike-care",
    "cleaning": "detailing",
}


def seed(session: Session):
    """Create missing collections and update existing ones. Returns (created, existing)."""
    created = []
    existing = []

    target_slugs = {spec["slug"] for spec in DEFAULT_COLLECTIONS}

    for old_slug, new_slug in RENAME_SLUGS.items():
        if new_slug in target_slugs:
            coll = session.query(UpgradeCollection).filter_by(slug=old_slug).first()
            if coll is not None and session.query(UpgradeCollection).filter_by(slug=new_slug).first() is None:
                coll.slug = new_slug

    for spec in DEFAULT_COLLECTIONS:
        coll = session.query(UpgradeCollection).filter_by(slug=spec["slug"]).first()
        if coll is not None:
            coll.name = spec["name"]
            coll.description = spec["description"]
            coll.icon = spec["icon"]
            coll.sort_order = spec["sort_order"]
            coll.enabled = spec["enabled"]
            existing.append(coll)
            continue
        coll = UpgradeCollection(**spec)
        session.add(coll)
        created.append(coll)
    session.commit()
    return created, existing


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Seed default Pimp My Ride Upgrade Collections (idempotent).",
    )
    parser.add_argument("--db", default=None,
                        help="SQLAlchemy DB URL (default: %(default)s).")
    args = parser.parse_args(argv)

    eng = create_engine(args.db or DB_URL_DEFAULT, echo=False)
    with Session(eng) as session:
        created, existing = seed(session)

        for coll in created:
            print(f"  created  [{coll.sort_order}] {coll.name} ({coll.slug}) {coll.icon}")
        for coll in existing:
            print(f"  updated  [{coll.sort_order}] {coll.name} ({coll.slug}) {coll.icon}")

        print(f"\n  {len(created)} created, {len(existing)} already present (refreshed), "
              f"{len(DEFAULT_COLLECTIONS)} total.")
        return created


if __name__ == "__main__":
    main()
