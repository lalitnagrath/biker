"""
Product Selection Engine
========================
Reusable recommendation engine for selecting, ranking, and diversifying
motorcycle accessory products from the product catalog.

Every function is motorcycle-agnostic and category-agnostic.
Feed it products + context, get curated results back.

All categories use canonical snake_case forms defined in product_library.py.
"""

from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict
import math

# Import canonical category system from product_library.
# This is the single source of truth for all category definitions.
from product_library import (
    CANONICAL_CATEGORIES,
    CATEGORY_ALIASES as _CATEGORY_ALIASES,
    CATEGORY_DISPLAY,
    CATEGORY_SLUGS,
    HIGH_CONFIDENCE_CATEGORIES,
    UNIVERSAL_CATEGORIES,
    BIKE_SPECIFIC_CATEGORIES,
    normalize_category as _lib_normalize_category,
    category_display as _lib_category_display,
    category_slug as _lib_category_slug,
    classify_product_type,
)

# Re-export for backward compatibility within this module
CATEGORY_ALIASES = _CATEGORY_ALIASES
normalize_category = _lib_normalize_category


def category_display(canonical: str) -> str:
    """Return human-readable display name for a canonical category."""
    return _lib_category_display(canonical)


def category_slug(canonical: str) -> str:
    """Return URL slug for a canonical category."""
    return _lib_category_slug(canonical)


# ===== Category Keyword Fallbacks =====
# Used when exact category matching fails in find_products_by_category.
# Keywords are checked against product category, title, and best_for.
# All keys are canonical snake_case categories.

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    'helmet': ['helmet', 'headgear', 'full face', 'flip up', 'dual visor'],
    'phone_mount': ['phone mount', 'phone holder', 'mobile holder', 'handlebar mount', 'bike phone'],
    'crash_guard': ['crash guard', 'engine guard', 'leg guard', 'frame slider', 'crash bar'],
    'bike_cover': ['bike cover', 'body cover', 'motorcycle cover', 'waterproof cover', 'dust cover'],
    'chain_lube': ['chain lub', 'chain lubricant', 'chain spray', 'chain wax'],
    'chain_cleaner': ['chain clean', 'chain cleaner'],
    'engine_oil': ['engine oil', '10w-40', '10w-50', '20w-50', 'motor oil', 'engine lubricant'],
    'tyre_inflator': ['tyre inflat', 'tire inflat', 'air pump', 'air compressor', 'tyre pump'],
    'gloves': ['riding gloves', 'bike gloves', 'gloves', 'riding glove'],
    'jackets': ['riding jacket', 'bike jacket', 'jacket', 'riding jacket'],
    'tank_bag': ['tank bag', 'tankpack'],
    'saddle_bag': ['saddlebag', 'saddle bag', 'side bag', 'pannier'],
    'tail_bag': ['tail bag', 'rear bag', 'seat bag', 'backrest bag'],
    'knee_guard': ['knee guard', 'knee pad', 'knee protector'],
    'usb_charger': ['dual usb', 'quick charge', 'usb charging', 'motorcycle charger', 'bike charger'],
    'disc_lock': ['disc', 'disk', 'brake lock', 'anti-theft', 'alarm lock'],
    'chain_lock': ['chain', 'lock', 'security', 'anti-theft', 'chain lock'],
}

# Valid categories for the recommendation engine (all canonical snake_case).
VALID_CATEGORIES = CANONICAL_CATEGORIES

# ===== Category Preferred Price Ranges (INR) =====
# Keyed by canonical snake_case category name.
CATEGORY_PRICE_RANGES: Dict[str, Tuple[int, int]] = {
    'phone_mount': (300, 900),
    'helmet': (1500, 5000),
    'chain_lube': (250, 600),
    'chain_cleaner': (250, 600),
    'bike_cover': (500, 1500),
    'tyre_inflator': (1500, 3500),
    'engine_oil': (400, 1200),
    'crash_guard': (1000, 4000),
    'gloves': (500, 2500),
    'jackets': (2000, 8000),
    'tank_bag': (1000, 4000),
    'saddle_bag': (1500, 6000),
    'tail_bag': (1000, 4000),
    'knee_guard': (500, 2500),
    'usb_charger': (300, 1500),
    'disc_lock': (400, 2000),
    'chain_lock': (300, 1500),
}

# Brands with an established reputation for the Indian two-wheeler market.
# Used as a small, transparent trust signal in the weighted score. This is a
# soft bonus only; it never overrides objective factors like rating/reviews.
TRUSTED_BRANDS = {
    'vega', 'steelbird', 'studds', 'axor', 'ls2', 'smk', 'mt',
    'motul', 'shell', 'castrol', 'liqui moly', 'motorex',
    'bobo', 'tiptop', 'gubbarey', 'autofy',
    'michelin', 'bosch', 'amazon basics', 'amazonbasics',
}

# ===== Category → Buying Guide URL Mapping =====
# Single source of truth for mapping canonical categories to guide slugs.
# Used by templates and generate.py to build correct links.
# ONLY categories with generated guide pages belong here.
CATEGORY_GUIDE_SLUGS: Dict[str, str] = {
    'helmet': 'helmet',
    'phone_mount': 'phone-mount',
    'engine_oil': 'engine-oil',
    'chain_lube': 'chain-lube',
    'tyre_inflator': 'tyre-inflator',
    'chain_cleaner': 'chain-cleaner',
}


def _filter_approved(products: list) -> list:
    """Return products with status 'approved' or 'review' (or no status for legacy compat).

    This is the gatekeeper for the recommendation pipeline.
    'review' products are auto-qualified by the quality pipeline and
    serve as fallback when approved products are scarce.
    Draft, hidden, out_of_stock, and discontinued products are excluded.
    """
    return [p for p in products if p.get('status', 'approved') in ('approved', 'review')]


def preferred_price_range(category: str) -> Optional[Tuple[int, int]]:
    """Return the (min, max) preferred price band for a category, or None."""
    return CATEGORY_PRICE_RANGES.get(normalize_category(category).lower())

# ===== Category → Buying Guide URL Mapping =====
# Single source of truth for mapping accessory categories to buying guide slugs.
# Used by templates and generate.py to build correct links.
# ONLY categories with generated guide pages belong here.
# If a category has no guide page, adding a slug here will create broken links.

CATEGORY_GUIDE_SLUGS: Dict[str, str] = {
    'helmet': 'helmet',
    'phone mount': 'phone-mount',
    'engine oil': 'engine-oil',
    'chain lube': 'chain-lube',
    'tyre inflator': 'tyre-inflator',
    'chain cleaner': 'chain-cleaner',
}


def category_to_guide_url(category: str, base_path: str = '', bike_slug: str = '') -> str:
    """Map a product category to its buying guide URL path.

    Returns a relative URL like 'guides/helmet/index.html'.
    If bike_slug is provided, appends ?bike={slug} for motorcycle-aware filtering.
    If the category has no guide, returns '#' as a safe fallback.
    """
    normalized = normalize_category(category).lower()
    slug = CATEGORY_GUIDE_SLUGS.get(normalized, '')
    if slug:
        url = f'{base_path}guides/{slug}/index.html'
        if bike_slug:
            url += f'?bike={bike_slug}'
        return url
    return '#'


# ===== Product Identity & Deduplication =====

def _product_key(product: dict) -> str:
    """Return a unique identity key for a product.

    Checks (in priority order):
        1. ASIN (most reliable unique identifier)
        2. slug (unique within the catalog)
        3. Normalized title (catches duplicates with different slugs)

    Returns empty string if the product has no identifiable fields.
    """
    asin = (product.get('asin') or '').strip()
    if asin:
        return f'asin:{asin.lower()}'

    slug = (product.get('slug') or '').strip()
    if slug:
        return f'slug:{slug.lower()}'

    title = (product.get('title') or '').strip().lower()
    if title:
        return f'title:{title}'

    return ''


