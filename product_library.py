"""
Product Library
===============
Central product library for the curated motorcycle recommendation platform.

This module is the single source of truth for loading, filtering, validating,
and managing the product catalog. It separates editorial data (owned by us)
from Amazon data (changes daily) and enforces product status throughout the
lifecycle.

Product Lifecycle:
    Discover -> Review -> Approve -> Add to Library -> Daily Sync -> Recommend

Data Structure:
    Each product has:
    - Identity: asin, slug, title, brand, category, type
    - Status: draft | approved | hidden | out_of_stock | discontinued
    - Editorial: score, pros, cons, features, fitment_notes, recommended_for, notes
    - Amazon: price, mrp, discount, rating, review_count, availability, etc.
    - Compatibility: compatible_bikes
    - Presentation: best_for, verdict

The library loads the nested JSON and flattens it into plain dicts that are
100% compatible with existing templates, product_engine.py, and generate.py.
Templates continue to access product.price, product.rating, etc. directly.
"""

import json
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ===== Valid Product Statuses =====

VALID_STATUSES = {'draft', 'approved', 'hidden', 'out_of_stock', 'discontinued'}

# Statuses that should appear on the website.
WEBSITE_STATUSES = {'approved', 'out_of_stock'}

# Statuses that the recommendation engine should process.
RECOMMENDABLE_STATUSES = {'approved'}


# ===== JSON Schema (for validation reference) =====

REQUIRED_TOP_LEVEL = {'asin', 'slug', 'title', 'brand', 'category', 'status'}
REQUIRED_EDITORIAL = {'score', 'pros', 'cons'}
REQUIRED_AMAZON = {'price', 'rating', 'affiliate_url'}

EDITORIAL_FIELDS = {'score', 'pros', 'cons', 'features', 'fitment_notes',
                    'recommended_for', 'notes'}
AMAZON_FIELDS = {'price', 'mrp', 'discount', 'rating', 'review_count',
                 'availability', 'affiliate_url', 'image', 'last_updated'}

# Fields that can exist at the top level alongside nested editorial/amazon.
TOP_LEVEL_FIELDS = {'asin', 'slug', 'title', 'brand', 'category', 'type',
                    'status', 'compatible_bikes', 'best_for', 'verdict'}


# ===== Loading & Flattening =====

def load_products(products_dir: Path) -> list:
    """Load all product JSON files from the products directory.

    Returns flat dicts compatible with templates and product_engine.
    Each product dict includes all fields at the top level for backward
    compatibility, plus a 'status' field for filtering.

    The flattened structure preserves:
    - amazon.price as product.price
    - amazon.rating as product.rating
    - amazon.review_count as product.reviews (legacy alias)
    - amazon.image as product.image (legacy alias)
    - editorial.score as product.editor_rating (legacy alias)
    - editorial.pros/cons as product.pros/cons (top-level)
    """
    products = []

    if not products_dir.exists():
        return products

    for filepath in sorted(products_dir.glob('*.json')):
        if filepath.suffix == '.bak':
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  Warning: Failed to load {filepath.name}: {e}")
            continue

        if isinstance(raw, list):
            for item in raw:
                flat = _flatten_product(item, filepath.name)
                if flat:
                    products.append(flat)
        elif isinstance(raw, dict):
            flat = _flatten_product(raw, filepath.name)
            if flat:
                products.append(flat)

    return products


