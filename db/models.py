from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer,
    JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db.base import Base


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    slug = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    logo_url = Column(String(1024), nullable=True)
    website_url = Column(String(2048), nullable=True)
    is_trusted = Column(Boolean, default=False)
    reputation_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="brand")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, index=True)
    niche = Column(String(100), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)

    parent = relationship("Category", back_populates="children",
                          remote_side="Category.id")
    children = relationship("Category", back_populates="parent",
                            remote_side="Category.parent_id")


__all__ = ["Brand", "Category"]


class AccessoryType(Base):
    __tablename__ = "accessory_types"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    slug = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    icon = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    products = relationship("Product", back_populates="accessory_type")
    upgrade_sections = relationship(
        "UpgradeSection",
        back_populates="accessory_type",
        cascade="all, delete-orphan"
    )


__all__.append("AccessoryType")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    asin = Column(String(20), nullable=False, unique=True, index=True)
    slug = Column(String(255), nullable=True, index=True)
    title = Column(String(1024), nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String(2048), nullable=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True)
    accessory_type_id = Column(Integer, ForeignKey("accessory_types.id"), nullable=True)
    niche = Column(String(100), nullable=False, index=True)
    price = Column(Float, nullable=True)
    mrp = Column(Float, nullable=True)
    currency = Column(String(10), default="INR")
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)
    bestseller_rank = Column(Integer, nullable=True)
    availability = Column(String(50), nullable=True)
    price_tier = Column(String(20), nullable=True)
    deal_quality = Column(String(20), nullable=True)
    editorial_verdict = Column(String(50), nullable=True)
    score = Column(Float, default=0.0)
    status = Column(String(20), default="active")
    is_featured = Column(Boolean, default=False)
    compatible_bikes = Column(JSON, nullable=True)
    universal = Column(Boolean, default=False, nullable=False)
    last_sync_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    brand = relationship("Brand", back_populates="products")
    accessory_type = relationship("AccessoryType", back_populates="products")
    categories = relationship("Category", secondary="product_categories",
                              back_populates="products")
    tags = relationship("ProductTag", back_populates="product",
                        cascade="all, delete-orphan")
    price_history = relationship("PriceHistory", back_populates="product",
                                 cascade="all, delete-orphan",
                                 order_by="PriceHistory.timestamp")
    images = relationship("Image", back_populates="product",
                          cascade="all, delete-orphan",
                          order_by="Image.sort_order")
    editorial_score = relationship("EditorialScore", back_populates="product",
                                   uselist=False, cascade="all, delete-orphan")
    collection_items = relationship("CollectionItem", back_populates="product",
                                     cascade="all, delete-orphan")
    motorcycles = relationship("Motorcycle", secondary="product_motorcycle",
                               back_populates="products")
    recommended_for_motorcycles = relationship(
        "Motorcycle",
        secondary="motorcycle_recommended_products",
        back_populates="recommended_products",
    )
    upgrade_sections = relationship(
        "UpgradeSection",
        secondary="product_upgrade_sections",
        back_populates="products",
    )


__all__.append("Product")


class ProductCategory(Base):
    __tablename__ = "product_categories"
    __table_args__ = (
        UniqueConstraint("product_id", "category_id",
                         name="uq_product_category"),
        Index("ix_product_categories_category_id", "category_id"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"),
                        nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"),
                         nullable=False)


Category.products = relationship("Product", secondary="product_categories",
                                 back_populates="categories")


__all__.append("ProductCategory")


class ProductTag(Base):
    __tablename__ = "product_tags"
    __table_args__ = (
        UniqueConstraint("product_id", "tag", name="uq_product_tag"),
        Index("ix_product_tags_tag", "tag"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"),
                        nullable=False)
    tag = Column(String(100), nullable=False)

    product = relationship("Product", back_populates="tags")


__all__.append("ProductTag")


class Collection(Base):
    __tablename__ = "collections"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, index=True)
    niche = Column(String(100), nullable=True, index=True)
    description = Column(Text, nullable=True)
    hero_image = Column(String(1024), nullable=True)
    seo_title = Column(String(255), nullable=True)
    seo_description = Column(Text, nullable=True)
    is_visible = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    rule_type = Column(String(20), default="manual")
    rule_definition = Column(JSON, nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("CollectionItem", back_populates="collection",
                         cascade="all, delete-orphan",
                         order_by="CollectionItem.sort_order")
    related = relationship(
        "Collection",
        secondary="collection_relations",
        primaryjoin="Collection.id == CollectionRelation.collection_id",
        secondaryjoin="Collection.id == CollectionRelation.related_collection_id",
        backref="related_from",
        lazy="selectin",
    )
    motorcycles = relationship(
        "Motorcycle",
        secondary="motorcycle_collections",
        back_populates="collections",
    )


class CollectionItem(Base):
    __tablename__ = "collection_items"
    __table_args__ = (
        UniqueConstraint("collection_id", "product_id",
                         name="uq_collection_product"),
        Index("ix_collection_items_sort", "collection_id", "sort_order"),
    )

    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer,
                           ForeignKey("collections.id", ondelete="CASCADE"),
                           nullable=False)
    product_id = Column(Integer,
                        ForeignKey("products.id", ondelete="CASCADE"),
                        nullable=False)
    sort_order = Column(Integer, default=0)
    badge = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    is_featured = Column(Boolean, default=False)

    collection = relationship("Collection", back_populates="items")
    product = relationship("Product", back_populates="collection_items")


class CollectionRelation(Base):
    __tablename__ = "collection_relations"
    __table_args__ = (
        UniqueConstraint("collection_id", "related_collection_id",
                         name="uq_collection_relation"),
    )

    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer,
                           ForeignKey("collections.id", ondelete="CASCADE"),
                           nullable=False)
    related_collection_id = Column(
        Integer,
        ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
    )


