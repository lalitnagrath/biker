"""
Product Model - Immutable Identity + Mutable Commerce Data
==========================================================
This module defines the single source of truth for what a *product* is.

A product has TWO clearly separated parts:

    1. IMMUTABLE IDENTITY
       These fields define the product forever. Once a Product object is
       created they are read only. Attempting to change them raises
       IdentityError. This is what prevents one product from ever
       displaying another product's ASIN, affiliate URL, title, etc.

    2. MUTABLE COMMERCE DATA
       Fields that legitimately change daily (price, rating, availability,
       affiliate/amazon URLs sourced from a commerce feed, etc.). These may
       only be updated through enrich(), and only when the incoming data has
       been confirmed by the matcher to belong to the SAME product.

The master catalog owns identity. Commerce feeds (Amazon, Flipkart, Myntra,
Ajio, Reliance Digital, ...) may only update mutable fields. Adding a new
commerce source therefore never touches product identity.

Product is a dict subclass so it stays 100% compatible with the existing
generator, Jinja templates (attribute + item access) and json serialization,
while still enforcing immutability of identity.
"""

from typing import Any, Dict, Iterable, Mapping


class IdentityError(Exception):
    """Raised when code attempts to mutate an immutable identity field."""


# Fields that define a product forever. Never overwrite them.
IDENTITY_FIELDS = (
    "internal_id",
    "slug",
    "asin",
    "title",
    "brand",
    "category",
    "specifications",
    "description",
    "pros",
    "cons",
    "features",
)

# Fields that may change daily. Only these may be enriched by commerce feeds.
COMMERCE_FIELDS = (
    "price",
    "mrp",
    "discount",
    "affiliate_url",
    "amazon_url",
    "image_url",
    "rating",
    "review_count",
    "bestseller",
    "amazon_choice",
    "bought_last_month",
    "availability",
)

# The subset of identity fields that must remain byte for byte identical after
# any merge. If any of these changes the merge is aborted (see validate_merge).
CORE_IDENTITY_FIELDS = (
    "internal_id",
    "slug",
    "asin",
    "title",
    "brand",
    "category",
)


class Product(dict):
    """A product with immutable identity and mutable commerce data.

    Behaves like a normal dict (so existing code, Jinja templates and json
    keep working) but refuses to overwrite identity fields once set.

    Legacy aliases: the historical catalog uses ``reviews`` and ``image``
    where the new model uses ``review_count`` and ``image_url``. Both are
    accepted transparently so no downstream template has to change.
    """

    _ALIAS = {
        "reviews": "review_count",
        "image": "image_url",
    }

    def __init__(self, data: Mapping[str, Any] = None, **kwargs):
        super().__init__()
        self._identity_locked = False
        merged: Dict[str, Any] = {}
        if data:
            merged.update(data)
        if kwargs:
            merged.update(kwargs)
        for key, value in merged.items():
            dict.__setitem__(self, key, value)
        # Guarantee a stable internal_id so identity always exists.
        if not self.get("internal_id"):
            dict.__setitem__(self, "internal_id", self._derive_internal_id())
        self._identity_locked = True

    def _derive_internal_id(self) -> str:
        """Derive a deterministic internal_id from the strongest available key."""
        asin = (self.get("asin") or "").strip().upper()
        if asin:
            return f"asin:{asin}"
        slug = (self.get("slug") or "").strip().lower()
        if slug:
            return f"slug:{slug}"
        title = (self.get("title") or "").strip().lower()
        if title:
            return f"title:{title}"
        return ""

    def __setitem__(self, key: str, value: Any) -> None:
        if getattr(self, "_identity_locked", False) and key in IDENTITY_FIELDS:
            current = dict.get(self, key)
            if current == value:
                return  # no-op write of the same value is harmless
            raise IdentityError(
                f"Cannot modify immutable identity field {key!r} "
                f"(is {current!r}, attempted {value!r}) on product "
                f"{dict.get(self, 'internal_id')!r}. Identity is read-only."
            )
        dict.__setitem__(self, key, value)

    def __setattr__(self, key: str, value: Any) -> None:
        # Allow internal bookkeeping attributes (leading underscore) only.
        if key.startswith("_"):
            object.__setattr__(self, key, value)
            return
        self[key] = value

    def __getattr__(self, key: str) -> Any:
        # Jinja + attribute style access, e.g. product.slug
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def update(self, *args, **kwargs):  # type: ignore[override]
        for k, v in dict(*args, **kwargs).items():
            self[k] = v

    def setdefault(self, key, default=None):  # type: ignore[override]
        if key not in self:
            self[key] = default
        return self[key]

    # ----- Commerce enrichment -----

    def enrich(self, commerce_data: Mapping[str, Any], *, overwrite: bool = True) -> int:
        """Update mutable commerce fields from a confirmed-same-product feed.

        Only fields in COMMERCE_FIELDS (plus their legacy aliases) are ever
        written. Identity is never touched. Returns the number of fields
        updated.

        This is the ONLY sanctioned way to change a product after creation.
        Callers must have already confirmed via the matcher that the incoming
        data belongs to the SAME product.
        """
        updated = 0
        for raw_key, value in commerce_data.items():
            key = self._ALIAS.get(raw_key, raw_key)
            if key not in COMMERCE_FIELDS:
                continue
            if value in (None, "", []):
                continue
            if not overwrite and self.get(key):
                continue
            if dict.get(self, key) != value:
                dict.__setitem__(self, key, value)
                updated += 1
        return updated

    def identity_snapshot(self) -> Dict[str, Any]:
        """Return a copy of the core identity fields for post-merge assertions."""
        return {f: dict.get(self, f) for f in CORE_IDENTITY_FIELDS}

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict copy (safe for json.dumps)."""
        return {k: v for k, v in self.items()}


def coerce_products(items: Iterable[Mapping[str, Any]]) -> list:
    """Convert a list of raw dicts into Product instances.

    Idempotent: already-Product instances are returned unchanged.
    """
    result = []
    for item in items:
        if isinstance(item, Product):
            result.append(item)
        else:
            result.append(Product(item))
    return result


def assert_identity_unchanged(product: "Product", snapshot: Mapping[str, Any]) -> None:
    """Raise IdentityError if any core identity field drifted from snapshot.

    Used after every merge as the last line of defence. Never silently
    continue: a mismatch here means the catalog is corrupt.
    """
    for field in CORE_IDENTITY_FIELDS:
        current = product.get(field)
        original = snapshot.get(field)
        if current != original:
            raise IdentityError(
                f"Identity drift detected on field {field!r}: "
                f"was {original!r}, now {current!r} "
                f"(product {product.get('internal_id')!r}). Merge aborted."
            )