def _flatten_product(raw: dict, source_file: str = '') -> Optional[dict]:
    """Convert a nested product dict into a flat dict for template compat.

    Handles both formats:
    1. New nested format: editorial.score, amazon.price, etc.
    2. Legacy flat format: editor_rating, price, rating, etc.

    Returns None if the product is missing critical fields.
    """
    if not raw:
        return None

    product = {}

    # --- Top-level identity & metadata ---
    for field in TOP_LEVEL_FIELDS:
        if field in raw:
            product[field] = raw[field]

    # --- Editorial data ---
    editorial = raw.get('editorial', {})
    if editorial:
        # Score
        product['editor_rating'] = editorial.get('score', raw.get('editor_rating', 0))
        # Pros & cons (keep at top level for templates)
        product['pros'] = editorial.get('pros', raw.get('pros', []))
        product['cons'] = editorial.get('cons', raw.get('cons', []))
        # Additional editorial fields
        product['features'] = editorial.get('features', [])
        product['fitment_notes'] = editorial.get('fitment_notes', '')
        product['recommended_for'] = editorial.get('recommended_for', [])
        product['editorial_notes'] = editorial.get('notes', '')
        # Store raw editorial for validation/sync reference
        product['_editorial'] = editorial
    else:
        # Legacy flat format fallback
        product['editor_rating'] = raw.get('editor_rating', 0)
        product['pros'] = raw.get('pros', [])
        product['cons'] = raw.get('cons', [])

    # --- Amazon data ---
    amazon = raw.get('amazon', {})
    if amazon:
        product['price'] = amazon.get('price', raw.get('price', 0))
        product['mrp'] = amazon.get('mrp', None)
        product['discount'] = amazon.get('discount', None)
        product['rating'] = amazon.get('rating', raw.get('rating', 0))
        product['reviews'] = amazon.get('review_count', raw.get('reviews', 0))
        product['review_count'] = product['reviews']  # both keys work
        product['availability'] = amazon.get('availability', '')
        product['affiliate_url'] = amazon.get('affiliate_url', raw.get('affiliate_url', ''))
        product['image'] = amazon.get('image', raw.get('image', ''))
        product['amazon_image_url'] = amazon.get('image', raw.get('image', ''))
        product['last_updated'] = amazon.get('last_updated', None)
        product['amazon_synced'] = bool(amazon.get('last_updated'))
        # Store raw amazon for sync engine reference
        product['_amazon'] = amazon
    else:
        # Legacy flat format fallback
        product['price'] = raw.get('price', 0)
        product['mrp'] = raw.get('mrp', None)
        product['discount'] = raw.get('discount', None)
        product['rating'] = raw.get('rating', 0)
        product['reviews'] = raw.get('reviews', 0)
        product['review_count'] = product['reviews']
        product['availability'] = raw.get('availability', '')
        product['affiliate_url'] = raw.get('affiliate_url', '')
        product['image'] = raw.get('image', '')
        product['amazon_image_url'] = raw.get('image', raw.get('amazon_image_url', ''))
        product['last_updated'] = None
        product['amazon_synced'] = False

    # --- Compatibility ---
    product['compatible_bikes'] = raw.get('compatible_bikes', ['*'])

    # --- Presentation ---
    product['best_for'] = raw.get('best_for', '')
    product['verdict'] = raw.get('verdict', '')

    # --- Status (default to 'approved' for legacy compat) ---
    product['status'] = raw.get('status', 'approved')

    # --- Source tracking ---
    product['_source_file'] = source_file

    return product


def unflatten_product(product: dict) -> dict:
    """Convert a flat product dict back to the nested JSON structure.

    Used when saving products back to JSON files. Strips internal keys
    (those starting with '_').
    """
    nested = {
        'asin': product.get('asin', ''),
        'slug': product.get('slug', ''),
        'title': product.get('title', ''),
        'brand': product.get('brand', ''),
        'category': product.get('category', ''),
        'type': product.get('type', ''),
        'status': product.get('status', 'approved'),
        'editorial': {
            'score': product.get('editor_rating', 0),
            'pros': product.get('pros', []),
            'cons': product.get('cons', []),
            'features': product.get('features', []),
            'fitment_notes': product.get('fitment_notes', ''),
            'recommended_for': product.get('recommended_for', []),
            'notes': product.get('editorial_notes', ''),
        },
        'amazon': {
            'price': product.get('price', 0),
            'mrp': product.get('mrp'),
            'discount': product.get('discount'),
            'rating': product.get('rating', 0),
            'review_count': product.get('review_count', product.get('reviews', 0)),
            'availability': product.get('availability', ''),
            'affiliate_url': product.get('affiliate_url', ''),
            'image': product.get('image', ''),
            'last_updated': product.get('last_updated'),
        },
        'compatible_bikes': product.get('compatible_bikes', ['*']),
        'best_for': product.get('best_for', ''),
        'verdict': product.get('verdict', ''),
    }
    return nested


# ===== Filtering =====

def approved_products(products: list) -> list:
    """Return only products with status == 'approved'."""
    return [p for p in products if p.get('status') == 'approved']


def active_products(products: list) -> list:
    """Return products that should appear on the website.

    Includes: approved, out_of_stock (shown with availability badge)
    Excludes: draft, hidden, discontinued
    """
    return [p for p in products if p.get('status') in WEBSITE_STATUSES]