def product_identity_keys(product: dict) -> Set[str]:
    """Return ALL identity keys that make a product unique on a page.

    A product is a duplicate of another if they share ANY of:
        asin, slug, normalized title, amazon/affiliate URL.

    Returning the full set lets a single shared seen-set enforce every
    uniqueness rule at once.
    """
    keys: Set[str] = set()
    asin = (product.get('asin') or '').strip().lower()
    if asin:
        keys.add(f'asin:{asin}')
    slug = (product.get('slug') or '').strip().lower()
    if slug:
        keys.add(f'slug:{slug}')
    title = (product.get('title') or '').strip().lower()
    if title:
        keys.add(f'title:{title}')
    for field in ('amazon_url', 'affiliate_url'):
        url = (product.get(field) or '').strip().lower()
        if url:
            keys.add(f'url:{url}')
    return keys


class PageDedup:
    """One shared seen-products set for an entire rendered page.

    Enforces, across EVERY section of a page (Must Have, Sidebar,
    Maintenance, Related Products, Featured Products, Editor's Picks,
    Homepage, ...):

        * No duplicate ASIN
        * No duplicate slug
        * No duplicate title
        * No duplicate Amazon / affiliate URL

    Usage:
        dedup = PageDedup()
        for p in candidates:
            if dedup.add(p):      # True if newly added (unique so far)
                render(p)
    """

    def __init__(self):
        self._seen: Set[str] = set()

    def seen(self, product: dict) -> bool:
        """Return True if this product collides with anything already added."""
        return bool(product_identity_keys(product) & self._seen)

    def add(self, product: dict) -> bool:
        """Register a product. Return True if it was unique, False if duplicate."""
        keys = product_identity_keys(product)
        if keys & self._seen:
            return False
        self._seen |= keys
        return True

    def filter(self, products: list) -> list:
        """Return only the products not yet seen, registering each kept one."""
        out = []
        for p in products:
            if self.add(p):
                out.append(p)
        return out


def deduplicate_products(products: list) -> list:
    """Remove duplicate products from a list.

    Guarantees:
        - No duplicate ASINs
        - No duplicate slugs
        - No duplicate titles (normalized)

    Keeps the first occurrence of each product.  This is the single
    entry point for deduplication across the entire project.
    """
    seen: Set[str] = set()
    unique: list = []
    for p in products:
        key = _product_key(p)
        if not key:
            unique.append(p)
            continue
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


# ===== 1. Category Normalization =====

def categories_match(cat_a: str, cat_b: str) -> bool:
    """Check whether two category strings refer to the same canonical category.

    Both inputs are normalized to canonical snake_case before comparison.
    """
    return normalize_category(cat_a) == normalize_category(cat_b)


# ===== 2. Compatibility Scoring =====

def compatibility_priority(product: dict, bike: dict) -> int:
    """Return a numeric compatibility priority for *product* against *bike*.

    Lower number = better match:
        1  exact motorcycle slug match
        2  same motorcycle brand  (brand:royal-enfield)
        3  same motorcycle type   (type:cruiser)
        4  universal accessory    (compatible_bikes: ["*"])
        5  empty compatible_bikes (fallback)
        0  not compatible at all
    """
    bike_slug = bike.get('slug', '').lower()
    bike_brand = bike.get('brand', '').lower()
    bike_type = bike.get('type', '').lower()

    compat = product.get('compatible_bikes', [])
    if not compat:
        return 5  # empty = low-priority fallback

    priority = 0
    for entry in compat:
        entry_lower = entry.lower()
        if entry_lower == '*':
            priority = max(priority, 4)
        elif entry_lower.startswith('brand:'):
            if entry_lower[6:] == bike_brand:
                priority = max(priority, 2)
        elif entry_lower.startswith('type:'):
            if entry_lower[5:] == bike_type:
                priority = max(priority, 3)
        elif entry_lower == bike_slug:
            priority = 1
            break  # perfect match, no need to continue

    return priority


def is_compatible_with_bike(product: dict, bike: dict) -> bool:
    """Check if a product is compatible with a specific motorcycle.

    Returns True if the product's compatible_bikes list matches the bike's
    slug, brand, type, or is universal ("*").  Empty compatible_bikes
    returns True as a permissive fallback.
    """
    cp = compatibility_priority(product, bike)
    return cp > 0 or not product.get('compatible_bikes')


def get_compatibility_label(product: dict, bike: dict) -> str:
    """Return a human-readable compatibility status for a product and bike.

    Returns one of:
        'compatible'     - direct match (slug, brand, or type)
        'universal'      - compatible with all bikes
        'incompatible'   - not compatible
    """
    compat = product.get('compatible_bikes', [])
    if not compat:
        return 'compatible'

    bike_slug = bike.get('slug', '').lower()
    bike_brand = bike.get('brand', '').lower()
    bike_type = bike.get('type', '').lower()

    for entry in compat:
        entry_lower = entry.lower()
        if entry_lower == '*':
            return 'universal'
        if entry_lower.startswith('brand:') and entry_lower[6:] == bike_brand:
            return 'compatible'
        if entry_lower.startswith('type:') and entry_lower[5:] == bike_type:
            return 'compatible'
        if entry_lower == bike_slug:
            return 'compatible'

    return 'incompatible'


def get_fitment_details(product: dict, bike: dict) -> dict:
    """Return fitment metadata for a product-bike pair.

    Returns a dict:
        {
            'status': 'compatible' | 'universal' | 'incompatible',
            'fitment_notes': str or None,
            'requires': [str, ...],
        }

    All fields are optional in the product JSON.  Missing fields return
    safe defaults.  Never raises.
    """
    status = get_compatibility_label(product, bike)
    fitment_notes = product.get('fitment_notes') or None
    requires = product.get('requires') or []

    if status == 'incompatible':
        return {'status': status, 'fitment_notes': None, 'requires': []}

    return {'status': status, 'fitment_notes': fitment_notes, 'requires': list(requires)}


# ===== 3. Product Ranking / Scoring =====

def ranking_score(product: dict, bike: Optional[dict] = None) -> float:
    """Compute a composite ranking score for a product.

    Higher = better.  Factors (in descending weight):

        1. Compatibility     (if bike is provided)
        2. Editorial signal  (0-1, real review content only; 0 if none)
        3. User rating       (0-5 scale, normalized to 0-10)
        4. Number of reviews (log-scaled)
        5. Price value       (lower price = better, with diminishing returns)
        6. Popularity        (reviews * rating as a proxy)

    A product with no bike context skips the compatibility factor and
    is scored purely on its intrinsic merits.
    """
    score = 0.0

    # --- Compatibility (weight: 30%) ---
    if bike is not None:
        cp = compatibility_priority(product, bike)
        if cp == 0:
            return -1.0  # incompatible, exclude entirely
        # Invert: priority 1 -> 5 points, priority 5 -> 1 point
        score += (6 - cp) * 3.0

    # --- Editorial signal (weight: 25%) ---
    # Derived from real editorial review content; 0 when no review exists.
    editor = editorial_signal(product)
    score += editor * 25.0

    # --- User rating (weight: 15%) ---
    rating = product.get('rating', 0)
    score += rating * 2.0  # max 5.0 * 2.0 = 10.0

    # --- Reviews (weight: 15%, log-scaled) ---
    reviews = int(product.get('reviews', 0))
    if reviews > 0:
        score += math.log10(reviews) * 3.0  # 1000 reviews -> 9.0

    # --- Price value (weight: 10%) ---
    price = product.get('price', 0)
    if price > 0:
        # Cheaper products get a small bonus; cap at 5 points
        price_score = min(5.0, 5000.0 / max(price, 1))
        score += price_score

    # --- Popularity (weight: 5%) ---
    popularity = min(5.0, (reviews * rating) / 5000.0)
    score += popularity

    return round(score, 2)


# ===== 3b. Weighted Recommendation Score =====

