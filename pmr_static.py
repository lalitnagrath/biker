"""Pimp My Ride - build-time (static) data generation.

The generated website is pure static HTML deployed to Cloudflare Pages,
with no backend and no runtime API.  This module produces all of the data
the Pimp My Ride section needs at generation time and injects it into each
motorcycle page as ``window.PIMP_MY_RIDE_DATA``.  The browser never makes a
network request; the front-end only wires up expand/collapse + tab UI.

Collection taxonomy is data-driven from ``pmr_collections.json``: curated
collections come from the DB, smart collections (by category, price band,
rating) and bike-type-specific collections come from the JSON config.
Adding a collection to the JSON makes it appear on every motorcycle page
at the next build - no template or JavaScript changes are required.
"""

import json
import math
from pathlib import Path

from sqlalchemy.orm import Session, joinedload

from db.base import engine
import db.models  # noqa: F401  - register ORM models with the metadata

CONFIG_PATH = Path(__file__).resolve().parent / "pmr_collections.json"

_CONFIG_CACHE = None


def load_config():
    """Load (and cache) the data-driven collection config."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            _CONFIG_CACHE = json.load(fh)
    return _CONFIG_CACHE


def load_upgrade_collections():
    """Return every upgrade collection plus the ASINs of its member products.

    Returns a list of dicts:
        {
            "slug": str, "name": str, "description": str, "icon": str,
            "sort_order": int, "enabled": bool, "asins": [str, ...],
        }

    Ordered by ``sort_order`` then ``name`` exactly like the old API endpoint
    ``/api/upgrade-collections`` used to do.
    """
    with Session(engine) as session:
        collections = (
            session.query(db.models.UpgradeCollection)
            .order_by(
                db.models.UpgradeCollection.sort_order,
                db.models.UpgradeCollection.name,
            )
            .all()
        )
        products = (
            session.query(db.models.Product)
            .options(joinedload(db.models.Product.upgrade_collections))
            .all()
        )

    asins_by_slug = {}
    for product in products:
        if not product.asin:
            continue
        for coll in product.upgrade_collections:
            asins_by_slug.setdefault(coll.slug, set()).add(product.asin)

    result = []
    for coll in collections:
        result.append(
            {
                "slug": coll.slug,
                "name": coll.name,
                "description": coll.description or "",
                "icon": coll.icon or "",
                "sort_order": coll.sort_order or 0,
                "enabled": bool(coll.enabled),
                "asins": sorted(asins_by_slug.get(coll.slug, set())),
            }
        )
    return result


def usable_image(url, base_path):
    """Mirror the client-side ``usableImage()`` resolution.

    Absolute Amazon URLs are kept as-is; local product filenames are turned
    into a relative path that works from any generated page.
    """
    s = str(url or "")
    if not s:
        return ""
    if s.startswith("http://") or s.startswith("https://") or s.startswith("//"):
        return s
    if "." not in s:
        return ""
    base = s.replace("\\", "/").rsplit("/", 1)[-1]
    if not base:
        return ""
    return base_path + "static/images/products/" + base


def normalize_product(product, base_path):
    """Flatten a generator product dict into the shape the UI expects.

    Field names/types intentionally match the client-side ``normalizeProduct()``
    that the old /api/products flow produced.
    """
    raw_image = product.get("image") or product.get("amazon_image_url") or ""
    return {
        "slug": product.get("slug") or product.get("asin") or "",
        "asin": product.get("asin") or "",
        "title": product.get("title") or "",
        "brand": product.get("brand") or "",
        "category": product.get("category") or "",
        "universal": bool(product.get("universal")),
        "compatible_bikes": product.get("compatible_bikes") or [],
        "status": product.get("status") or "",
        "price": int(product.get("price") or 0),
        "mrp": int(product.get("mrp") or 0),
        "rating": product.get("rating") or 0,
        "review_count": int(product.get("review_count") or product.get("reviews") or 0),
        "editor_rating": product.get("editor_rating") or 0,
        "editorial_verdict": product.get("editorial_verdict") or "",
        "editors_choice": bool(product.get("editors_choice")),
        "image": usable_image(raw_image, base_path),
        "affiliate_url": product.get("affiliate_url") or "",
    }


def _norm_category(category):
    """Normalize a category value to the keys used in the JSON config."""
    return str(category or "").strip().lower().replace(" ", "_").replace("-", "_")


def _rank_products(products):
    """Rank products inside a collection.

    Mirrors the client-side ``scoreProduct()``: Editor's Choice first, then
    a weighted blend of editor rating, user rating, review volume, having a
    price, image and affiliate link.  Sorting is stable so products that are
    already ranked well upstream keep their relative order.
    """
    def score(p):
        s = 0
        ev = str(p.get("editorial_verdict") or "").lower()
        if p.get("editors_choice") or "editor" in ev:
            s += 40
        elif "best value" in ev:
            s += 30
        elif "premium" in ev:
            s += 25
        s += float(p.get("editor_rating") or 0) * 0.3
        s += float(p.get("rating") or 0) * 4
        reviews = int(p.get("review_count") or p.get("reviews") or 0)
        s += min(20, math.log10(reviews + 1) * 10)
        if float(p.get("price") or 0) > 0:
            s += 8
        if p.get("image") or p.get("amazon_image_url"):
            s += 4
        if p.get("affiliate_url"):
            s += 2
        if p.get("status") == "approved":
            s += 6
        elif p.get("status") == "review":
            s += 3
        return s

    return sorted(products, key=score, reverse=True)


def _products_for_spec(spec, matched_products, by_category):
    """Resolve the member products of a smart-collection spec."""
    cats = spec.get("categories")
    if cats:
        pool = []
        seen = set()
        for c in cats:
            for p in by_category.get(c, []):
                key = p.get("asin") or id(p)
                if key not in seen:
                    seen.add(key)
                    pool.append(p)
    else:
        pool = list(matched_products)

    exclude = set(spec.get("exclude_categories") or [])
    if exclude:
        pool = [p for p in pool if _norm_category(p.get("category")) not in exclude]

    price_max = spec.get("price_max") or 0
    if price_max:
        pool = [p for p in pool if 0 < float(p.get("price") or 0) <= price_max]

    min_rating = spec.get("min_rating") or 0
    if min_rating:
        pool = [p for p in pool if float(p.get("rating") or 0) >= min_rating]

    return _rank_products(pool)


def _build_collection_item(slug, name, description, icon, badge, products,
                           base_path, sort_order, max_products=0):
    """Build a single collection payload entry ready for the template/JS."""
    norm = [normalize_product(p, base_path) for p in products]
    if max_products:
        norm = norm[:max_products]
    hero = next((n for n in norm if n.get("image")), None) or (norm[0] if norm else None)
    prices = [n["price"] for n in norm if n.get("price", 0) > 0]
    return {
        "slug": slug,
        "name": name,
        "description": description or "",
        "cardDescription": (description or "")[:120],
        "icon": icon or "",
        "badge": badge or "",
        "sort_order": int(sort_order or 0),
        "count": len(norm),
        "heroImage": (hero or {}).get("image", ""),
        "startingPrice": min(prices) if prices else None,
        "compatibleProducts": norm,
    }


def _select_products(pool, target, max_same_brand, max_same_category):
    """Pick a diverse, editorially-curated subset of ``target`` products.

    Products are ranked best-first, then greedily selected so no single brand
    or product category dominates the collection.  A relaxed second pass fills
    any remaining slots so short pools never come back empty.
    """
    ranked = _rank_products(pool)
    picked = []
    brand_n = {}
    cat_n = {}

    def bump(p):
        b = p.get("brand") or "_"
        c = _norm_category(p.get("category"))
        brand_n[b] = brand_n.get(b, 0) + 1
        cat_n[c] = cat_n.get(c, 0) + 1

    for p in ranked:
        if len(picked) >= target:
            break
        b = p.get("brand") or "_"
        c = _norm_category(p.get("category"))
        if brand_n.get(b, 0) >= max_same_brand:
            continue
        if cat_n.get(c, 0) >= max_same_category:
            continue
        picked.append(p)
        bump(p)

    if len(picked) < target:
        for p in ranked:
            if len(picked) >= target:
                break
            if p not in picked:
                picked.append(p)

    return picked


def _build_candidates(config, collections, matched_products, bike_type):
    """Build every candidate collection for a motorcycle.

    Returns a list of dicts (ordered by type relevance priority) with:
        slug, name, description, icon, badge, sort_order, products,
        allow_overlap
    """
    matched_by_asin = {}
    by_category = {}
    for product in matched_products:
        asin = product.get("asin") or ""
        if asin and asin not in matched_by_asin:
            matched_by_asin[asin] = product
        by_category.setdefault(_norm_category(product.get("category")), []).append(product)

    priority = config.get("type_priorities", {}).get(bike_type) or config.get("default_priority", [])
    prio_index = {slug: i for i, slug in enumerate(priority)}

    candidates = []

    db_order = config.get("db_collection_display_order") or {}
    db_badges = config.get("db_collection_badges") or {}
    for coll in collections:
        if not coll.get("enabled", True):
            continue
        products = []
        for asin in coll.get("asins", []):
            product = matched_by_asin.get(asin)
            if product is not None:
                products.append(product)
        if not products:
            continue
        candidates.append({
            "slug": coll["slug"],
            "name": coll["name"],
            "description": coll.get("description") or "",
            "icon": coll.get("icon") or "",
            "badge": db_badges.get(coll["slug"], ""),
            "sort_order": db_order.get(coll["slug"], coll.get("sort_order") or 0),
            "products": products,
            "allow_overlap": False,
        })

    for spec in config.get("collections", []):
        products = _products_for_spec(spec, matched_products, by_category)
        if not products:
            continue
        candidates.append({
            "slug": spec["slug"],
            "name": spec["name"],
            "description": spec.get("description") or "",
            "icon": spec.get("icon") or "",
            "badge": spec.get("badge") or "",
            "sort_order": spec.get("sort_order") or 0,
            "products": products,
            "allow_overlap": bool(spec.get("allow_overlap")),
        })

    bike_spec = config.get("bike_specific", {}).get(bike_type)
    if bike_spec:
        products = _products_for_spec(bike_spec, matched_products, by_category)
        if products:
            candidates.append({
                "slug": bike_spec["slug"],
                "name": bike_spec["name"],
                "description": bike_spec.get("description") or "",
                "icon": bike_spec.get("icon") or "",
                "badge": bike_spec.get("badge") or "",
                "sort_order": bike_spec.get("sort_order") or 0,
                "products": products,
                "allow_overlap": False,
            })

    for c in candidates:
        c["prio"] = prio_index.get(c["slug"], len(priority) + (c.get("sort_order") or 0))

    candidates.sort(key=lambda c: (c["prio"], c.get("sort_order") or 0, c["name"]))
    return candidates


def build_pimp_my_ride(collections, matched_products, base_path, bike=None):
    """Build the editorially-curated Pimp My Ride payload for a motorcycle.

    Collections are ranked by relevance to the motorcycle type; products are
    de-duplicated across collections (true essentials may appear up to
    ``max_appearances`` times); each collection is filled with a small,
    brand-and-type-diverse set; weak collections are dropped; and only the
    best ``max_visible`` collections are shown up front (the rest are behind
    the "View More Collections" toggle).
    """
    config = load_config()
    controls = config.get("controls") or {}
    min_products = int(controls.get("min_products", 4))
    target_products = int(controls.get("target_products", 6))
    max_visible = int(controls.get("max_visible", 8))
    max_appearances = int(controls.get("max_appearances", 2))
    max_same_brand = int(controls.get("max_same_brand", 2))
    max_same_category = int(controls.get("max_same_category", 2))
    always_show = set(controls.get("always_show", []))
    essential_categories = set(controls.get("essential_categories", []))

    bike_type = (bike or {}).get("type") or ""
    candidates = _build_candidates(config, collections, matched_products, bike_type)

    # Allocate products collection-by-collection in relevance order.  A product
    # is available to a later collection only if it is a true essential (up to
    # max_appearances total) or has never been used — enforced globally across
    # every collection, so no product ever shows up in more than two.
    assigned = {}
    for c in candidates:
        pool = []
        for p in c["products"]:
            asin = p.get("asin")
            if not asin:
                continue
            limit = max_appearances if _norm_category(p.get("category")) in essential_categories else 1
            if assigned.get(asin, 0) < limit:
                pool.append(p)
        selected = _select_products(pool, target_products, max_same_brand, max_same_category)
        for p in selected:
            asin = p.get("asin")
            if asin:
                assigned[asin] = assigned.get(asin, 0) + 1
        c["selected"] = selected

    # Drop weak, non-essential collections; keep "always_show" ones regardless
    # (as long as they have at least one product — never render an empty card).
    kept = [
        c for c in candidates
        if len(c["selected"]) >= min_products or (c["slug"] in always_show and c["selected"])
    ]

    # Featured slots go to the strongest, most relevant collections first, so a
    # weak always-show collection (e.g. Emergency Kit / Security) falls into the
    # "View More" grid instead of wasting a prominent slot.
    kept.sort(key=lambda c: (0 if len(c["selected"]) >= min_products else 1, c["prio"]))
    for i, c in enumerate(kept):
        c["featured"] = i < max_visible

    payload = []
    for c in kept:
        item = _build_collection_item(
            slug=c["slug"], name=c["name"], description=c["description"],
            icon=c["icon"], badge=c["badge"], products=c["selected"],
            base_path=base_path, sort_order=c["sort_order"],
        )
        item["featured"] = c["featured"]
        payload.append(item)

    return {"collections": payload}