def recommendable_products(products: list) -> list:
    """Return products the recommendation engine should process.

    Only 'approved' products are recommendable.
    """
    return [p for p in products if p.get('status') in RECOMMENDABLE_STATUSES]


def products_by_status(products: list) -> Dict[str, list]:
    """Group products by their status."""
    groups: Dict[str, list] = defaultdict(list)
    for p in products:
        status = p.get('status', 'unknown')
        groups[status].append(p)
    return dict(groups)


def products_by_category(products: list) -> Dict[str, list]:
    """Group products by their category."""
    groups: Dict[str, list] = defaultdict(list)
    for p in products:
        cat = p.get('category', 'Other')
        groups[cat].append(p)
    return dict(groups)


def products_by_brand(products: list) -> Dict[str, list]:
    """Group products by their brand."""
    groups: Dict[str, list] = defaultdict(list)
    for p in products:
        brand = p.get('brand', 'Unknown')
        groups[brand].append(p)
    return dict(groups)


# ===== Validation =====

def validate_products(products: list) -> dict:
    """Validate the entire product library.

    Checks:
    - Duplicate ASINs
    - Missing affiliate links (approved products)
    - Missing images (approved products)
    - Invalid prices (negative, zero for approved)
    - Missing categories
    - Missing editorial info (pros, cons, score)
    - Empty compatible_bikes
    - Unknown status values

    Returns: {errors: [...], warnings: [...], stats: {...}}
    """
    errors = []
    warnings = []
    asin_index: Dict[str, list] = defaultdict(list)
    slug_index: Dict[str, list] = defaultdict(list)

    for i, p in enumerate(products):
        slug = p.get('slug', f'product_{i}')
        asin = (p.get('asin') or '').strip().upper()
        status = p.get('status', 'approved')
        source = p.get('_source_file', 'unknown')

        # --- Required fields ---
        if not p.get('slug'):
            errors.append(f"[{source}] Product at index {i}: missing 'slug'")
        if not p.get('title'):
            errors.append(f"[{source}] {slug}: missing 'title'")
        if not p.get('brand'):
            warnings.append(f"[{source}] {slug}: missing 'brand'")
        if not p.get('category'):
            errors.append(f"[{source}] {slug}: missing 'category'")

        # --- Status ---
        if status not in VALID_STATUSES:
            errors.append(f"[{source}] {slug}: invalid status '{status}' "
                         f"(must be one of: {', '.join(sorted(VALID_STATUSES))})")

        # --- ASIN tracking ---
        if asin:
            asin_index[asin].append(slug)

        # --- Slug tracking ---
        if p.get('slug'):
            slug_index[p['slug']].append(source)

        # --- Approved product quality checks ---
        if status == 'approved':
            # Affiliate link
            if not p.get('affiliate_url'):
                warnings.append(f"[{source}] {slug}: approved product missing affiliate URL")

            # Image
            if not p.get('image'):
                warnings.append(f"[{source}] {slug}: approved product missing image")

            # Price
            price = p.get('price', 0)
            if price < 0:
                errors.append(f"[{source}] {slug}: negative price ({price})")
            if price == 0:
                warnings.append(f"[{source}] {slug}: price is 0 (may be unavailable)")

            # Editorial
            if not p.get('pros'):
                warnings.append(f"[{source}] {slug}: missing 'pros' in editorial data")
            if not p.get('cons'):
                warnings.append(f"[{source}] {slug}: missing 'cons' in editorial data")
            if not p.get('editor_rating'):
                warnings.append(f"[{source}] {slug}: missing editor rating/score")

            # Compatibility
            compat = p.get('compatible_bikes', [])
            if not compat:
                warnings.append(f"[{source}] {slug}: empty compatible_bikes list")

    # --- Duplicate detection ---
    for asin, slugs in asin_index.items():
        if len(slugs) > 1:
            errors.append(f"Duplicate ASIN {asin}: found in {', '.join(slugs)}")

    for slug, sources in slug_index.items():
        if len(sources) > 1:
            errors.append(f"Duplicate slug '{slug}': found in {', '.join(sources)}")

    # --- Stats ---
    by_status = defaultdict(int)
    by_category = defaultdict(int)
    by_brand = defaultdict(int)
    for p in products:
        by_status[p.get('status', 'unknown')] += 1
        by_category[p.get('category', 'Unknown')] += 1
        by_brand[p.get('brand', 'Unknown')] += 1
    stats = {
        'total': len(products),
        'by_status': dict(by_status),
        'by_category': dict(by_category),
        'by_brand': dict(by_brand),
    }

    return {
        'errors': errors,
        'warnings': warnings,
        'stats': stats,
        'valid': len(errors) == 0,
    }


