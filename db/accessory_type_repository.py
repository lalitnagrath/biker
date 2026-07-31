from sqlalchemy.orm import Session
from typing import List, Optional

from db.models import AccessoryType


class AccessoryTypeRepository:
    """Repository for AccessoryType CRUD operations."""

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
        accessory_type = AccessoryType(
            name=data["name"],
            slug=data["slug"],
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