__all__.extend(["Collection", "CollectionItem", "CollectionRelation"])


class Image(Base):
    __tablename__ = "images"
    __table_args__ = (
        Index("ix_images_product_variant", "product_id", "variant"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"),
                        nullable=False)
    url = Column(String(2048), nullable=False)
    local_path = Column(String(1024), nullable=True)
    variant = Column(String(20), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    dominant_color = Column(String(7), nullable=True)
    alt_text = Column(String(500), nullable=True)
    is_primary = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)

    product = relationship("Product", back_populates="images")


__all__.append("Image")


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        Index("ix_price_history_timestamp", "timestamp"),
        Index("ix_price_history_product_timestamp", "product_id", "timestamp"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"),
                        nullable=False)
    old_price = Column(Float, nullable=True)
    price = Column(Float, nullable=False)
    mrp = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="price_history")


__all__.append("PriceHistory")


class EditorialScore(Base):
    __tablename__ = "editorial_scores"

    product_id = Column(Integer,
                        ForeignKey("products.id", ondelete="CASCADE"),
                        primary_key=True, unique=True)
    editor_score = Column(Float, default=0.0)
    pros = Column(JSON, nullable=True)
    cons = Column(JSON, nullable=True)
    features = Column(JSON, nullable=True)
    picks = Column(JSON, nullable=True)
    recommended_for = Column(JSON, nullable=True)
    editorial_notes = Column(Text, nullable=True)
    editors_choice = Column(Boolean, default=False)
    override_rank = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product = relationship("Product", back_populates="editorial_score")


__all__.append("EditorialScore")


class Motorcycle(Base):
    __tablename__ = "motorcycles"
    __table_args__ = (
        UniqueConstraint("make", "model", "year_start",
                         name="uq_make_model_year"),
        Index("ix_motorcycles_make", "make"),
        Index("ix_motorcycles_model", "model"),
    )

    id = Column(Integer, primary_key=True)
    make = Column(String(255), nullable=False)
    model = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=True, index=True)
    year_start = Column(Integer, nullable=True)
    year_end = Column(Integer, nullable=True)
    category = Column(String(100), nullable=True)
    engine_cc = Column(Integer, nullable=True)
    type = Column(String(50), nullable=True)
    hero_image = Column(String(1024), nullable=True)
    description = Column(Text, nullable=True)

    products = relationship("Product", secondary="product_motorcycle",
                            back_populates="motorcycles")
    tags = relationship("MotorcycleTag", back_populates="motorcycle",
                        cascade="all, delete-orphan")
    faqs = relationship("MotorcycleFAQ", back_populates="motorcycle",
                        cascade="all, delete-orphan",
                        order_by="MotorcycleFAQ.sort_order")
    upgrade_sections = relationship(
        "UpgradeSection",
        secondary="motorcycle_upgrade_sections",
        back_populates="motorcycles",
    )
    recommended_products = relationship(
        "Product",
        secondary="motorcycle_recommended_products",
        back_populates="recommended_for_motorcycles",
    )
    collections = relationship(
        "Collection",
        secondary="motorcycle_collections",
        back_populates="motorcycles",
    )
    related_motorcycles = relationship(
        "Motorcycle",
        secondary="motorcycle_relations",
        primaryjoin="Motorcycle.id==MotorcycleRelation.motorcycle_id",
        secondaryjoin="Motorcycle.id==MotorcycleRelation.related_motorcycle_id",
        backref="related_from",
        lazy="selectin",
    )


__all__.append("Motorcycle")