def find_duplicates(products: list) -> dict:
    """Find duplicate products by ASIN, slug, or normalized title.

    Returns: {asin_duplicates: [...], slug_duplicates: [...], title_duplicates: [...]}
    """
    asin_index: Dict[str, list] = defaultdict(list)
    slug_index: Dict[str, list] = defaultdict(list)
    title_index: Dict[str, list] = defaultdict(list)

    for p in products:
        asin = (p.get('asin') or '').strip().upper()
        if asin:
            asin_index[asin].append(p.get('slug', 'unknown'))

        slug = (p.get('slug') or '').strip().lower()
        if slug:
            slug_index[slug].append(p.get('_source_file', 'unknown'))

        title = (p.get('title') or '').strip().lower()
        if title:
            title_index[title].append(p.get('slug', 'unknown'))

    asin_dupes = [{'asin': a, 'products': s} for a, s in asin_index.items() if len(s) > 1]
    slug_dupes = [{'slug': s, 'sources': src} for s, src in slug_index.items() if len(src) > 1]
    title_dupes = [{'title': t, 'products': s} for t, s in title_index.items() if len(s) > 1]

    return {
        'asin_duplicates': asin_dupes,
        'slug_duplicates': slug_dupes,
        'title_duplicates': title_dupes,
    }


# ===== Statistics =====

def generate_stats(products: list) -> dict:
    """Generate comprehensive product library statistics."""
    by_status = defaultdict(int)
    by_category = defaultdict(int)
    by_brand = defaultdict(int)

    stats = {
        'total_products': len(products),
        'average_rating': 0.0,
        'average_discount': 0.0,
        'average_price': 0.0,
        'average_editor_rating': 0.0,
        'out_of_stock_count': 0,
        'draft_count': 0,
        'discontinued_count': 0,
        'hidden_count': 0,
        'missing_editorial': [],
        'missing_images': [],
        'missing_affiliate': [],
        'duplicate_asins': [],
        'categories_empty': [],
        'products_with_compatibility': 0,
        'universal_products': 0,
    }

    if not products:
        return stats

    ratings = []
    discounts = []
    prices = []
    editor_ratings = []
    asin_seen: Dict[str, list] = defaultdict(list)

    for p in products:
        status = p.get('status', 'unknown')
        category = p.get('category', 'Unknown')
        brand = p.get('brand', 'Unknown')
        slug = p.get('slug', 'unknown')

        by_status[status] += 1
        by_category[category] += 1
        by_brand[brand] += 1

        if status == 'out_of_stock':
            stats['out_of_stock_count'] += 1
        elif status == 'draft':
            stats['draft_count'] += 1
        elif status == 'discontinued':
            stats['discontinued_count'] += 1
        elif status == 'hidden':
            stats['hidden_count'] += 1

        # Ratings
        r = p.get('rating', 0)
        if r:
            ratings.append(float(r))

        er = p.get('editor_rating', 0)
        if er:
            editor_ratings.append(float(er))

        # Price
        price = p.get('price', 0)
        if price:
            prices.append(float(price))

        # Discount
        disc = p.get('discount', 0)
        if disc:
            discounts.append(float(disc))

        # Missing data
        if not p.get('pros') and not p.get('cons'):
            stats['missing_editorial'].append(slug)
        if not p.get('image'):
            stats['missing_images'].append(slug)
        if not p.get('affiliate_url'):
            stats['missing_affiliate'].append(slug)

        # Compatibility
        compat = p.get('compatible_bikes', [])
        if compat:
            stats['products_with_compatibility'] += 1
            if '*' in compat:
                stats['universal_products'] += 1

        # ASIN tracking
        asin = (p.get('asin') or '').strip().upper()
        if asin:
            asin_seen[asin].append(slug)

    # Averages
    if ratings:
        stats['average_rating'] = round(sum(ratings) / len(ratings), 2)
    if editor_ratings:
        stats['average_editor_rating'] = round(sum(editor_ratings) / len(editor_ratings), 2)
    if prices:
        stats['average_price'] = round(sum(prices) / len(prices), 0)
    if discounts:
        stats['average_discount'] = round(sum(discounts) / len(discounts), 1)

    # Duplicates
    stats['duplicate_asins'] = [
        {'asin': a, 'products': s} for a, s in asin_seen.items() if len(s) > 1
    ]

    # Final grouping stats
    stats['by_status'] = dict(by_status)
    stats['by_category'] = dict(by_category)
    stats['by_brand'] = dict(by_brand)

    return stats