def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def value_for_money(product: dict) -> float:
    """Return a 0-1 value-for-money signal.

    Combines quality (rating + editor rating) against price, normalized so
    cheaper high-rated products score higher. Deterministic and bounded.
    """
    price = _as_float(product.get('price', 0))
    if price <= 0:
        return 0.0
    rating = _as_float(product.get('rating', 0))                # 0-5
    editor = editorial_signal(product) * 5.0                    # 0-1 -> 0-5
    quality = (rating + editor) / 2.0                           # 0-5
    # Price in thousands; higher price divides down the ratio.
    ratio = quality / max(price / 1000.0, 0.1)
    return min(1.0, ratio / 10.0)


def editorial_signal(product: dict) -> float:
    """Return a 0-1 editorial quality signal derived from REAL data.

    We never fabricate a numeric editorial score. Instead:
      * If a genuine editorial review exists (pros/cons/verdict or a stored
        editorial verdict label), the signal reflects that judgment.
      * If no editorial review exists, this returns 0.0 so the product is
        ranked purely on customer rating / reviews / value — it is NOT
        penalized for lacking an editorial opinion, and NOT rewarded with an
        invented number.

    The signal can never exceed the level implied by the Amazon rating, so it
    can never contradict the customer score (trust preservation).
    """
    rating = _as_float(product.get('rating', 0))  # 0-5
    rating_signal = min(1.0, rating / 5.0)

    has_review = bool(
        product.get('pros') or product.get('cons')
        or product.get('verdict') or product.get('editorial_notes')
        or product.get('editorial_verdict')
    )
    if not has_review:
        return 0.0

    label = (product.get('editorial_verdict') or '').lower()
    label_signal = {
        'excellent': 1.0,
        'best_value': 1.0,
        'premium_pick': 0.95,
        'very_good': 0.85,
        'budget_pick': 0.8,
        'good': 0.65,
    }.get(label, 0.85)

    # Trust guard: editorial signal may not exceed what the rating implies.
    return min(label_signal, rating_signal)


def price_fit_score(product: dict, category: Optional[str] = None) -> float:
    """Return a 0-1 score for how well a product's price fits its category band.

    * Inside the preferred band              -> 1.0
    * Below the band (cheaper)               -> 0.85 (good for a budget pick)
    * Above the band                         -> decays toward 0 as it gets
                                                more expensive.

    This is what stops the engine recommending unusually expensive products
    unless they clearly outperform via other factors.
    """
    cat = category or product.get('category', '')
    band = preferred_price_range(cat)
    price = _as_float(product.get('price', 0))
    if not band or price <= 0:
        return 0.5  # neutral when we have no reference
    low, high = band
    if low <= price <= high:
        return 1.0
    if price < low:
        return 0.85
    # Above the band: linear decay, hitting ~0 at 3x the upper bound.
    overshoot = (price - high) / max(high * 2.0, 1.0)
    return max(0.0, 1.0 - overshoot)


# Weights for the composite recommendation score. Sum is documented, not
# enforced, so individual factors can be tuned independently.
_SCORE_WEIGHTS = {
    'rating': 22.0,        # user rating quality
    'reviews': 16.0,       # social proof (log scaled)
    'bestseller': 6.0,     # Amazon Bestseller badge
    'amazon_choice': 6.0,  # Amazon's Choice badge
    'price_fit': 14.0,     # fits category preferred band
    'value': 12.0,         # value for money
    'discount': 8.0,       # active discount
    'brand_trust': 6.0,    # established brand
    'editor': 10.0,        # editorial rating
}


def weighted_score(product: dict, category: Optional[str] = None) -> float:
    """Composite recommendation score. Higher = better.

    Deterministic weighted blend of:
        rating, review_count, bestseller badge, Amazon's Choice badge, price,
        discount, value for money, category preferred price, brand trust,
        editorial rating.

    Never uses fuzzy matching or randomness, so results are stable across
    builds even with tens of thousands of products.
    """
    w = _SCORE_WEIGHTS
    score = 0.0

    rating = _as_float(product.get('rating', 0))          # 0-5
    score += w['rating'] * (rating / 5.0)

    reviews = _as_int(product.get('review_count', product.get('reviews', 0)))
    if reviews > 0:
        # log10: 10 -> 1, 1000 -> 3, 100000 -> 5; normalize to ~0-1
        score += w['reviews'] * min(1.0, math.log10(reviews + 1) / 5.0)

    if product.get('bestseller'):
        score += w['bestseller']
    if product.get('amazon_choice'):
        score += w['amazon_choice']

    score += w['price_fit'] * price_fit_score(product, category)
    score += w['value'] * value_for_money(product)

    discount = _as_float(product.get('discount', 0))
    if discount > 0:
        score += w['discount'] * min(1.0, discount / 50.0)

    brand = (product.get('brand') or '').strip().lower()
    if brand in TRUSTED_BRANDS:
        score += w['brand_trust']

    editor = editorial_signal(product)                     # 0-1 (real only)
    score += w['editor'] * editor

    return round(score, 3)


# ===== 3c. Intelligent Recommendation Score =====

# Factor weights for the composite recommendation score.  These control how
# much each dimension influences the final ranking.  Weights are documented
# but not enforced to sum to 100; they are tuning knobs.
_REC_WEIGHTS = {
    'editor':      25.0,   # editorial quality assessment
    'value':       20.0,   # value for money (quality / price)
    'rating':      15.0,   # customer rating (0-5)
    'reviews':     15.0,   # social proof (log-scaled review count)
    'compatibility': 15.0, # fit for the selected bike
    'brand':        5.0,   # trusted brand bonus
    'availability': 5.0,   # in-stock / easy to buy
}


def _availability_score(product: dict) -> float:
    """Return a 0-1 score for product availability.

    'In Stock' / 'Available' -> 1.0
    'Currently unavailable' / empty -> 0.0
    """
    avail = (product.get('availability') or '').strip().lower()
    if avail in ('in stock', 'available', 'in_stock'):
        return 1.0
    if avail in ('currently unavailable', 'out of stock', 'unavailable'):
        return 0.0
    # Unknown availability: assume available (benefit of the doubt)
    return 0.5


def recommendation_score(product: dict, category: Optional[str] = None,
                         bike: Optional[dict] = None) -> float:
    """Composite recommendation score.  Higher = better.

    Delegates to the central, configurable scoring engine (scoring.py) so
    weights stay in one place and can be tuned per category. Returns the
    normalised 0-1 blended score used for badge assignment and ranking.

    NOTE: this numeric score is internal only and must never be rendered to
    end users; only the derived badge / best_for / pros / price / rating may
    be displayed.
        7. Availability       (0-1)

    This is the score used for badge assignment (Editor's Choice, etc.).
    It is distinct from weighted_score() which is used for list ranking.
    """
    from scoring import compute_recommendation_score, is_editorial_override

    # Hard-exclude incompatible products when a bike is selected.
    if bike is not None:
        cp = compatibility_priority(product, bike)
        if cp == 0:
            return -1.0

    result = compute_recommendation_score(product, category, bike)
    # Editorial overrides may not be denied a badge just because their
    # automatic score is low; return a high floor so they still rank.
    if result["overridden"]:
        return 1.0
    return result["score"]


# ===== 3d. Badge Assignment =====

_BADGE_ICONS = {
    'editors_choice': '&#127942;',   # trophy
    'best_value':     '&#128176;',   # money bag
    'premium_pick':   '&#11088;',    # star
    'most_popular':   '&#128293;',   # fire
}

_BADGE_LABELS = {
    'editors_choice': "Editor's Choice",
    'best_value':     'Best Value',
    'premium_pick':   'Premium Pick',
    'most_popular':   'Most Popular',
}