class ProductMotorcycle(Base):
    __tablename__ = "product_motorcycle"
    __table_args__ = (
        UniqueConstraint("product_id", "motorcycle_id",
                         name="uq_product_motorcycle"),
        Index("ix_product_motorcycle_motorcycle", "motorcycle_id"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"),
                        nullable=False)
    motorcycle_id = Column(Integer,
                           ForeignKey("motorcycles.id", ondelete="CASCADE"),
                           nullable=False)
    confidence = Column(Float, default=0.0)
    match_strategy = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)


__all__.append("ProductMotorcycle")


class MotorcycleTag(Base):
    __tablename__ = "motorcycle_tags"
    __table_args__ = (
        UniqueConstraint("motorcycle_id", "tag", name="uq_motorcycle_tag"),
        Index("ix_motorcycle_tags_tag", "tag"),
    )

    id = Column(Integer, primary_key=True)
    motorcycle_id = Column(
        Integer, ForeignKey("motorcycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    tag = Column(String(100), nullable=False)

    motorcycle = relationship("Motorcycle", back_populates="tags")


__all__.append("MotorcycleTag")


class MotorcycleFAQ(Base):
    __tablename__ = "motorcycle_faqs"
    __table_args__ = (
        Index("ix_motorcycle_faqs_sort", "motorcycle_id", "sort_order"),
    )

    id = Column(Integer, primary_key=True)
    motorcycle_id = Column(
        Integer, ForeignKey("motorcycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    question = Column(String(500), nullable=False)
    answer = Column(Text, nullable=False)
    sort_order = Column(Integer, default=0)

    motorcycle = relationship("Motorcycle", back_populates="faqs")


__all__.append("MotorcycleFAQ")


class UpgradeSection(Base):
    __tablename__ = "upgrade_sections"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    icon = Column(String(100), nullable=True)
    accessory_type_id = Column(Integer, ForeignKey("accessory_types.id"), nullable=True)
    accessory_type = relationship("AccessoryType", back_populates="upgrade_sections")
    sort_order = Column(Integer, default=0)

    motorcycles = relationship(
        "Motorcycle",
        secondary="motorcycle_upgrade_sections",
        back_populates="upgrade_sections",
    )
    products = relationship(
        "Product",
        secondary="product_upgrade_sections",
        back_populates="upgrade_sections",
    )


__all__.append("UpgradeSection")


class MotorcycleUpgradeSection(Base):
    __tablename__ = "motorcycle_upgrade_sections"
    __table_args__ = (
        UniqueConstraint("motorcycle_id", "upgrade_section_id",
                         name="uq_moto_upgrade"),
    )

    id = Column(Integer, primary_key=True)
    motorcycle_id = Column(
        Integer, ForeignKey("motorcycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    upgrade_section_id = Column(
        Integer, ForeignKey("upgrade_sections.id", ondelete="CASCADE"),
        nullable=False,
    )


__all__.append("MotorcycleUpgradeSection")


class ProductUpgradeSection(Base):
    __tablename__ = "product_upgrade_sections"
    __table_args__ = (
        UniqueConstraint("product_id", "upgrade_section_id",
                         name="uq_product_upgrade"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    upgrade_section_id = Column(
        Integer, ForeignKey("upgrade_sections.id", ondelete="CASCADE"),
        nullable=False,
    )


__all__.append("ProductUpgradeSection")


class MotorcycleRecommendedProduct(Base):
    __tablename__ = "motorcycle_recommended_products"
    __table_args__ = (
        UniqueConstraint("motorcycle_id", "product_id",
                         name="uq_moto_recommended_product"),
    )

    id = Column(Integer, primary_key=True)
    motorcycle_id = Column(
        Integer, ForeignKey("motorcycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = Column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )


__all__.append("MotorcycleRecommendedProduct")


class MotorcycleCollection(Base):
    __tablename__ = "motorcycle_collections"
    __table_args__ = (
        UniqueConstraint("motorcycle_id", "collection_id",
                         name="uq_moto_collection"),
    )

    id = Column(Integer, primary_key=True)
    motorcycle_id = Column(
        Integer, ForeignKey("motorcycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    collection_id = Column(
        Integer, ForeignKey("collections.id", ondelete="CASCADE"),
        nullable=False,
    )


__all__.append("MotorcycleCollection")


class MotorcycleRelation(Base):
    __tablename__ = "motorcycle_relations"
    __table_args__ = (
        UniqueConstraint("motorcycle_id", "related_motorcycle_id",
                         name="uq_moto_relation"),
    )

    id = Column(Integer, primary_key=True)
    motorcycle_id = Column(
        Integer, ForeignKey("motorcycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    related_motorcycle_id = Column(
        Integer, ForeignKey("motorcycles.id", ondelete="CASCADE"),
        nullable=False,
    )


__all__.append("MotorcycleRelation")


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(255), nullable=False, unique=True, index=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


__all__.append("Setting")