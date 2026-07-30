from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from db.models import (
    Brand, Category, Collection, CollectionItem, EditorialScore,
    Image, Motorcycle, PriceHistory, Product, ProductCategory,
    ProductMotorcycle, ProductTag, Setting,
)


class ProductRepository:
    """Single point of access for the products table and all relations."""

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Product queries
    # ------------------------------------------------------------------

    def get_product(self, product_id: int) -> Optional[Product]:
        return (
            self.session.query(Product)
            .options(
                joinedload(Product.brand),
                joinedload(Product.categories),
                joinedload(Product.tags),
                joinedload(Product.price_history),
                joinedload(Product.images),
                joinedload(Product.editorial_score),
                joinedload(Product.collection_items),
                joinedload(Product.motorcycles),
            )
            .filter(Product.id == product_id)
            .populate_existing()
            .first()
        )

    def get_by_asin(self, asin: str) -> Optional[Product]:
        return (
            self.session.query(Product)
            .options(
                joinedload(Product.brand),
                joinedload(Product.categories),
                joinedload(Product.tags),
                joinedload(Product.price_history),
                joinedload(Product.images),
                joinedload(Product.editorial_score),
                joinedload(Product.collection_items),
                joinedload(Product.motorcycles),
            )
            .filter(Product.asin == asin)
            .populate_existing()
            .first()
        )

    def get_many(
        self,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        descending: bool = True,
    ) -> List[Product]:
        col = getattr(Product, order_by, Product.updated_at)
        direction = col.desc() if descending else col.asc()
        return (
            self.session.query(Product)
            .options(joinedload(Product.brand))
            .order_by(direction)
            .offset(offset)
            .limit(limit)
            .all()
        )

    def search_products(
        self,
        query: str = "",
        *,
        niche: Optional[str] = None,
        brand_id: Optional[int] = None,
        category_id: Optional[int] = None,
        price_tier: Optional[str] = None,
        deal_quality: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_rating: Optional[float] = None,
        min_score: Optional[float] = None,
        status: Optional[str] = None,
        is_featured: Optional[bool] = None,
        offset: int = 0,
        limit: int = 100,
        order_by: str = "updated_at",
        descending: bool = True,
    ) -> Tuple[List[Product], int]:
        q = self.session.query(Product).options(joinedload(Product.brand))

        if query:
            like = f"%{query}%"
            q = q.filter(
                or_(
                    Product.title.ilike(like),
                    Product.description.ilike(like),
                    Product.asin.ilike(like),
                )
            )

        if niche is not None:
            q = q.filter(Product.niche == niche)
        if brand_id is not None:
            q = q.filter(Product.brand_id == brand_id)
        if category_id is not None:
            q = q.join(ProductCategory).filter(
                ProductCategory.category_id == category_id
            )
        if price_tier:
            q = q.filter(Product.price_tier == price_tier)
        if deal_quality:
            q = q.filter(Product.deal_quality == deal_quality)
        if min_price is not None:
            q = q.filter(Product.price >= min_price)
        if max_price is not None:
            q = q.filter(Product.price <= max_price)
        if min_rating is not None:
            q = q.filter(Product.rating >= min_rating)
        if min_score is not None:
            q = q.filter(Product.score >= min_score)
        if status:
            q = q.filter(Product.status == status)
        if is_featured is not None:
            q = q.filter(Product.is_featured == is_featured)

        total = q.count()
        col = getattr(Product, order_by, Product.updated_at)
        direction = col.desc() if descending else col.asc()
        results = q.order_by(direction).offset(offset).limit(limit).all()
        return results, total

    def count(self) -> int:
        return self.session.query(Product).count()

    # ------------------------------------------------------------------
    # Product mutations
    # ------------------------------------------------------------------

    def insert_product(self, data: Dict[str, Any]) -> Product:
        product = Product(
            asin=data.get("asin"),
            slug=data.get("slug"),
            title=data.get("title") or "",
            description=data.get("description"),
            url=data.get("url"),
            niche=data.get("niche", "motorcycles"),
            price=data.get("price"),
            mrp=data.get("mrp"),
            currency=data.get("currency", "INR"),
            rating=data.get("rating"),
            review_count=data.get("review_count"),
            bestseller_rank=data.get("bestseller_rank"),
            availability=data.get("availability"),
            score=data.get("score") or 0.0,
            price_tier=data.get("price_tier"),
            deal_quality=data.get("deal_quality"),
            status=data.get("status", "active"),
            is_featured=data.get("is_featured", False),
        )
        self.session.add(product)
        self.session.flush()

        self._attach_brand(product, data.get("brand_name"))
        self._attach_categories(product, data.get("category_names"))
        self._attach_tags(product, data.get("tags"))
        self._attach_price_history(product, data)
        self._attach_images(product, data.get("image_urls"))
        self._attach_editorial(product, data.get("editorial"))

        return product

    def update_product(
        self, product_id: int, data: Dict[str, Any]
    ) -> Optional[Product]:
        product = self.session.query(Product).get(product_id)
        if not product:
            return None

        old_price = product.price
        price_in_data = "price" in data
        price_changed = (
            price_in_data
            and data["price"] != old_price
            and not (old_price is None and data["price"] is None)
        )

        scalar_fields = [
            "asin", "slug", "title", "description", "url", "niche",
            "mrp", "currency", "rating", "review_count",
            "bestseller_rank", "availability", "score", "price_tier",
            "deal_quality", "editorial_verdict", "status", "is_featured",
        ]
        for field in scalar_fields:
            if field in data:
                setattr(product, field, data[field])

        if price_in_data:
            product.price = data["price"]

        product.updated_at = datetime.now(timezone.utc)

        if price_changed:
            new_price = product.price
            if new_price is not None:
                self.session.add(
                    PriceHistory(
                        product_id=product.id,
                        old_price=float(old_price) if old_price is not None else None,
                        price=float(new_price),
                        mrp=float(data["mrp"]) if data.get("mrp") is not None else None,
                    )
                )

        if "brand_name" in data:
            self._attach_brand(product, data["brand_name"])
        if "category_names" in data:
            self._replace_categories(product, data["category_names"])
        if "tags" in data:
            self._replace_tags(product, data["tags"])
        if "image_urls" in data:
            self._replace_images(product, data["image_urls"])
        if "editorial" in data:
            self._attach_editorial(product, data["editorial"])

        return product

    def delete_product(self, product_id: int) -> bool:
        product = self.session.query(Product).get(product_id)
        if not product:
            return False
        self.session.delete(product)
        return True

    # ------------------------------------------------------------------
    # Category queries
    # ------------------------------------------------------------------

    def get_categories(self, niche: Optional[str] = None) -> List[Category]:
        q = self.session.query(Category).order_by(Category.name)
        if niche:
            q = q.filter(Category.niche == niche)
        return q.all()

    def set_categories(self, product_id: int, names: List[str]) -> Optional[Product]:
        product = self.session.query(Product).get(product_id)
        if not product:
            return None
        self._replace_categories(product, names)
        return product

    def assign_categories(
        self, product_id: int, *, primary: Optional[str] = None,
        subtype: Optional[str] = None,
        recommended: Optional[List[str]] = None,
        extra_tags: Optional[List[str]] = None,
    ) -> Optional[Product]:
        names = self.derive_category_names(
            primary=primary, subtype=subtype,
            recommended=recommended, extra_tags=extra_tags,
        )
        return self.set_categories(product_id, names)

    # ------------------------------------------------------------------
    # Price history
    # ------------------------------------------------------------------

    def get_price_history(
        self, product_id: int, limit: int = 50
    ) -> List[PriceHistory]:
        return (
            self.session.query(PriceHistory)
            .filter_by(product_id=product_id)
            .order_by(PriceHistory.timestamp.desc())
            .limit(limit)
            .all()
        )

    # ------------------------------------------------------------------
    # Collection queries
    # ------------------------------------------------------------------

    def get_collections(
        self, niche: Optional[str] = None
    ) -> List[Collection]:
        q = self.session.query(Collection).order_by(Collection.sort_order)
        if niche:
            q = q.filter(Collection.niche == niche)
        return q.all()

    def get_collection(self, collection_id: int) -> Optional[Collection]:
        return (
            self.session.query(Collection)
            .options(joinedload(Collection.items))
            .filter(Collection.id == collection_id)
            .first()
        )

    def add_product_to_collection(
        self, collection_id: int, product_id: int,
        sort_order: int = 0, badge: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> CollectionItem:
        item = CollectionItem(
            collection_id=collection_id,
            product_id=product_id,
            sort_order=sort_order,
            badge=badge,
            notes=notes,
        )
        self.session.add(item)
        return item

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    RECOMMENDED_CATEGORIES = {
        "budget": "Budget",
        "premium": "Premium",
        "daily-commute": "Commuting",
        "commuting": "Commuting",
        "safety-focused": "Safety",
        "safety": "Safety",
        "touring": "Touring",
        "off-road": "Off-Road",
        "offroad": "Off-Road",
        "racing": "Racing",
        "track": "Racing",
        "urban": "Urban",
        "adventure": "Adventure",
        "winter": "Winter",
        "waterproof": "Waterproof",
        "heavy-duty": "Heavy Duty",
        "lightweight": "Lightweight",
        "noise-isolation": "Noise Isolation",
        "bluetooth": "Bluetooth",
        "universal": "Universal Fit",
    }

    @staticmethod
    def derive_category_names(
        *,
        primary: Optional[str] = None,
        subtype: Optional[str] = None,
        recommended: Optional[List[str]] = None,
        extra_tags: Optional[List[str]] = None,
    ) -> List[str]:
        names = []
        seen = set()
        for src in (primary, subtype):
            if src and src.strip() and src.strip() not in seen:
                names.append(src.strip())
                seen.add(src.strip())
        for tag in (recommended or []):
            mapped = ProductRepository.RECOMMENDED_CATEGORIES.get(
                tag.strip().lower()
            )
            if mapped and mapped not in seen:
                names.append(mapped)
                seen.add(mapped)
        for tag in (extra_tags or []):
            t = tag.strip().lower()
            mapped = ProductRepository.RECOMMENDED_CATEGORIES.get(t)
            if mapped and mapped not in seen:
                names.append(mapped)
                seen.add(mapped)
        return names

    @staticmethod
    def _slugify(text: str) -> str:
        return text.lower().replace(" ", "-").replace("/", "-").replace("&", "and")

    def _get_or_create_brand(self, name: str) -> Optional[Brand]:
        if not name or not name.strip():
            return None
        name = name.strip()
        brand = self.session.query(Brand).filter_by(name=name).first()
        if not brand:
            brand = Brand(name=name, slug=self._slugify(name))
            self.session.add(brand)
            self.session.flush()
        return brand

    def _get_or_create_category(
        self, name: str, niche: str = "motorcycles"
    ) -> Optional[Category]:
        if not name or not name.strip():
            return None
        name = name.strip()
        cat = (
            self.session.query(Category)
            .filter_by(name=name, niche=niche)
            .first()
        )
        if not cat:
            cat = Category(name=name, slug=self._slugify(name), niche=niche)
            self.session.add(cat)
            self.session.flush()
        return cat

    def _attach_brand(self, product: Product, brand_name: Optional[str]):
        brand = self._get_or_create_brand(brand_name)
        product.brand_id = brand.id if brand else None

    def _attach_categories(self, product: Product, names: Optional[List[str]]):
        if not names:
            return
        for name in names:
            cat = self._get_or_create_category(name, product.niche)
            if cat and cat not in product.categories:
                product.categories.append(cat)

    def _replace_categories(self, product: Product, names: List[str]):
        product.categories = []
        self.session.flush()
        self._attach_categories(product, names)

    def _attach_tags(self, product: Product, tags: Optional[List[str]]):
        if not tags:
            return
        existing = {t.tag for t in product.tags}
        for tag in tags:
            t = tag.strip().lower().replace(" ", "-")
            if t and t not in existing:
                product.tags.append(ProductTag(product_id=product.id, tag=t))
                existing.add(t)

    def _replace_tags(self, product: Product, tags: List[str]):
        product.tags = []
        self.session.flush()
        self._attach_tags(product, tags)

    def _attach_price_history(self, product: Product, data: Dict[str, Any]):
        price = data.get("price")
        if price is not None:
            self.session.add(
                PriceHistory(
                    product_id=product.id,
                    old_price=None,
                    price=float(price),
                    mrp=float(data["mrp"]) if data.get("mrp") is not None else None,
                )
            )

    def _attach_images(
        self, product: Product, images: Optional[List[Dict[str, Any]]]
    ):
        if not images:
            return
        for img in images:
            if img.get("url"):
                product.images.append(
                    Image(
                        product_id=product.id,
                        url=img["url"],
                        variant=img.get("variant", "full"),
                        width=img.get("width"),
                        height=img.get("height"),
                        dominant_color=img.get("dominant_color"),
                        alt_text=img.get("alt_text"),
                        is_primary=img.get("is_primary", False),
                        sort_order=img.get("sort_order", 0),
                    )
                )

    def _replace_images(
        self, product: Product, images: List[Dict[str, Any]]
    ):
        product.images = []
        self.session.flush()
        self._attach_images(product, images)

    def _attach_editorial(
        self, product: Product, editorial: Optional[Dict[str, Any]]
    ):
        if not editorial:
            return
        score = (
            self.session.query(EditorialScore)
            .filter_by(product_id=product.id)
            .first()
        )
        if score:
            for field in ("editor_score", "pros", "cons", "picks",
                          "editorial_notes"):
                if field in editorial:
                    setattr(score, field, editorial[field])
        else:
            self.session.add(
                EditorialScore(product_id=product.id, **{
                    k: v for k, v in editorial.items()
                    if k in ("editor_score", "pros", "cons", "picks",
                             "editorial_notes")
                })
            )