def _generate_badge_reason(product: dict, badge_type: str,
                           category: Optional[str] = None) -> str:
    """Generate a short 1-liner explaining why a product got this badge."""
    title = product.get('title', 'This product')
    price = _as_int(product.get('price', 0))
    rating = _as_float(product.get('rating', 0))
    editor = _as_float(product.get('editor_rating', 0))
    reviews = _as_int(product.get('review_count', product.get('reviews', 0)))
    brand = product.get('brand', '')
    vfm = value_for_money(product)

    if badge_type == 'editors_choice':
        parts = ['Our top recommendation']
        if rating >= 4.0:
            parts.append(f'{rating}/5 user rating')
        if vfm > 0.3:
            parts.append('excellent value')
        return ', '.join(parts) + f' at \u20b9{price}'

    if badge_type == 'best_value':
        parts = ['Best quality-to-price ratio']
        if rating >= 4.0:
            parts.append(f'{rating}/5 user rating')
        parts.append(f'at just \u20b9{price}')
        return ', '.join(parts)

    if badge_type == 'premium_pick':
        parts = [f'Premium choice at \u20b9{price}']
        if rating >= 4.0:
            parts.append(f'{rating}/5 user rating')
        verdict = (product.get('editorial_verdict') or '').lower()
        if verdict in ('excellent', 'premium_pick', 'best_value'):
            parts.append('editor-approved')
        return ', '.join(parts)

    if badge_type == 'most_popular':
        parts = [f'Most reviewed with {reviews:,} reviews']
        if rating >= 4.0:
            parts.append(f'{rating}/5 user rating')
        return ', '.join(parts)

    return ''


def assign_badges(products: list, category: Optional[str] = None,
                  bike: Optional[dict] = None) -> dict:
    """Assign recommendation badges to products.

    Returns a dict keyed by product slug:
        {
            'product-slug': {
                'badge': 'Editor\'s Choice',
                'badge_type': 'editors_choice',
                'icon': '&#127942;',
                'reason': 'Highest recommendation with 9/10 editor rating...'
            },
            ...
        }

    Rules:
        - Only compatible products receive badges (when bike is provided).
        - Each product gets at most one badge.
        - Exactly 4 badges are assigned (if enough compatible products exist).
        - Badge priority: Editor's Choice > Best Value > Most Popular > Premium Pick.
    """
    if not products:
        return {}

    # Filter to compatible products only
    if bike is not None:
        compatible = []
        for p in products:
            cp = compatibility_priority(p, bike)
            if cp > 0:
                compatible.append(p)
    else:
        compatible = list(products)

    if not compatible:
        return {}

    # Score each compatible product
    scored = []
    for p in compatible:
        slug = p.get('slug', '')
        if not slug:
            continue
        score = recommendation_score(p, category, bike)
        if score < 0:
            continue
        scored.append((score, p))

    if not scored:
        return {}

    scored.sort(key=lambda x: x[0], reverse=True)

    # Track assigned slugs to avoid duplicates
    assigned = {}
    used_slugs = set()

    def _assign(badge_type: str, candidates: list) -> bool:
        for _, p in candidates:
            slug = p.get('slug', '')
            if slug and slug not in used_slugs:
                from scoring import compute_recommendation_score
                reasons = compute_recommendation_score(p, category, bike).get('reasons', [])
                assigned[slug] = {
                    'badge': _BADGE_LABELS[badge_type],
                    'badge_type': badge_type,
                    'icon': _BADGE_ICONS[badge_type],
                    'reason': _generate_badge_reason(p, badge_type, category),
                    'reasons': reasons,
                }
                used_slugs.add(slug)
                return True
        return False

    # 1. Editor's Choice: manual editorial picks win unconditionally,
    #    otherwise the highest composite score. Guarantees req #4.
    override_products = [
        (s, p) for s, p in scored
        if p.get('editors_choice') or _as_int(p.get('override_rank', 0)) > 0
    ]
    override_products.sort(
        key=lambda x: (
            not bool(x[1].get('editors_choice')),
            _as_int(x[1].get('override_rank', 0)) or 0,
            x[0],
        )
    )
    if not _assign('editors_choice', override_products):
        _assign('editors_choice', scored)

    # 2. Best Value: best value_for_money among remaining
    remaining = [(s, p) for s, p in scored if p.get('slug') not in used_slugs]
    by_value = sorted(remaining, key=lambda x: value_for_money(x[1]), reverse=True)
    _assign('best_value', by_value)

    # 3. Most Popular: highest review count among remaining
    remaining = [(s, p) for s, p in scored if p.get('slug') not in used_slugs]
    by_popularity = sorted(
        remaining,
        key=lambda x: _as_int(x[1].get('review_count', x[1].get('reviews', 0))),
        reverse=True,
    )
    _assign('most_popular', by_popularity)

    # 4. Premium Pick: highest price with good rating (>= 4.0) among remaining
    remaining = [(s, p) for s, p in scored if p.get('slug') not in used_slugs]
    premium = [x for x in remaining if _as_float(x[1].get('rating', 0)) >= 4.0]
    if not premium:
        premium = remaining
    by_price = sorted(premium, key=lambda x: _as_float(x[1].get('price', 0)), reverse=True)
    _assign('premium_pick', by_price)

    return assigned


# ===== 4. Brand Diversity =====

def enforce_brand_diversity(products: list, max_per_brand: int = 2) -> list:
    """Limit the number of products from any single brand.

    Walks the (already sorted) list and keeps at most *max_per_brand*
    products from each brand.  This ensures the user sees meaningful
    choices rather than a wall of BOBO phone mounts.
    """
    brand_counts: Dict[str, int] = defaultdict(int)
    diversified: list = []
    for p in products:
        brand = p.get('brand', '')
        if brand_counts[brand] < max_per_brand:
            diversified.append(p)
            brand_counts[brand] += 1
    return diversified


def brand_diversity_score(products: list) -> float:
    """Return a 0-1 diversity score. 1.0 = all different brands."""
    if not products:
        return 0.0
    brands = {p.get('brand', '') for p in products}
    return len(brands) / len(products)


# ===== 5. Product Count Management =====

MIN_PRODUCTS = 3
PREFERRED_PRODUCTS = 5
MAX_PRODUCTS = 8


def select_product_count(matched: int) -> int:
    """Decide how many products to display based on availability.

    Returns:
        MIN_PRODUCTS (3) if 3-4 products match
        PREFERRED_PRODUCTS (5) if 5-7 products match
        MAX_PRODUCTS (8) if 8+ products match
        matched if fewer than 3
    """
    if matched <= MIN_PRODUCTS:
        return matched
    if matched <= PREFERRED_PRODUCTS:
        return PREFERRED_PRODUCTS
    return min(matched, MAX_PRODUCTS)


# ===== 6. Product Search (Full-Text) =====

def find_products_by_category(
    products: list,
    category: str,
    subcategory: Optional[str] = None,
) -> list:
    """Find ALL products matching a category, optionally filtered by subcategory.

    Only products with status 'approved' (or no status for legacy compat)
    are included. Draft, hidden, out_of_stock, and discontinued products
    are excluded.

    Search order:
        1. Exact match on normalized category
        2. Case-insensitive substring match on category
        3. Keyword fallback (category + title + best_for)

    If subcategory is provided, results are further filtered to only
    products whose subcategory matches.

    Returns unsorted list of matching products.
    """
    products = _filter_approved(products)
    normalized = normalize_category(category)

    # 1. Exact normalized category match
    matched = [
        p for p in products
        if normalize_category(p.get('category', '')).lower() == normalized.lower()
    ]

    # 2. Case-insensitive substring on category field (fallback if no exact match)
    if not matched:
        normalized_lower = normalized.lower()
        matched = [
            p for p in products
            if normalized_lower in p.get('category', '').lower()
        ]

    # 3. Keyword fallback: check category, title, and best_for
    if not matched:
        keywords = CATEGORY_KEYWORDS.get(normalized.lower(), [])
        for kw in keywords:
            matched = [
                p for p in products
                if kw in p.get('category', '').lower()
                or kw in p.get('title', '').lower()
                or kw in p.get('best_for', '').lower()
            ]
            if matched:
                break

    # 4. Subcategory filter
    if subcategory and matched:
        sub_lower = subcategory.lower()
        sub_filtered = [
            p for p in matched
            if p.get('subcategory', '').lower() == sub_lower
        ]
        # Only use subcategory filter if it produced results
        if sub_filtered:
            matched = sub_filtered

    return deduplicate_products(matched) if matched else []


# ===== 7. Main Recommendation Pipeline =====

