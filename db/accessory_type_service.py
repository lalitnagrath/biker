from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from db.models import AccessoryType


class AccessoryTypeService:
    """Service for AccessoryType business logic operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_accessory_type(self, accessory_type_id: int) -> Optional[AccessoryType]:
        """Get an accessory type by its ID."""
        return self.session.query(AccessoryType).filter_by(id=accessory_type_id).first()

    def get_accessory_type_by_slug(self, slug: str) -> Optional[AccessoryType]:
        """Get an accessory type by its slug."""
        return self.session.query(AccessoryType).filter_by(slug=slug).first()

    def get_all_accessory_types(self, active_only: bool = True) -> List[AccessoryType]:
        """Get all accessory types."""
        query = self.session.query(AccessoryType)
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(AccessoryType.name).all()

    def create_accessory_type(self, data: dict) -> AccessoryType:
        """Create a new accessory type."""
        slug = self._generate_slug(data["name"])
        accessory_type = AccessoryType(
            name=data["name"],
            slug=slug,
            description=data.get("description"),
            icon=data.get("icon"),
            is_active=data.get("is_active", True)
        )
        self.session.add(accessory_type)
        self.session.commit()
        return accessory_type

    def update_accessory_type(self, accessory_type_id: int, data: dict) -> Optional[AccessoryType]:
        """Update an existing accessory type."""
        accessory_type = self.get_accessory_type(accessory_type_id)
        if not accessory_type:
            return None

        if "name" in data:
            accessory_type.name = data["name"]
            accessory_type.slug = self._generate_slug(data["name"])
        if "slug" in data:
            accessory_type.slug = data["slug"]
        if "description" in data:
            accessory_type.description = data["description"]
        if "icon" in data:
            accessory_type.icon = data["icon"]
        if "is_active" in data:
            accessory_type.is_active = data["is_active"]

        self.session.commit()
        return accessory_type

    def delete_accessory_type(self, accessory_type_id: int) -> bool:
        """Delete an accessory type by its ID."""
        accessory_type = self.get_accessory_type(accessory_type_id)
        if not accessory_type:
            return False

        self.session.delete(accessory_type)
        self.session.commit()
        return True

    def count_accessory_types(self) -> int:
        """Get the total count of accessory types."""
        return self.session.query(AccessoryType).count()

    def _generate_slug(self, name: str) -> str:
        """Generate a slug from the name."""
        return name.lower().replace(" ", "-").replace("_", "-").replace("/", "-").replace("&", "and")

    def get_active_accessory_types(self) -> List[AccessoryType]:
        """Get all active accessory types for UI dropdowns."""
        return self.session.query(AccessoryType).filter_by(is_active=True).order_by(AccessoryType.name).all()


# Seed data for accessory types
ACCESSORY_TYPES_DATA = [
    {"name": "Bar End Mirror", "slug": "bar-end-mirror", "description": "Handlebar bar end mirrors for better visibility"},
    {"name": "Visor", "slug": "visor", "description": "Helmet visor for wind and debris protection"},
    {"name": "Crash Guard", "slug": "crash-guard", "description": "Motorcycle crash guard for engine protection"},
    {"name": "Leg Guard", "slug": "leg-guard", "description": "Leg guards for protection from debris"},
    {"name": "Tank Pad", "slug": "tank-pad", "description": "Fuel tank pad for comfort and protection"},
    {"name": "Phone Mount", "slug": "phone-mount", "description": "Motorcycle phone mount for navigation"},
    {"name": "Seat Cover", "slug": "seat-cover", "description": "Motorcycle seat cover for comfort and style"},
    {"name": "Top Box", "slug": "top-box", "description": "Motorcycle top box for storage"},
    {"name": "Saddle Stay", "slug": "saddle-stay", "description": "Saddle stay reinforcement for rear frame"},
    {"name": "Lever Guard", "slug": "lever-guard", "description": "Handlebar lever guards for clutch/brake levers"},
    {"name": "Engine Guard", "slug": "engine-guard", "description": "Engine guard for protection in crashes"},
    {"name": "Mobile Holder", "slug": "mobile-holder", "description": "Mobile phone holder for motorcycle"},
]


def seed_accessory_types(session: Session) -> None:
    """Seed the database with default accessory types if none exist."""
    count = session.query(AccessoryType).count()
    if count == 0:
        for data in ACCESSORY_TYPES_DATA:
            accessory_type = AccessoryType(
                name=data["name"],
                slug=data["slug"],
                description=data["description"],
                icon=None,
                is_active=True
            )
            session.add(accessory_type)
        session.commit()
        print(f"✅ Seeded {len(ACCESSORY_TYPES_DATA)} accessory types")


# Standalone function for quick seeding
def seed_accessory_types_standalone():
    """Seed accessory types (convenience function)."""
    from db.base import SessionLocal
    from db.models import AccessoryType

    session = SessionLocal()
    try:
        seed_accessory_types(session)
    finally:
        session.close()


if __name__ == "__main__":
    seed_accessory_types_standalone()