# ===== Import/Export =====

def import_legacy_products(products_dir: Path, dry_run: bool = False) -> dict:
    """Migrate old flat JSON files to the new nested structure.

    Reads each .json file in products_dir, converts products from flat format
    to the new nested format, and saves them back.

    Returns: {migrated: int, files: [...], errors: [...]}
    """
    result = {'migrated': 0, 'files': [], 'errors': []}

    if not products_dir.exists():
        result['errors'].append(f"Directory not found: {products_dir}")
        return result

    for filepath in sorted(products_dir.glob('*.json')):
        if filepath.suffix == '.bak':
            continue

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            result['errors'].append(f"Failed to read {filepath.name}: {e}")
            continue

        if not isinstance(raw, list):
            result['errors'].append(f"{filepath.name}: expected array, got {type(raw).__name__}")
            continue

        migrated_products = []
        for item in raw:
            nested = _migrate_legacy_product(item)
            migrated_products.append(nested)
            result['migrated'] += 1

        if not dry_run:
            # Create backup
            backup_path = filepath.with_suffix('.json.bak')
            shutil.copy2(filepath, backup_path)

            # Write migrated data
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(migrated_products, f, indent=2, ensure_ascii=False)

        result['files'].append(filepath.name)

    return result


def _migrate_legacy_product(raw: dict) -> dict:
    """Convert a legacy flat product dict to the new nested structure."""
    # Determine status - default to 'approved' for existing products
    status = raw.get('status', 'approved')

    # Build editorial section
    editorial = {
        'score': raw.get('editor_rating', 0),
        'pros': raw.get('pros', []),
        'cons': raw.get('cons', []),
        'features': raw.get('features', []),
        'fitment_notes': raw.get('fitment_notes', ''),
        'recommended_for': raw.get('recommended_for', []),
        'notes': raw.get('editorial_notes', ''),
    }

    # Build amazon section
    amazon = {
        'price': raw.get('price', 0),
        'mrp': raw.get('mrp'),
        'discount': raw.get('discount'),
        'rating': raw.get('rating', 0),
        'review_count': raw.get('reviews', raw.get('review_count', 0)),
        'availability': raw.get('availability', ''),
        'affiliate_url': raw.get('affiliate_url', ''),
        'image': raw.get('image', ''),
        'last_updated': raw.get('last_updated'),
    }

    return {
        'asin': raw.get('asin', ''),
        'slug': raw.get('slug', ''),
        'title': raw.get('title', ''),
        'brand': raw.get('brand', ''),
        'category': raw.get('category', ''),
        'type': raw.get('type', ''),
        'status': status,
        'editorial': editorial,
        'amazon': amazon,
        'compatible_bikes': raw.get('compatible_bikes', ['*']),
        'best_for': raw.get('best_for', ''),
        'verdict': raw.get('verdict', ''),
    }


def export_products(products: list, output_path: Path) -> None:
    """Export products to a JSON file (for backup/sharing).

    Converts flat dicts back to nested format for clean export.
    """
    nested = [unflatten_product(p) for p in products]
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(nested, f, indent=2, ensure_ascii=False)


# ===== Product Lookup =====

def find_product_by_slug(products: list, slug: str) -> Optional[dict]:
    """Find a product by its slug."""
    for p in products:
        if p.get('slug') == slug:
            return p
    return None


def find_product_by_asin(products: list, asin: str) -> Optional[dict]:
    """Find a product by its ASIN."""
    asin_upper = asin.strip().upper()
    for p in products:
        if (p.get('asin') or '').strip().upper() == asin_upper:
            return p
    return None


def find_products_by_asin(products: list, asins: list) -> list:
    """Find multiple products by their ASINs."""
    asin_set = {a.strip().upper() for a in asins}
    return [p for p in products if (p.get('asin') or '').strip().upper() in asin_set]


# ===== Product Count Management =====

def count_by_status(products: list) -> Dict[str, int]:
    """Count products by status."""
    counts: Dict[str, int] = defaultdict(int)
    for p in products:
        counts[p.get('status', 'unknown')] += 1
    return dict(counts)