# Negative signals indicating the product is a 12V car-only tyre inflator that
# requires a car power socket and is therefore unsuitable for motorcycles.
_TYRE_INFLATOR_CAR_SIGNALS = (
    '12v',
    'cigarette lighter',
    'car tyre inflator',
    'car socket',
    'dc 12v car',
    'car only',
    'for car',
)

# Positive signals indicating the product is portable / battery-powered /
# motorcycle-compatible.
_TYRE_INFLATOR_MOTO_SIGNALS = (
    'rechargeable',
    'battery',
    'battery powered',
    'lithium',
    'portable inflator',
    'cordless',
    'motorcycle',
    'bike inflator',
    'wireless',
)


def is_motorcycle_tyre_inflator(product: dict) -> bool:
    """Return True if a tyre inflator is motorcycle-compatible.

    Motorcycle pages should only recommend portable/rechargeable/battery-powered
    inflators or inflators explicitly compatible with motorcycles. 12V
    cigarette-lighter / car-only inflators that require a car power socket are
    excluded. If a product shows neither strong positive nor negative signals it
    is defaulted to included to avoid over-filtering.
    """
    text = ' '.join(
        str(product.get(field, ''))
        for field in ('title', 'type', 'features', 'best_for')
    ).lower()

    has_car_signal = any(sig in text for sig in _TYRE_INFLATOR_CAR_SIGNALS)
    has_moto_signal = any(sig in text for sig in _TYRE_INFLATOR_MOTO_SIGNALS)

    if has_car_signal and not has_moto_signal:
        return False
    return True


def recommend_products(
    products: list,
    category: str,
    bike: Optional[dict] = None,
    min_count: int = MIN_PRODUCTS,
    preferred_count: int = PREFERRED_PRODUCTS,
    max_count: int = MAX_PRODUCTS,
) -> list:
    """End-to-end product recommendation for a single category.

    Pipeline:
        1. Search all products matching the category (full catalog)
        2. Score each product (compatibility + intrinsic quality)
        3. Filter out incompatible products (score < 0)
        4. Sort by score descending
        5. Enforce brand diversity (max 2 per brand)
        6. Trim to target count

    If fewer than *min_count* products survive, tries fallbacks:
        - Universal products first
        - Then any product in the same category family

    Returns the final curated list, sorted by ranking score.
    """
    # --- Stage 1: Search ---
    candidates = find_products_by_category(products, category)

    if not candidates:
        return []

    # --- Stage 1b: Hard exclusion of 12V car-only tyre inflators ---
    if normalize_category(category).lower() == 'tyre_inflator':
        candidates = [
            p for p in candidates
            if is_motorcycle_tyre_inflator(p)
        ]
        if not candidates:
            return []

    # --- Stage 2: Score ---
    # Weighted intrinsic quality (rating, reviews, badges, price fit, value,
    # discount, brand trust, editorial) is the primary signal. Compatibility is
    # layered on top as a hard filter + priority boost when a bike is provided.
    from scoring import compute_recommendation_score, sort_key_for_ranking

    scored: list = []
    for p in candidates:
        base = weighted_score(p, category)
        if bike is not None:
            cp = compatibility_priority(p, bike)
            if cp == 0:
                continue  # incompatible: exclude entirely
            base += (6 - cp) * 8.0  # priority 1 -> +40, priority 5 -> +8
        precomp = compute_recommendation_score(p, category, bike)
        scored.append((sort_key_for_ranking(p, precomp, category, bike), base, p))

    # --- Stage 3: Sort (editorial overrides first, then by score) ---
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    ranked = [p for _, _, p in scored]

    # --- Stage 4: Brand diversity ---
    diversified = enforce_brand_diversity(ranked, max_per_brand=2)

    # --- Stage 5: Trim to count ---
    target = select_product_count(len(diversified))
    if target < min_count and len(diversified) >= min_count:
        target = min_count
    result = diversified[:target]

    # --- Stage 6: Fallback if too few ---
    if len(result) < min_count and bike:
        # Try universal products (compatible with all bikes)
        universal = find_products_by_category(products, category)
        seen_slugs = {p.get('slug') for p in result}
        for p in universal:
            if p.get('slug') not in seen_slugs:
                compat = p.get('compatible_bikes', [])
                if '*' in [c.lower() for c in compat]:
                    score = ranking_score(p, bike)
                    if score >= 0:
                        result.append(p)
                        seen_slugs.add(p.get('slug'))
                        if len(result) >= min_count:
                            break

    return result


def recommend_for_category(
    products: list,
    category: str,
    bike: Optional[dict] = None,
) -> dict:
    """Recommend products with editorial picks and badge assignments.

    Returns a dict:
        {
            'category': 'Phone Mount',
            'products': [...],         # ranked, diversified list
            'count': 5,
            'editors_choice': {...},   # highest composite score
            'best_value': {...},       # best value-for-money
            'premium_pick': {...},     # highest-priced with good rating
            'most_popular': {...},     # highest review count
            'badge_data': {            # slug -> badge info for template
                'slug': {
                    'badge': "Editor's Choice",
                    'badge_type': 'editors_choice',
                    'icon': '&#127942;',
                    'reason': 'Highest recommendation with 9/10 editor rating...'
                }
            }
        }

    All picks are guaranteed to be unique products (no slug/title/ASIN
    duplicates across picks).  Badge data includes a short reason string
    explaining why each product was recommended.
    """
    ranked = recommend_products(products, category, bike)

    result = {
        'category': normalize_category(category),
        'products': ranked,
        'count': len(ranked),
        'editors_choice': None,
        'best_value': None,
        'premium_pick': None,
        'most_popular': None,
        'badge_data': {},
    }

    if len(ranked) == 0:
        return result

    # Assign badges using the composite recommendation score.
    # This handles dedup internally (each product gets at most one badge).
    badge_data = assign_badges(ranked, category, bike)
    result['badge_data'] = badge_data

    # Also set named picks for backward compatibility.
    # These are the actual product dicts for each badge type.
    for slug, info in badge_data.items():
        badge_type = info.get('badge_type', '')
        for p in ranked:
            if p.get('slug') == slug:
                if badge_type == 'editors_choice':
                    result['editors_choice'] = p
                elif badge_type == 'best_value':
                    result['best_value'] = p
                elif badge_type == 'premium_pick':
                    result['premium_pick'] = p
                elif badge_type == 'most_popular':
                    result['most_popular'] = p
                break

    return result


# ===== 8. Sidebar Recommendations =====

def _infer_categories_from_article(article: dict) -> List[str]:
    """Infer product categories from article metadata.

    Uses tags and title to find relevant product categories.
    Returns a list of canonical category names.
    """
    tag_to_category = {
        'helmet': 'Helmet',
        'helmets': 'Helmet',
        'phone-mount': 'Phone Mount',
        'phone-holder': 'Phone Mount',
        'mobile-mount': 'Phone Mount',
        'navigation': 'Phone Mount',
        'crash-guard': 'Crash Guard',
        'engine-guard': 'Crash Guard',
        'protection': 'Crash Guard',
        'engine-oil': 'Engine Oil',
        'oil': 'Engine Oil',
        'maintenance': 'Engine Oil',
        'chain-lube': 'Chain Lube',
        'chain': 'Chain Lube',
        'bike-cover': 'Bike Cover',
        'cover': 'Bike Cover',
        'gloves': 'Gloves',
        'riding-gloves': 'Gloves',
        'jackets': 'Jackets',
        'riding-jacket': 'Jackets',
        'riding-jackets': 'Jackets',
        'tank-bag': 'Tank Bag',
        'saddle-bag': 'Saddle Bag',
        'tail-bag': 'Tail Bag',
        'tyre-inflator': 'Tyre Inflator',
        'tyre': 'Tyre Inflator',
        'tire': 'Tyre Inflator',
        'touring': 'Tank Bag',
        'washing': 'Cleaning Kit',
        'wash': 'Cleaning Kit',
        'cleaning': 'Cleaning Kit',
        'clean': 'Cleaning Kit',
        'rain': 'Rain Gear',
        'monsoon': 'Rain Gear',
        'knee-guard': 'Knee Guard',
        'knee': 'Knee Guard',
        'buying-guide': None,
        'review': None,
        'tips': None,
        'safety': None,
        'riding': None,
        'india': None,
    }

    categories = []
    seen = set()

    # Check tags first
    for tag in article.get('tags', []):
        tag_lower = tag.lower().strip()
        cat = tag_to_category.get(tag_lower)
        if cat and cat not in seen:
            categories.append(cat)
            seen.add(cat)

    # Also check title for category hints
    title_lower = article.get('title', '').lower()
    for keyword, cat in tag_to_category.items():
        if cat and cat not in seen and keyword in title_lower:
            categories.append(cat)
            seen.add(cat)

    # Fallback: check slug for category hints (works even without YAML parsing)
    slug_lower = article.get('slug', '').lower()
    for keyword, cat in tag_to_category.items():
        if cat and cat not in seen and keyword in slug_lower:
            categories.append(cat)
            seen.add(cat)

    # Final fallback: check body text for category keywords
    if not categories:
        body_lower = article.get('body', '').lower()[:2000]
        for keyword, cat in tag_to_category.items():
            if cat and cat not in seen and keyword in body_lower:
                categories.append(cat)
                seen.add(cat)
                if len(categories) >= 3:
                    break

    return categories


def recommend_sidebar_products(
    products: list,
    bike: Optional[dict] = None,
    article: Optional[dict] = None,
    product: Optional[dict] = None,
    max_products: int = 5,
) -> list:
    """Recommend products for sidebar display.

    Uses the SAME engine as main content (find_products_by_category +
    ranking_score + enforce_brand_diversity).  There is only one product
    recommendation engine in the project.

    Context:
        motorcycle pages  -> pass bike=...
        article pages     -> pass article=...
        product pages     -> pass product=...

    Returns a list of dicts:
        [{'product': {...}, 'category': str, 'reason': str}, ...]

    Returns empty list if no suitable products found — the sidebar widget
    should be hidden completely in that case.
    """
    candidates = []
    products = _filter_approved(products)

    if bike is not None:
        # Motorcycle page: filter to compatible products, best per category
        for p in products:
            cp = compatibility_priority(p, bike)
            if cp > 0:
                candidates.append(p)

        # Pick best product per category, sorted by ranking_score
        best_by_cat: Dict[str, dict] = {}
        for p in candidates:
            cat = normalize_category(p.get('category', ''))
            if cat not in best_by_cat or ranking_score(p, bike) > ranking_score(best_by_cat[cat], bike):
                best_by_cat[cat] = p

        ranked = sorted(best_by_cat.values(), key=lambda p: ranking_score(p, bike), reverse=True)
        diversified = enforce_brand_diversity(ranked, max_per_brand=2)

        return [
            {
                'product': p,
                'category': normalize_category(p.get('category', '')),
                'reason': 'Best compatible product for your motorcycle',
            }
            for p in diversified[:max_products]
        ]

    elif article is not None:
        # Article page: infer categories from article metadata
        cats = _infer_categories_from_article(article)
        if not cats:
            return []

        seen_slugs = set()
        results = []
        for cat in cats:
            matched = find_products_by_category(products, cat)
            if not matched:
                continue
            matched.sort(key=lambda p: ranking_score(p), reverse=True)
            diverse = enforce_brand_diversity(matched, max_per_brand=1)
            for p in diverse:
                if p.get('slug') not in seen_slugs:
                    results.append({
                        'product': p,
                        'category': cat,
                        'reason': f'Recommended for {cat.lower()}',
                    })
                    seen_slugs.add(p.get('slug'))
                    if len(results) >= max_products:
                        return results

        return results

    elif product is not None:
        # Product page: same category products
        cat = normalize_category(product.get('category', ''))
        matched = find_products_by_category(products, cat)
        matched = [p for p in matched if p.get('slug') != product.get('slug')]
        matched.sort(key=lambda p: ranking_score(p), reverse=True)
        diversified = enforce_brand_diversity(matched, max_per_brand=2)

        return [
            {
                'product': p,
                'category': cat,
                'reason': f'Similar {cat.lower()} product',
            }
            for p in diversified[:max_products]
        ]

    return []


def filter_compatible_products(products: list, bike: dict) -> list:
    """Return all compatible products for a motorcycle, sorted by ranking.

    Only approved products are included.

    Returns a list of products with an added 'normalized_category' field.
    Products are sorted by compatibility priority first, then ranking score.
    This is the single entry point for motorcycle-specific product filtering.
    """
    products = _filter_approved(products)
    matched = []
    for product in products:
        cp = compatibility_priority(product, bike)
        if cp > 0:
            product_copy = dict(product)
            product_copy['normalized_category'] = normalize_category(
                product.get('category', '')
            )
            matched.append((cp, product_copy))

    matched.sort(key=lambda x: (x[0], -ranking_score(x[1], bike)))
    return [item[1] for item in matched]


def group_products_by_category(products: list) -> Dict[str, list]:
    """Group products by their normalized category name.

    Returns a dict mapping canonical category name to list of products.
    """
    categories: Dict[str, list] = defaultdict(list)
    for product in products:
        cat = normalize_category(product.get('category', 'Other'))
        categories[cat].append(product)
    return dict(categories)


def count_products_by_category(products: list, category: str) -> int:
    """Count how many products match a given category (normalized)."""
    return len(find_products_by_category(products, category))


def best_per_category(
    products: list,
    categories: list,
    bike: Optional[dict] = None,
) -> list:
    """Return the single best product for each requested category.

    Only approved products are considered.

    Iterates *categories* in order, finds matching products via
    find_products_by_category, ranks them, and returns the top one per
    category. Categories with no matching products are skipped.
    """
    products = _filter_approved(products)
    results = []
    seen_cats = set()
    for cat in categories:
        normalized = normalize_category(cat).lower()
        if normalized in seen_cats:
            continue
        matched = find_products_by_category(products, cat)
        if not matched:
            continue
        if normalize_category(cat).lower() == 'tyre_inflator':
            matched = [p for p in matched if is_motorcycle_tyre_inflator(p)]
            if not matched:
                continue
        scored = [(ranking_score(p, bike), p) for p in matched]
        scored.sort(key=lambda x: x[0], reverse=True)
        results.append(scored[0][1])
        seen_cats.add(normalized)
    return results


# ===== 9. Validation & Reporting =====

def validate_category_products(
    products: list,
    categories: Optional[list] = None,
) -> dict:
    """Validate product distribution across categories.

    Returns a dict with:
        'categories': {category: count}
        'empty': [categories with 0 products]
        'understocked': [categories with < 3 products]
        'report': formatted string for console output
    """
    if categories is None:
        categories = sorted(VALID_CATEGORIES)

    cat_counts: Dict[str, int] = defaultdict(int)
    for p in products:
        cat = normalize_category(p.get('category', '')).lower()
        cat_counts[cat] += 1

    empty = []
    understocked = []
    report_lines = []

    for cat in sorted(categories):
        cat_lower = cat.lower()
        count = cat_counts.get(cat_lower, 0)
        label = cat.ljust(20)
        if count == 0:
            report_lines.append(f'    ! {label} 0 products  *** EMPTY ***')
            empty.append(cat)
        elif count < MIN_PRODUCTS:
            report_lines.append(f'    ~ {label} {count} products (below minimum {MIN_PRODUCTS})')
            understocked.append(cat)
        else:
            report_lines.append(f'    * {label} {count} products')

    report = '\n'.join(report_lines)
    return {
        'categories': dict(cat_counts),
        'empty': empty,
        'understocked': understocked,
        'report': report,
    }