def count_by_category(products: list) -> Dict[str, int]:
    """Count products by category."""
    counts: Dict[str, int] = defaultdict(int)
    for p in products:
        counts[p.get('category', 'Unknown')] += 1
    return dict(counts)


# ===== Import Helpers =====

# Brand normalization map: lowercase canonical -> display name
BRAND_DISPLAY_NAMES: Dict[str, str] = {
    'bobo': 'BOBO',
    'studds': 'Studds',
    'steelbird': 'Steelbird',
    'vega': 'Vega',
    'axor': 'Axor',
    'ls2': 'LS2',
    'smk': 'SMK',
    'mt': 'MT',
    'motul': 'Motul',
    'shell': 'Shell',
    'castrol': 'Castrol',
    'liqui moly': 'Liqui Moly',
    'motorex': 'Motorex',
    'michelin': 'Michelin',
    'bosch': 'Bosch',
    'amazon basics': 'Amazon Basics',
    'amazonbasics': 'Amazon Basics',
    'tvs': 'TVS',
    'hero': 'Hero MotoCorp',
    'honda': 'Honda',
    'yamaha': 'Yamaha',
    'bajaj': 'Bajaj',
    'suzuki': 'Suzuki',
    'royal enfield': 'Royal Enfield',
    'ktm': 'KTM',
    'harley-davidson': 'Harley-Davidson',
    'triumph': 'Triumph',
    'xiaomi': 'Xiaomi',
    'strief': 'STRIFF',
}

# Category normalization aliases (subset of product_engine.CATEGORY_ALIASES
# for use without importing the full engine)
CATEGORY_IMPORT_ALIASES: Dict[str, str] = {
    # Phone Mount
    'phone holder': 'Phone Mount',
    'mobile holder': 'Phone Mount',
    'mobile mount': 'Phone Mount',
    'handlebar mount': 'Phone Mount',
    'motorcycle phone mount': 'Phone Mount',
    'bike phone mount': 'Phone Mount',
    'motorcycle': 'Phone Mount',
    'motorcycle mobile holder': 'Phone Mount',
    'phone mount': 'Phone Mount',
    'mobile mount': 'Phone Mount',
    'mobile holder for bike': 'Phone Mount',
    'phone mount': 'Phone Mount',
    'mobile mount': 'Phone Mount',
    'motorcycle phone mount': 'Phone Mount',
    'bike phone mount': 'Phone Mount',
    'bike phone mount': 'Phone Mount',
    'phone mount': 'Phone Mount',
    'mobile holder for bike': 'Phone Mount',
    'motorcycle phone mount': 'Phone Mount',
    # Crash Guard
    'engine guard': 'Crash Guard',
    'leg guard': 'Crash Guard',
    'crash protection': 'Crash Guard',
    'frame slider': 'Crash Guard',
    # Chain Lube
    'chain spray': 'Chain Lube',
    'chain lubricant': 'Chain Lube',
    'chain wax': 'Chain Lube',
    'chain lube': 'Chain Lube',
    'bike chain lube': 'Chain Lube',
    'motorcycle chain lube': 'Chain Lube',
    # Chain Cleaner
    'chain cleaner spray': 'Chain Cleaner',
    'chain cleaner': 'Chain Cleaner',
    'bike chain cleaner': 'Chain Cleaner',
    'motorcycle chain cleaner': 'Chain Cleaner',
    # Tyre Inflator
    'air compressor': 'Tyre Inflator',
    'tyre pump': 'Tyre Inflator',
    'air pump': 'Tyre Inflator',
    'portable compressor': 'Tyre Inflator',
    'tire inflator': 'Tyre Inflator',
    'tyre inflator': 'Tyre Inflator',
    # Gloves
    'riding gloves': 'Gloves',
    'bike gloves': 'Gloves',
    'motorcycle gloves': 'Gloves',
    # Jackets
    'riding jacket': 'Jackets',
    'bike jacket': 'Jackets',
    'motorcycle jacket': 'Jackets',
    # Bike Cover
    'motorcycle cover': 'Bike Cover',
    'body cover': 'Bike Cover',
    'bike body cover': 'Bike Cover',
    'bike cover': 'Bike Cover',
    # Helmet
    'full face helmet': 'Helmet',
    'open face helmet': 'Helmet',
    'modular helmet': 'Helmet',
    'half helmet': 'Helmet',
    'motorcycle helmet': 'Helmet',
    'riding helmet': 'Helmet',
    'bike helmet': 'Helmet',
    'helmet bluetooth': 'Helmet',
    # Engine Oil
    'engine oil 10w-40': 'Engine Oil',
    'engine oil 10w-50': 'Engine Oil',
    'motor oil': 'Engine Oil',
    # Luggage
    'tank bag motorcycle': 'Tank Bag',
    'tank bag': 'Tank Bag',
    'saddlebag': 'Saddle Bag',
    'saddle bags': 'Saddle Bag',
    'motorcycle saddle bag': 'Saddle Bag',
    'bike saddle bag': 'Saddle Bag',
    'tail bag': 'Tail Bag',
    # Protection
    'knee pad': 'Knee Guard',
    'knee guard': 'Knee Guard',
    # Ear Plugs
    'ear plugs': 'Ear Plugs',
    'ear plug': 'Ear Plugs',
    # Cameras
    'action camera': 'Action Camera',
    'dash cam': 'Dash Cam',
    # Seat Cover
    'bike seat cover': 'Seat Cover',
    'motorcycle seat cover': 'Seat Cover',
    # Riding Pants
    'riding pants': 'Riding Pants',
    # Handlebar
    'handlebar grip': 'Handlebar Grip',
    # Mirrors
    'bike mirror': 'Mirror',
    'motorcycle mirror': 'Mirror',
    # Windshield
    'motorcycle windshield': 'Windshield',
    'bike windshield': 'Windshield',
    # GPS
    'gps tracker for bike': 'GPS Tracker',
    'bike gps': 'GPS Tracker',
    # Lights
    'motorcycle headlight': 'Headlight',
    'motorcycle indicator': 'Indicator',
    'bike indicator': 'Indicator',
    # Horn
    'motorcycle horn': 'Horn',
    'bike horn': 'Horn',
    # Charger
    'motorcycle charger': 'Charger',
    # Footrest
    'motorcycle footrest': 'Footrest',
    # Locks
    'chain lock': 'Chain Lock',
    'bike disc lock': 'Disc Lock',
    # Alarm
    'bike alarm': 'Alarm',
    'motorcycle alarm': 'Alarm',
    # Tools
    'motorcycle tool kit': 'Tool Kit',
    # Polish
    'bike polish': 'Polish',
}