def validate_motorcycle_products(
    motorcycle: dict,
    products: list,
    target_categories: Optional[list] = None,
) -> dict:
    """Validate product availability for a specific motorcycle.

    Returns a dict:
        'matched': total matched products
        'categories_found': set of category names
        'categories_missing': categories with 0 products
        'category_counts': {category: count}
    """
    if target_categories is None:
        target_categories = list(VALID_CATEGORIES)

    cat_counts: Dict[str, int] = defaultdict(int)

    for p in products:
        cp = compatibility_priority(p, motorcycle)
        if cp > 0:
            cat = normalize_category(p.get('category', ''))
            cat_counts[cat] += 1

    categories_found = set(cat_counts.keys())
    categories_missing = [
        c for c in target_categories
        if normalize_category(c) not in categories_found
    ]

    return {
        'matched': sum(cat_counts.values()),
        'categories_found': categories_found,
        'categories_missing': categories_missing,
        'category_counts': dict(cat_counts),
    }


# ===== 10. Motorcycle Page Recommendation =====

# Category groups for motorcycle ownership pages.
# Each group contains categories with their display names, product limits,
# and optional subcategory filters.
# When 'subcategories' is specified, only products matching those subcategories
# are included in recommendations for that category.
MOTORCYCLE_CATEGORY_GROUPS: List[Dict] = [
    {
        'name': 'Safety',
        'categories': [
            {
                'name': 'helmet', 'display': 'Helmets', 'display_plural': 'Helmets',
                'limit': 6,
                'subcategories': ['full_face', 'modular', 'open_face'],
            },
            {
                'name': 'riding_gear', 'display': 'Riding Gloves', 'display_plural': 'Riding Gloves',
                'limit': 4,
                'subcategories': ['gloves'],
            },
            {
                'name': 'riding_gear', 'display': 'Riding Jackets', 'display_plural': 'Riding Jackets',
                'limit': 4,
                'subcategories': ['jacket'],
            },
        ],
    },
    {
        'name': 'Maintenance',
        'categories': [
            {
                'name': 'chain_lube', 'display': 'Chain Lube', 'display_plural': 'Chain Lubes',
                'limit': 4,
            },
            {
                'name': 'chain_cleaner', 'display': 'Chain Cleaner', 'display_plural': 'Chain Cleaners',
                'limit': 4,
            },
            {
                'name': 'engine_oil', 'display': 'Engine Oil', 'display_plural': 'Engine Oils',
                'limit': 4,
            },
        ],
    },
    {
        'name': 'Daily Riding',
        'categories': [
            {
                'name': 'phone_mount', 'display': 'Phone Mounts', 'display_plural': 'Phone Mounts',
                'limit': 4,
            },
            {
                'name': 'usb_charger', 'display': 'USB Chargers', 'display_plural': 'USB Chargers',
                'limit': 4,
            },
            {
                'name': 'tyre_inflator', 'display': 'Tyre Inflators', 'display_plural': 'Tyre Inflators',
                'limit': 4,
            },
        ],
    },
    {
        'name': 'Touring',
        'categories': [
            {
                'name': 'tank_bag', 'display': 'Tank Bags', 'display_plural': 'Tank Bags',
                'limit': 4,
            },
            {
                'name': 'saddle_bag', 'display': 'Saddle Bags', 'display_plural': 'Saddle Bags',
                'limit': 4,
            },
            {
                'name': 'bike_cover', 'display': 'Bike Covers', 'display_plural': 'Bike Covers',
                'limit': 4,
            },
        ],
    },
    {
        'name': 'Security',
        'categories': [
            {
                'name': 'disc_lock', 'display': 'Disc Locks', 'display_plural': 'Disc Locks',
                'limit': 4,
            },
            {
                'name': 'chain_lock', 'display': 'Chain Locks', 'display_plural': 'Chain Locks',
                'limit': 4,
            },
        ],
    },
]


def _motorcycle_score(product: dict, bike: dict) -> int:
    """Score a product for motorcycle page recommendation.

    Scoring weights (per specification):
        +100  Explicit motorcycle compatibility (specific slug or brand/type match)
        +50   Universal motorcycle product (compatible_bikes contains '*')
        +30   Editor's Choice (editorial score >= 75/100 or >= 7.5/10)
        +20   Best Seller (review count >= 500)
        +10   Rating above 4.3
        +5    Large review count (>= 1000)

    Returns an integer score. Higher = more relevant.
    """
    score = 0

    # --- Compatibility ---
    cp = compatibility_priority(product, bike)
    if cp == 1:
        score += 100
    elif cp == 2:
        score += 80
    elif cp == 3:
        score += 60
    elif cp == 4:
        score += 50
    elif cp == 5:
        score += 40
    else:
        return 0

    # --- Editor's Choice ---
    # Driven by a genuine editorial verdict + strong customer rating, never a
    # fabricated numeric score.
    verdict = (product.get('editorial_verdict') or '').lower()
    rating = _as_float(product.get('rating', 0))
    is_editor = verdict in ('excellent', 'best_value', 'premium_pick') and rating >= 4.3
    if is_editor:
        score += 30

    # --- Best Seller ---
    reviews = product.get('review_count', 0) or product.get('reviews', 0) or 0
    if reviews >= 500:
        score += 20

    # --- Rating above 4.3 ---
    rating = product.get('rating', 0) or 0
    if rating > 4.3:
        score += 10

    # --- Large review count ---
    if reviews >= 1000:
        score += 5

    return score


def recommend_for_motorcycle(
    products: list,
    bike: dict,
    editorial: Optional[dict] = None,
) -> List[Dict]:
    """Recommend products for all categories on a motorcycle ownership page.

    Returns a flat list of category items grouped by purpose:
        Safety Essentials (Helmet, Gloves, Jackets)
        Maintenance Essentials (Chain Lube, Chain Cleaner, Engine Oil)
        Daily Riding (Phone Mount, USB Charger, Tyre Inflator)
        Touring (Tank Bag, Saddle Bag, Bike Cover)
        Security (Disc Lock, Chain Lock)

    Each item contains:
        category, display, slug, group, products (0-6), count, description
        category_total: total products in this category (for "See all X (N)" links)

    Products within each category are assigned badges:
        editors_choice, best_value, premium_pick, budget_pick, most_reviewed

    The same product will never appear in two categories.
    If no compatible products exist for a category, universal products are used.
    If no products exist at all, the category is included with an empty list.

    Returns a list of ~15 items (one per category).
    """
    must_have_descriptions = {}
    if editorial:
        must_have_descriptions = editorial.get('must_have_descriptions', {})

    seen_keys: Set[str] = set()
    result: List[Dict] = []

    for group in MOTORCYCLE_CATEGORY_GROUPS:
        for cat_config in group['categories']:
            cat_name = cat_config['name']
            limit = cat_config['limit']
            subcategories = cat_config.get('subcategories', [])

            # Find all approved products in this category, optionally filtered by subcategory
            if subcategories:
                candidates = []
                for sub in subcategories:
                    found = find_products_by_category(products, cat_name, subcategory=sub)
                    if not found:
                        found = find_products_by_category(products, sub)
                    candidates.extend(found)
                candidates = deduplicate_products(candidates)
            else:
                candidates = find_products_by_category(products, cat_name)

            # Total count for "See all X (N)" link
            category_total = len(candidates)

            # Score each product, excluding already-seen products
            scored = []
            for p in candidates:
                key = _product_key(p)
                if key in seen_keys:
                    continue
                s = _motorcycle_score(p, bike)
                if s > 0:
                    scored.append((s, p))

            # Sort by score descending
            scored.sort(key=lambda x: x[0], reverse=True)

            # Select top N
            selected = []
            for s, p in scored[:limit]:
                selected.append(p)
                seen_keys.add(_product_key(p))

            # Fallback: if no scored products, try any compatible/universal product
            if not selected:
                for p in candidates:
                    key = _product_key(p)
                    if key in seen_keys:
                        continue
                    cp = compatibility_priority(p, bike)
                    if cp > 0:
                        selected.append(p)
                        seen_keys.add(key)
                        if len(selected) >= limit:
                            break

            # Second fallback: any product in category not yet used
            if not selected:
                for p in candidates:
                    key = _product_key(p)
                    if key in seen_keys:
                        continue
                    selected.append(p)
                    seen_keys.add(key)
                    if len(selected) >= limit:
                        break

            # Assign badges to selected products
            _assign_category_badges(selected)

            # Build description
            desc = must_have_descriptions.get(
                cat_name,
                f'Essential {category_display(cat_name).lower()} for your {bike.get("model", "motorcycle")}.',
            )

            result.append({
                'category': cat_name,
                'display': cat_config['display'],
                'display_plural': cat_config.get('display_plural', cat_config['display'] + 's'),
                'slug': category_slug(cat_name),
                'group': group['name'],
                'products': selected,
                'count': len(selected),
                'category_total': category_total,
                'description': desc,
            })

    return result


def _assign_category_badges(products: list) -> None:
    """Assign shopping badges to products within a category.

    Modifies each product dict in-place, adding a 'badge' field.
    Badge types:
        editors_choice  - highest recommendation score (top product)
        best_value      - best price-to-rating ratio
        premium_pick    - highest priced with good rating
        budget_pick     - lowest price with acceptable rating
        most_reviewed   - highest review count
    """
    if not products:
        return

    # Reset badges
    for p in products:
        p['badge'] = None
        p['badge_label'] = None

    if len(products) == 1:
        products[0]['badge'] = 'editors_choice'
        products[0]['badge_label'] = "Editor's Choice"
        return

    # Editors Choice: first product (already ranked by score)
    products[0]['badge'] = 'editors_choice'
    products[0]['badge_label'] = "Editor's Choice"

    # Most Reviewed: highest review_count
    reviewed = [p for p in products if p.get('review_count', 0) > 0]
    if reviewed:
        most_rev = max(reviewed, key=lambda p: p.get('review_count', 0))
        if most_rev is not products[0]:
            most_rev['badge'] = 'most_reviewed'
            most_rev['badge_label'] = 'Most Reviewed'

    # Best Value: best rating/price ratio (exclude editors choice)
    priced = [p for p in products[1:] if p.get('price', 0) > 0 and p.get('rating', 0) > 0]
    if priced:
        best_val = max(priced, key=lambda p: p.get('rating', 0) / max(p.get('price', 1), 1) * 1000)
        if not best_val.get('badge'):
            best_val['badge'] = 'best_value'
            best_val['badge_label'] = 'Best Value'

    # Premium Pick: highest price with rating >= 4
    premium = [p for p in products[1:] if p.get('price', 0) > 0 and p.get('rating', 0) >= 4.0]
    if premium:
        prem = max(premium, key=lambda p: p.get('price', 0))
        if not prem.get('badge'):
            prem['badge'] = 'premium_pick'
            prem['badge_label'] = 'Premium Pick'

    # Budget Pick: lowest price among remaining
    remaining = [p for p in products[1:] if not p.get('badge') and p.get('price', 0) > 0]
    if remaining:
        budget = min(remaining, key=lambda p: p.get('price', float('inf')))
        budget['badge'] = 'budget_pick'
        budget['badge_label'] = 'Budget Pick'


# ===== 10. Editorial Recommendation System (no Amazon ratings) =====
#
# We do NOT display Amazon customer ratings because most products lack that
# data. Instead, every recommendation carries an EDITORIAL verdict derived
# deterministically from the recommendation engine's own signals:
#
#     recommendation_score (editorial signal, value, compatibility, brand,
#     availability) and quality signals (editorial_signal, value_for_money).
#
# Tiers (percentile-based across the candidate pool, or absolute fallback):
#     Top 10%  -> 5 stars  "Highly Recommended"
#     Top 30%  -> 4 stars  "Recommended"
#     Top 60%  -> 3 stars  "Good Choice"
#     Remaining-> None     (no editorial stars shown)
#
# We NEVER emit 1 or 2 star tiers (low value) and NEVER hardcode a rating.

EDITORIAL_TIERS = {
    5: {'stars': 5, 'label': 'Highly Recommended'},
    4: {'stars': 4, 'label': 'Recommended'},
    3: {'stars': 3, 'label': 'Good Choice'},
}


def editorial_quality_score(product: dict, category: Optional[str] = None,
                            bike: Optional[dict] = None) -> float:
    """Return a 0-1 editorial quality score derived from real engine signals.

    Combines the composite recommendation score (which already blends
    editorial signal, value for money, compatibility, brand trust, and
    availability) with the intrinsic quality signals. Deterministic; no
    randomness, no fabricated Amazon rating.
    """
    rec = recommendation_score(product, category, bike)        # ~0-1 weighted
    editor = editorial_signal(product)                          # 0-1 real only
    value = value_for_money(product)                            # 0-1
    # Weighted blend emphasizing the engine's own composite score.
    score = 0.6 * max(0.0, rec) + 0.25 * editor + 0.15 * value
    return round(min(1.0, max(0.0, score)), 4)


def _tier_from_percentile(percentile: float) -> Optional[dict]:
    """Map a 0-1 percentile rank (higher = better) to an editorial tier.

    Top 10% -> Highly Recommended (5)
    Top 30% -> Recommended (4)
    Top 60% -> Good Choice (3)
    else    -> None (no editorial stars)
    """
    if percentile >= 0.90:
        return dict(EDITORIAL_TIERS[5])
    if percentile >= 0.70:
        return dict(EDITORIAL_TIERS[4])
    if percentile >= 0.40:
        return dict(EDITORIAL_TIERS[3])
    return None


def get_editorial_recommendation(product: dict, category: Optional[str] = None,
                                 bike: Optional[dict] = None,
                                 percentile: Optional[float] = None) -> dict:
    """Return the editorial recommendation tier for a single product.

    Args:
        product: the product dict.
        category: canonical category (optional, improves scoring).
        bike: selected motorcycle (optional, improves scoring).
        percentile: optional 0-1 rank of this product within its candidate
            pool. When provided, tiers follow the percentile mapping
            (Top 10% / 30% / 60%). When omitted, an absolute quality
            threshold is used so a product can still earn a tier on its own.

    Returns:
        {'stars': int, 'label': str} or {} when the product does not qualify
        for any editorial tier (callers then render NO stars at all).
    """
    if percentile is not None:
        tier = _tier_from_percentile(float(percentile))
        return tier if tier else {}

    # Absolute fallback: base the tier on intrinsic quality signals.
    quality = editorial_quality_score(product, category, bike)
    # Thresholds chosen so a genuinely strong product earns a tier, and a
    # weak product earns none (never 1-2 stars).
    if quality >= 0.75:
        return dict(EDITORIAL_TIERS[5])
    if quality >= 0.55:
        return dict(EDITORIAL_TIERS[4])
    if quality >= 0.38:
        return dict(EDITORIAL_TIERS[3])
    return {}


def assign_editorial_tiers(products: list, category: Optional[str] = None,
                           bike: Optional[dict] = None) -> Dict[str, dict]:
    """Assign editorial tiers to a ranked pool of products.

    Computes each product's percentile rank by editorial_quality_score within
    the pool and maps it to a tier (Top 10% / 30% / 60%, else none).

    Returns a dict keyed by product slug -> {'stars': int, 'label': str}.
    Products that do not qualify are simply absent from the dict (callers
    render no editorial stars for them).
    """
    if not products:
        return {}

    scored = []
    for p in products:
        slug = p.get('slug') or p.get('asin') or ''
        if not slug:
            continue
        scored.append((slug, editorial_quality_score(p, category, bike)))

    if not scored:
        return {}

    scores = [s for _, s in scored]
    lo, hi = min(scores), max(scores)
    span = (hi - lo) or 1.0

    tiers: Dict[str, dict] = {}
    for slug, score in scored:
        # Percentile rank: fraction of the pool at or below this score.
        below = sum(1 for s in scores if s <= score)
        percentile = (below - 1) / max(len(scores) - 1, 1)
        # Normalize so the single best product is ~1.0 (top of pool).
        norm = (score - lo) / span
        tier = _tier_from_percentile(max(percentile, norm))
        if tier:
            tiers[slug] = tier
    return tiers