def keyword_to_category(keyword: str) -> Optional[str]:
    """Map a bike-deals.json _search_keyword to a canonical category name.

    Returns None if the keyword doesn't map to any known category.
    """
    if not keyword:
        return None
    key = keyword.strip().lower()
    if key in CATEGORY_IMPORT_ALIASES:
        return CATEGORY_IMPORT_ALIASES[key]
    return None


def generate_slug(title: str) -> str:
    """Generate a URL-friendly slug from a product title.

    Examples:
        'BOBO BM4 PRO Plus' -> 'bobo-bm4-pro-plus'
        'Motul 7100 4T 10W-40' -> 'motul-7100-4t-10w-40'
    """
    import re
    slug = title.lower().strip()
    # Remove non-alphanumeric except hyphens
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    # Replace spaces with hyphens
    slug = re.sub(r'[\s]+', '-', slug)
    # Collapse multiple hyphens
    slug = re.sub(r'-+', '-', slug)
    # Strip leading/trailing hyphens
    slug = slug.strip('-')
    return slug


def normalize_brand(brand: str) -> str:
    """Normalize a brand name to its canonical display form.

    Examples:
        'bobo' -> 'BOBO'
        'studds' -> 'Studds'
        'TVS' -> 'TVS'
    """
    if not brand:
        return brand
    key = brand.strip().lower()
    return BRAND_DISPLAY_NAMES.get(key, brand.strip().title())


def normalize_category_name(category: str) -> str:
    """Normalize a category name using the import alias map.

    Returns the canonical category name.
    """
    if not category:
        return category
    key = category.strip().lower()
    if key in CATEGORY_IMPORT_ALIASES:
        return CATEGORY_IMPORT_ALIASES[key]
    return category.strip().title()


def is_empty_or_default(value: Any) -> bool:
    """Check if a value is empty or a default/placeholder value.

    Used to decide whether to generate content for a field.
    """
    if value is None:
        return True
    if isinstance(value, str) and value.strip() in ('', 'N/A', 'TBD', 'TODO'):
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    if isinstance(value, (int, float)) and value == 0:
        return True
    return False
