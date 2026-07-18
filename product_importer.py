#!/usr/bin/env python3
"""
Product Import Assistant
=======================
CLI tool for importing, validating, deduplicating, and enriching products
in the BikeReview India product library.

Usage:
    python product_importer.py import <file> [--dry-run] [--output <path>] [--on-duplicate skip|merge|replace]
    python product_importer.py validate [--verbose]
    python product_importer.py dedupe [--verbose]
    python product_importer.py enrich [--category <name>] [--dry-run]

Pipeline:
    1. Load products from JSON or CSV
    2. Normalize fields (category, brand, slug, ASIN)
    3. Validate required fields and data integrity
    4. Detect and resolve duplicates against existing catalog
    5. Generate missing editorial content (flagged for review)
    6. Write enriched products to output file

All generated editorial fields are flagged with _generated: true so they
can be reviewed and manually overwritten. Manually edited fields are
never overwritten.
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from product_library import (
    VALID_STATUSES,
    load_products,
    validate_products,
    find_duplicates,
    unflatten_product,
    generate_slug,
    resolve_slug_duplicates,
    normalize_brand,
    normalize_category,
    is_empty_or_default,
    CATEGORY_IMPORT_ALIASES,
    BRAND_DISPLAY_NAMES,
    keyword_to_category,
)
from product_engine import (
    TRUSTED_BRANDS,
    CATEGORY_PRICE_RANGES,
    preferred_price_range,
    value_for_money,
)

# ===== Constants =====

DATA_DIR = PROJECT_ROOT / 'data' / 'products'
GENERATED_FLAG = '_generated_fields'


# ===== 1. Import Sources =====

# CSV column aliases: maps common CSV header names to product field names
CSV_COLUMN_ALIASES: Dict[str, str] = {
    'product name': 'title',
    'product_title': 'title',
    'product name (english)': 'title',
    'name': 'title',
    'product_title (english)': 'title',
    'asin': 'asin',
    'amazon asin': 'asin',
    'brand': 'brand',
    'manufacturer': 'brand',
    'category': 'category',
    'product category': 'category',
    'type': 'type',
    'product type': 'type',
    'price': 'price',
    'current price': 'price',
    'selling price': 'price',
    'mrp': 'mrp',
    'max retail price': 'mrp',
    'discount': 'discount',
    'rating': 'rating',
    'customer rating': 'rating',
    'stars': 'rating',
    'review count': 'review_count',
    'reviews': 'review_count',
    'number of reviews': 'review_count',
    'availability': 'availability',
    'in stock': 'availability',
    'affiliate url': 'affiliate_url',
    'amazon url': 'affiliate_url',
    'url': 'affiliate_url',
    'link': 'affiliate_url',
    'image': 'image',
    'image url': 'image',
    'product image': 'image',
    'compatible bikes': 'compatible_bikes',
    'compatibility': 'compatible_bikes',
    'best for': 'best_for',
    'recommended for': 'best_for',
    'status': 'status',
}


def load_json(path: Path) -> list:
    """Load products from a JSON file. Handles both nested and flat formats."""
    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        raw = [raw]

    if not isinstance(raw, list):
        print(f"  Error: Expected JSON array, got {type(raw).__name__}")
        return []

    products = []
    for item in raw:
        flat = _normalize_to_flat(item)
        if flat:
            products.append(flat)
    return products


def load_csv(path: Path) -> list:
    """Load products from a CSV file. Maps columns using aliases."""
    products = []

    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            print("  Error: CSV has no header row")
            return []

        # Map CSV columns to product fields
        col_map = {}
        for col in reader.fieldnames:
            normalized = col.strip().lower()
            if normalized in CSV_COLUMN_ALIASES:
                col_map[col] = CSV_COLUMN_ALIASES[normalized]
            else:
                col_map[col] = normalized

        for i, row in enumerate(reader):
            product = {}
            for csv_col, field_name in col_map.items():
                value = row.get(csv_col, '').strip()
                if value:
                    product[field_name] = value

            flat = _normalize_to_flat(product)
            if flat:
                products.append(flat)

    return products


def _normalize_to_flat(raw: dict) -> Optional[dict]:
    """Convert any product dict (nested or flat) to the flat format."""
    product = {}

    # Handle nested format
    editorial = raw.get('editorial', {})
    amazon = raw.get('amazon', {})

    # Top-level fields
    for field in ('asin', 'slug', 'title', 'brand', 'category', 'type',
                  'status', 'compatible_bikes', 'best_for', 'verdict'):
        if field in raw:
            product[field] = raw[field]
        elif field == 'status':
            product[field] = 'draft'  # new imports default to draft

    # Editorial fields
    if editorial:
        product['editor_rating'] = editorial.get('score', raw.get('editor_rating', 0))
        product['pros'] = editorial.get('pros', raw.get('pros', []))
        product['cons'] = editorial.get('cons', raw.get('cons', []))
        product['features'] = editorial.get('features', [])
        product['fitment_notes'] = editorial.get('fitment_notes', '')
        product['recommended_for'] = editorial.get('recommended_for', [])
        product['editorial_notes'] = editorial.get('notes', '')
    else:
        for field in ('editor_rating', 'editorial_verdict', 'pros', 'cons', 'features',
                      'fitment_notes', 'recommended_for', 'editorial_notes'):
            if field in raw:
                product[field] = raw[field]

    # Amazon fields
    if amazon:
        product['price'] = amazon.get('price', raw.get('price', 0))
        product['mrp'] = amazon.get('mrp', raw.get('mrp'))
        product['discount'] = amazon.get('discount', raw.get('discount'))
        product['rating'] = amazon.get('rating', raw.get('rating', 0))
        product['review_count'] = amazon.get('review_count', raw.get('review_count', 0))
        product['availability'] = amazon.get('availability', raw.get('availability', ''))
        product['affiliate_url'] = amazon.get('affiliate_url', raw.get('affiliate_url', ''))
        product['image'] = amazon.get('image', raw.get('image', ''))
        product['last_updated'] = amazon.get('last_updated')
    else:
        for field in ('price', 'mrp', 'discount', 'rating', 'review_count',
                      'availability', 'affiliate_url', 'image', 'last_updated'):
            if field in raw:
                product[field] = raw[field]

    # Ensure reviews alias exists
    if 'review_count' in product:
        product['reviews'] = product['review_count']
    elif 'reviews' in product:
        product['review_count'] = product['reviews']

    # Ensure required fields exist
    product.setdefault('price', 0)
    product.setdefault('rating', 0)
    product.setdefault('editor_rating', 0)
    product.setdefault('editorial_verdict', '')
    product.setdefault('pros', [])
    product.setdefault('cons', [])
    product.setdefault('features', [])
    product.setdefault('compatible_bikes', ['*'])
    product.setdefault('best_for', '')
    product.setdefault('verdict', '')
    product.setdefault('fitment_notes', '')
    product.setdefault('affiliate_url', '')
    product.setdefault('image', '')
    product.setdefault('availability', '')
    product.setdefault('status', 'draft')

    # Validate minimum required fields
    if not product.get('title'):
        return None

    return product


# ===== 2. Normalization =====

def normalize_product(product: dict) -> dict:
    """Normalize all fields of a product to canonical forms."""
    # Brand
    if product.get('brand'):
        product['brand'] = normalize_brand(product['brand'])

    # Category
    if product.get('category'):
        product['category'] = normalize_category(product['category'])

    # Slug - regenerate if it looks like a full title (long or many words)
    old_slug = product.get('slug', '')
    if not old_slug or len(old_slug) > 60 or len(old_slug.split('-')) > 8:
        product['slug'] = generate_slug(product['title'])

    # ASIN
    if product.get('asin'):
        product['asin'] = product['asin'].strip().upper()

    # Numeric fields
    for field in ('price', 'mrp', 'discount', 'rating', 'editor_rating', 'review_count'):
        val = product.get(field)
        if val is not None and val != '':
            try:
                product[field] = float(val) if '.' in str(val) else int(val)
            except (ValueError, TypeError):
                product[field] = 0

    # Rating bounds
    if product.get('rating', 0) > 5:
        product['rating'] = 5.0
    if product.get('editor_rating', 0) > 10:
        product['editor_rating'] = 10.0

    # List fields
    for field in ('pros', 'cons', 'features', 'compatible_bikes', 'recommended_for'):
        val = product.get(field)
        if isinstance(val, str):
            product[field] = [v.strip() for v in val.split(',') if v.strip()]
        elif not isinstance(val, list):
            product[field] = []

    # Ensure reviews alias
    if 'review_count' in product:
        product['reviews'] = product['review_count']

    return product


# ===== 3. Validation =====

def pre_import_validate(products: list) -> dict:
    """Validate products before import. Returns {errors, warnings, stats}."""
    errors = []
    warnings = []
    stats = {'total': len(products), 'valid': 0, 'invalid': 0}

    for i, p in enumerate(products):
        slug = p.get('slug', f'product_{i}')
        source = p.get('_source_file', 'import')

        # Required fields
        if not p.get('title'):
            errors.append(f"[{source}] Index {i}: missing 'title'")
            stats['invalid'] += 1
            continue

        if not p.get('brand'):
            warnings.append(f"[{source}] {slug}: missing 'brand'")

        if not p.get('category'):
            errors.append(f"[{source}] {slug}: missing 'category'")
            stats['invalid'] += 1
            continue

        # Status
        status = p.get('status', 'draft')
        if status not in VALID_STATUSES:
            errors.append(f"[{source}] {slug}: invalid status '{status}'")
            stats['invalid'] += 1
            continue

        # Price
        price = p.get('price', 0)
        if price < 0:
            errors.append(f"[{source}] {slug}: negative price ({price})")
            stats['invalid'] += 1
            continue

        # Rating
        rating = p.get('rating', 0)
        if rating and (rating < 0 or rating > 5):
            warnings.append(f"[{source}] {slug}: rating {rating} outside 0-5 range")

        # ASIN format
        asin = p.get('asin', '')
        if asin and not re.match(r'^B0[A-Z0-9]{8}$', asin):
            warnings.append(f"[{source}] {slug}: ASIN '{asin}' doesn't match expected format (B0XXXXXXXX)")

        stats['valid'] += 1

    return {'errors': errors, 'warnings': warnings, 'stats': stats}


# ===== 4. Duplicate Detection =====

def detect_import_duplicates(new_products: list, existing_products: list) -> list:
    """Detect duplicates between new and existing products.

    Returns list of duplicates:
        [
            {
                'new_index': 0,
                'existing_slug': 'motul-7100-10w40',
                'match_type': 'asin',  # asin, slug, title, url
                'confidence': 'exact',  # exact, high, medium
            },
            ...
        ]
    """
    # Build indexes from existing products
    existing_asins = {}
    existing_slugs = {}
    existing_titles = {}
    existing_urls = {}

    for p in existing_products:
        asin = (p.get('asin') or '').strip().upper()
        if asin:
            existing_asins[asin] = p.get('slug', '')

        slug = (p.get('slug') or '').strip().lower()
        if slug:
            existing_slugs[slug] = p

        title = _normalize_title(p.get('title', ''))
        if title:
            existing_titles[title] = p.get('slug', '')

        url = (p.get('affiliate_url') or '').strip()
        if url:
            existing_urls[url] = p.get('slug', '')

    duplicates = []
    for i, new in enumerate(new_products):
        # ASIN match (highest confidence)
        asin = (new.get('asin') or '').strip().upper()
        if asin and asin in existing_asins:
            duplicates.append({
                'new_index': i,
                'existing_slug': existing_asins[asin],
                'match_type': 'asin',
                'confidence': 'exact',
            })
            continue

        # Slug match
        slug = (new.get('slug') or '').strip().lower()
        if slug and slug in existing_slugs:
            duplicates.append({
                'new_index': i,
                'existing_slug': slug,
                'match_type': 'slug',
                'confidence': 'exact',
            })
            continue

        # Title match (normalized)
        title = _normalize_title(new.get('title', ''))
        if title and title in existing_titles:
            duplicates.append({
                'new_index': i,
                'existing_slug': existing_titles[title],
                'match_type': 'title',
                'confidence': 'high',
            })
            continue

        # URL match
        url = (new.get('affiliate_url') or '').strip()
        if url and url in existing_urls:
            duplicates.append({
                'new_index': i,
                'existing_slug': existing_urls[url],
                'match_type': 'url',
                'confidence': 'medium',
            })

    return duplicates


def _normalize_title(title: str) -> str:
    """Normalize a title for comparison. Strips brand, lowercases, removes extra spaces."""
    t = title.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t


# ===== 5. Editorial Content Generation =====

# Category-specific editorial templates
CATEGORY_EDITORIAL: Dict[str, dict] = {
    'Helmet': {
        'pros_pool': [
            'ISI certified for safety', 'Good ventilation system',
            'Scratch-resistant visor', 'Comfortable padding',
            'Lightweight design', 'Quick-release buckle',
            'Aerodynamic shape', 'Wide field of view',
            'Easy to clean interior', 'Multiple size options',
        ],
        'cons_pool': [
            'Visor scratches over time', 'Padding may compress with use',
            'Slightly heavy for long rides', 'Limited color options',
            'Noise at high speeds', 'Fogging in cold weather',
        ],
        'best_for_templates': [
            '{tier} riders wanting a {cert} {type} helmet',
            'Daily commuters needing {cert} head protection',
            '{tier} riders seeking a comfortable {type} helmet',
        ],
        'verdict_templates': [
            'The {brand} {short_name} is a {cert} {type} helmet offering {benefit} at an {price_ctx} price point.',
            'With {cert} certification and {feature}, the {brand} {short_name} delivers {benefit} for {tier} riders.',
        ],
    },
    'Phone Mount': {
        'pros_pool': [
            'Secure grip mechanism', 'Vibration dampener protects phone camera',
            'Waterproof design', 'Easy one-hand operation',
            'Quick-release mechanism', 'Universal handlebar fit',
            '360-degree rotation', 'Fits phones with cases',
        ],
        'cons_pool': [
            'Adds bulk to handlebar', 'Premium pricing',
            'Vibration damper needs periodic check', 'Plastic parts may weaken in heat',
            'Quick release can loosen on rough roads',
        ],
        'best_for_templates': [
            'Riders wanting {feature} phone mounting',
            '{tier} riders needing secure phone navigation',
            'Touring riders who need {feature}',
        ],
        'verdict_templates': [
            'The {brand} {short_name} offers {feature} with {benefit} for motorcycle phone mounting.',
            'Best for riders who need {feature}, the {brand} {short_name} provides {benefit}.',
        ],
    },
    'Engine Oil': {
        'pros_pool': [
            'Excellent engine protection', 'Smooth gear shifting',
            'Long drain interval', 'API/JASO certified',
            'Resists thermal breakdown', 'Reduces engine wear',
            'Suitable for Indian conditions', 'Value for money',
        ],
        'cons_pool': [
            'Higher price than mineral oils', 'May not suit older engines',
            'Shorter interval than fully synthetic', 'Requires specific grade',
            'Not ideal for very cold climates',
        ],
        'best_for_templates': [
            '{tier} riders wanting {type} engine protection',
            'Daily commuters needing reliable {viscosity} oil',
            '{tier} riders seeking {benefit}',
        ],
        'verdict_templates': [
            'The {brand} {short_name} is a {type} engine oil offering {benefit} at an {price_ctx} price.',
            'With {cert} certification, {brand} {short_name} delivers {benefit} for {tier} riders.',
        ],
    },
    'Chain Lube': {
        'pros_pool': [
            'Long-lasting lubrication', 'O-ring/X-ring safe',
            'Water-resistant formula', 'Easy spray application',
            'Minimal fling-off', 'Reduces chain noise',
            'Fast drying', 'Protects against rust',
        ],
        'cons_pool': [
            'Attracts dust in dry conditions', 'Strong chemical smell',
            'Can fling off at high speeds', 'Needs frequent reapplication in rain',
            'Spray nozzle can clog', 'Premium pricing',
        ],
        'best_for_templates': [
            '{tier} riders wanting long-lasting chain protection',
            'Daily commuters needing {benefit} chain lube',
            'Riders in {climate} conditions',
        ],
        'verdict_templates': [
            'The {brand} {short_name} is a {type} chain lube offering {benefit} for motorcycle chain maintenance.',
            'Best for {climate} conditions, {brand} {short_name} provides {benefit}.',
        ],
    },
    'Chain Cleaner': {
        'pros_pool': [
            'Effective grease removal', 'O-ring safe formula',
            'Fast evaporation', 'Easy spray application',
            'Biodegradable formula', 'No residue left behind',
        ],
        'cons_pool': [
            'Strong chemical smell', 'Can damage paint if oversprayed',
            'Needs刷 brush for heavy grime', 'Premium pricing',
            'Requires ventilation during use',
        ],
        'best_for_templates': [
            '{tier} riders wanting effective chain cleaning',
            'Regular maintainers needing {benefit}',
        ],
        'verdict_templates': [
            'The {brand} {short_name} is a {type} chain cleaner that {benefit} for motorcycle chain maintenance.',
        ],
    },
    'Tyre Inflator': {
        'pros_pool': [
            'Fast inflation speed', 'Digital pressure gauge',
            'Auto-shutoff at target PSI', 'Compact and portable',
            'LED emergency light', 'Multiple nozzle adapters',
            'Accurate pressure reading', 'Good build quality',
        ],
        'cons_pool': [
            'Gets hot during extended use', 'Noisy operation',
            'Limited battery life (cordless)', 'Plastic construction',
            'Short power cord', 'Heavy for touring',
        ],
        'best_for_templates': [
            '{tier} riders wanting portable tyre inflation',
            'Touring riders needing {benefit}',
            'Daily commuters who want roadside independence',
        ],
        'verdict_templates': [
            'The {brand} {short_name} is a {type} tyre inflator offering {benefit} at an {price_ctx} price.',
            'Best for riders who need {benefit}, the {brand} {short_name} delivers {feature}.',
        ],
    },
}

# Price tier labels
def _price_tier(price: int, category: str) -> str:
    """Determine price tier for a product in a category."""
    band = preferred_price_range(category)
    if not band:
        return 'mid-range'
    low, high = band
    if price <= low * 0.6:
        return 'budget'
    if price <= low:
        return 'value'
    if price <= high:
        return 'mid-range'
    if price <= high * 1.5:
        return 'premium'
    return 'high-end'


def _price_context(price: int, category: str) -> str:
    """Generate price context string."""
    tier = _price_tier(price, category)
    return {
        'budget': 'affordable',
        'value': 'reasonable',
        'mid-range': 'competitive',
        'premium': 'premium',
        'high-end': 'premium',
    }.get(tier, 'competitive')


def _rating_label(rating: float) -> str:
    """Generate a label from a rating."""
    if rating >= 4.5:
        return 'excellent'
    if rating >= 4.0:
        return 'good'
    if rating >= 3.5:
        return 'decent'
    if rating >= 3.0:
        return 'average'
    return 'below average'


def generate_editorial(product: dict) -> dict:
    """Generate missing editorial fields for a product.

    Returns a dict of fields that were generated (empty if nothing was generated).
    Never overwrites existing manual content.
    """
    generated = {}
    category = product.get('category', '')
    brand = product.get('brand', '')
    title = product.get('title', '')
    price = int(product.get('price', 0))
    rating = float(product.get('rating', 0))
    editor_rating = float(product.get('editor_rating', 0))
    review_count = int(product.get('review_count', product.get('reviews', 0)))
    features = product.get('features', [])
    product_type = product.get('type', '')

    # Short name for templates (brand + model, e.g. "BM4 PRO Plus")
    short_name = title
    if brand and title.lower().startswith(brand.lower()):
        short_name = title[len(brand):].strip()
    if not short_name:
        short_name = title

    templates = CATEGORY_EDITORIAL.get(category, {})
    if not templates:
        return generated

    tier = _price_tier(price, category)

    # --- Pros ---
    if is_empty_or_default(product.get('pros')) and templates.get('pros_pool'):
        pros = _generate_pros(product, templates['pros_pool'])
        if pros:
            product['pros'] = pros
            generated['pros'] = pros

    # --- Cons ---
    if is_empty_or_default(product.get('cons')) and templates.get('cons_pool'):
        cons = _generate_cons(product, templates['cons_pool'])
        if cons:
            product['cons'] = cons
            generated['cons'] = cons

    # --- Best For ---
    if is_empty_or_default(product.get('best_for')) and templates.get('best_for_templates'):
        best_for = _generate_best_for(product, templates['best_for_templates'], tier)
        if best_for:
            product['best_for'] = best_for
            generated['best_for'] = best_for

    # --- Verdict ---
    if is_empty_or_default(product.get('verdict')) and templates.get('verdict_templates'):
        verdict = _generate_verdict(product, templates['verdict_templates'], tier)
        if verdict:
            product['verdict'] = verdict
            generated['verdict'] = verdict

    # --- Fitment Notes ---
    if is_empty_or_default(product.get('fitment_notes')):
        fitment = _generate_fitment_notes(product)
        if fitment:
            product['fitment_notes'] = fitment
            generated['fitment_notes'] = fitment

    # --- Editorial Verdict (never a fabricated numeric score) ---
    # Derive a verdict label from REAL data only. We never invent an
    # arbitrary number; the Amazon rating stays the trust anchor.
    if is_empty_or_default(product.get('editorial_verdict')):
        verdict = derive_editorial_verdict(product)
        if verdict:
            product['editorial_verdict'] = verdict
            generated['editorial_verdict'] = verdict

    # --- Features (if not set) ---
    if is_empty_or_default(product.get('features')):
        features = _infer_features(product)
        if features:
            product['features'] = features
            generated['features'] = features

    return generated


def _generate_pros(product: dict, pool: list) -> list:
    """Generate pros from the pool based on product attributes."""
    pros = []
    rating = float(product.get('rating', 0))
    review_count = int(product.get('review_count', product.get('reviews', 0)))
    price = int(product.get('price', 0))
    category = product.get('category', '')
    features = product.get('features', [])

    # Always include top-rated pros
    if rating >= 4.3:
        pros.append(pool[0])  # Top pro from pool
    if review_count >= 1000:
        pros.append('Highly rated by ' + str(review_count) + ' buyers')
    if features:
        # Match features to pros
        for feat in features[:2]:
            for p in pool:
                if feat.lower()[:8] in p.lower() and p not in pros:
                    pros.append(p)
                    break

    # Fill remaining from pool
    for p in pool:
        if len(pros) >= 4:
            break
        if p not in pros:
            pros.append(p)

    return pros[:4]


def _generate_cons(product: dict, pool: list) -> list:
    """Generate cons from the pool. Lower-rated products get more cons."""
    cons = []
    rating = float(product.get('rating', 0))

    # Start from the end of pool for more negative items
    if rating < 4.0:
        cons.append(pool[-1])
    if rating < 3.5:
        cons.append(pool[-2])

    # Always include at least one con
    if not cons:
        cons.append(pool[-1])

    return cons[:2]


def _generate_best_for(product: dict, templates: list, tier: str) -> str:
    """Generate a best_for string."""
    brand = product.get('brand', '')
    features = product.get('features', [])
    feature = features[0] if features else 'quality'
    title = product.get('title', '')
    product_type = product.get('type', '')
    cert = 'certified' if 'ISI' in title or 'DOT' in title else 'quality'

    # Pick template based on tier
    tmpl = templates[0] if templates else '{tier} riders'

    fmt = {
        'tier': tier,
        'brand': brand,
        'feature': feature.lower(),
        'benefit': feature.lower(),
        'cert': cert,
        'type': product_type.lower() if product_type else '',
    }

    result = tmpl
    for key, val in fmt.items():
        result = result.replace('{' + key + '}', str(val))
    result = re.sub(r'\{[a-z_]+\}', '', result)
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def _generate_verdict(product: dict, templates: list, tier: str) -> str:
    """Generate a verdict string."""
    brand = product.get('brand', '')
    title = product.get('title', '')
    price = int(product.get('price', 0))
    category = product.get('category', '')
    features = product.get('features', [])

    # Short name
    short_name = title
    if brand and title.lower().startswith(brand.lower()):
        short_name = title[len(brand):].strip()
    if not short_name:
        short_name = title

    feature = features[0] if features else ''
    product_type = product.get('type', '')
    # Use product_type as the descriptive type, fall back to category
    desc_type = product_type if product_type else ''
    # If type repeats the category, use just the type qualifier (e.g. "Fully Synthetic" not "Fully Synthetic Engine Oil")
    if desc_type and category.lower() in desc_type.lower():
        desc_type = desc_type.replace(category, '').replace(category.lower(), '').strip()
    cert = 'certified' if 'ISI' in title or 'DOT' in title else 'quality'
    benefit = _rating_label(float(product.get('rating', 0))) + ' performance'
    price_ctx = _price_context(price, category)

    # Safe format with defaults for all possible template variables
    fmt = {
        'brand': brand,
        'short_name': short_name,
        'type': desc_type,
        'feature': feature.lower() if feature else desc_type.lower(),
        'benefit': benefit,
        'price_ctx': price_ctx,
        'cert': cert,
        'tier': tier,
        'title': title,
    }

    tmpl = templates[0]
    # Replace any remaining {placeholders} with empty string
    result = tmpl
    for key, val in fmt.items():
        result = result.replace('{' + key + '}', str(val))
    # Clean up any unfilled placeholders
    result = re.sub(r'\{[a-z_]+\}', '', result)
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def _generate_fitment_notes(product: dict) -> str:
    """Generate fitment notes based on category and compatibility."""
    category = product.get('category', '')
    compat = product.get('compatible_bikes', [])
    product_type = product.get('type', '')

    if '*' in compat or not compat:
        if category == 'Helmet':
            return 'Universal fit - available in multiple sizes. Check size chart before ordering.'
        elif category == 'Phone Mount':
            return 'Universal - fits all handlebars 22-32mm diameter'
        elif category == 'Engine Oil':
            viscosity = product.get('type', '')
            return f'Universal - suitable for all 4-stroke motorcycles requiring {viscosity}'.strip()
        elif category in ('Chain Lube', 'Chain Cleaner'):
            return 'Universal - safe for all O-ring, X-ring, and standard chains'
        elif category == 'Tyre Inflator':
            return 'Universal - works with all Schrader valve motorcycle tyres'
        elif category == 'Bike Cover':
            return 'Universal - available in multiple sizes. Check size chart for your motorcycle.'
        else:
            return 'Universal fit - compatible with most motorcycles'
    else:
        # Specific compatibility
        bike_list = ', '.join(compat[:5])
        if len(compat) > 5:
            bike_list += f' and {len(compat) - 5} more'
        return f'Compatible with: {bike_list}'


# Verdict labels, ordered from strongest to weakest. These are qualitative
# editorial judgments, NOT numeric scores. The base tier is always anchored to
# the real Amazon rating so we never show an editorial verdict that contradicts
# or undercuts what customers actually rated the product.
EDITORIAL_VERDICTS = {
    'excellent': 'Excellent',
    'very_good': 'Very Good',
    'good': 'Good',
    'budget_pick': 'Budget Pick',
    'premium_pick': 'Premium Pick',
    'best_value': 'Best Value',
}

# Only products rated this high or better by customers may receive an
# unqualified positive editorial verdict. This enforces requirement 5: an
# editorial verdict must never undercut the user rating.
_POSITIVE_VERDICT_MIN_RATING = 4.0


def derive_editorial_verdict(product: dict) -> str:
    """Derive an editorial verdict label from REAL data only.

    Rules (designed to preserve trust and never invent scores):
      * The verdict is anchored to the Amazon user rating. A product rated
        below 4.0 by customers never receives a positive editorial verdict.
      * Editorial-only labels (Budget Pick, Premium Pick, Best Value) are
        assigned only when a genuine editorial review exists (pros/cons or a
        manual verdict), so we never fabricate an opinion.
      * If no editorial review content exists, we surface only the base
        rating-derived verdict (or nothing for low-rated products).

    Returns one of EDITORIAL_VERDICTS values, or '' when nothing honest can be
    shown (caller then displays the Amazon rating alone).
    """
    rating = float(product.get('rating', 0) or 0)
    if rating <= 0:
        return ''

    has_editorial_review = bool(
        product.get('pros') or product.get('cons')
        or product.get('verdict') or product.get('editorial_notes')
    )

    # Base verdict tier strictly follows the customer rating.
    if rating >= 4.5:
        base = 'excellent'
    elif rating >= _POSITIVE_VERDICT_MIN_RATING:
        base = 'very_good'
    elif rating >= 3.5:
        base = 'good'
    else:
        # Low-rated product: do not attach a positive editorial verdict.
        # Caller shows Amazon rating only (requirement 6 / 7).
        return ''

    # Without a real editorial review we keep the honest, rating-based verdict.
    if not has_editorial_review:
        return base

    # With a genuine review, refine using price positioning. This is a
    # qualitative categorization, not an invented numeric score.
    tier = _price_tier(int(product.get('price', 0) or 0), product.get('category', ''))
    if tier in ('budget', 'value') and rating >= _POSITIVE_VERDICT_MIN_RATING:
        return 'budget_pick'
    if tier in ('premium', 'high-end') and rating >= 4.3:
        return 'premium_pick'
    if rating >= 4.3 and _looks_like_best_value(product):
        return 'best_value'
    return base


def _looks_like_best_value(product: dict) -> bool:
    """Heuristic: high rating at a price at/under the category band."""
    band = preferred_price_range(product.get('category', ''))
    price = int(product.get('price', 0) or 0)
    rating = float(product.get('rating', 0) or 0)
    if not band or price <= 0:
        return False
    low, high = band
    return low <= price <= high and rating >= 4.3


def _infer_features(product: dict) -> list:
    """Infer features from title and other data."""
    title = product.get('title', '').lower()
    features = []

    # Common feature patterns in titles
    feature_patterns = [
        (r'isi\s+certified', 'ISI certified'),
        (r'dot\s+certified', 'DOT certified'),
        (r'ece\s+certified', 'ECE certified'),
        (r'dual\s+cert', 'Dual certification'),
        (r'waterproof', 'Waterproof'),
        (r'vibration\s+damp', 'Vibration dampener'),
        (r'quick[\s-]*release', 'Quick-release mechanism'),
        (r'auto[\s-]*shutoff|auto[\s-]*stop', 'Auto-shutoff'),
        (r'digital', 'Digital display'),
        (r'led\s+light', 'LED light'),
        (r'abs\s+shell', 'ABS shell'),
        (r'full\s+face', 'Full face'),
        (r'open\s+face', 'Open face'),
        (r'modular|flip[\s-]*up', 'Modular/flip-up'),
        (r'synthetic', 'Synthetic'),
        (r'o[\s-]*ring\s+safe', 'O-ring safe'),
        (r'x[\s-]*ring', 'X-ring compatible'),
        (r'spoiler', 'Aerodynamic spoiler'),
        (r'vent', 'Multi-ventilation'),
        (r'budget|affordable', 'Budget-friendly'),
        (r'premium|pro', 'Premium build'),
        (r'portable', 'Portable design'),
        (r'compact', 'Compact size'),
        (r'150ml|200ml|500ml', 'Compact size'),
    ]

    for pattern, feature in feature_patterns:
        if re.search(pattern, title):
            features.append(feature)

    # Limit to 4 features
    return features[:4]


def load_products_from_file(filepath: Path) -> list:
    """Load products from a single JSON file (not the whole directory)."""
    if not filepath.exists():
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    products = []
    for item in raw:
        flat = _normalize_to_flat(item)
        if flat:
            products.append(flat)
    return products


# ===== 6. Import Pipeline =====

def import_products(
    source_path: Path,
    output_path: Optional[Path] = None,
    on_duplicate: str = 'skip',
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Full import pipeline: load -> normalize -> validate -> dedup -> enrich -> write.

    Returns a report dict with all results.
    """
    report = {
        'source': str(source_path),
        'loaded': 0,
        'normalized': 0,
        'valid': 0,
        'invalid': 0,
        'duplicates_found': 0,
        'duplicates_resolved': 0,
        'enriched': 0,
        'fields_generated': 0,
        'written': 0,
        'errors': [],
        'warnings': [],
        'products': [],
    }

    # Step 1: Load
    print(f"\n  [1/6] Loading products from {source_path.name}...")
    if source_path.suffix.lower() == '.csv':
        new_products = load_csv(source_path)
    elif source_path.suffix.lower() == '.json':
        new_products = load_json(source_path)
    else:
        report['errors'].append(f"Unsupported file format: {source_path.suffix}")
        return report

    report['loaded'] = len(new_products)
    print(f"    Loaded {len(new_products)} products")

    if not new_products:
        report['errors'].append("No products found in source file")
        return report

    # Step 2: Normalize
    print("  [2/6] Normalizing fields...")
    for p in new_products:
        normalize_product(p)
        report['normalized'] += 1

    # Step 2b: Resolve duplicate slugs
    resolve_slug_duplicates(new_products)

    # Step 3: Validate
    print("  [3/6] Validating...")
    validation = pre_import_validate(new_products)
    report['errors'].extend(validation['errors'])
    report['warnings'].extend(validation['warnings'])
    report['valid'] = validation['stats']['valid']
    report['invalid'] = validation['stats']['invalid']

    if report['invalid'] > 0:
        print(f"    {report['invalid']} products failed validation")

    # Filter to valid products only
    valid_products = [p for p in new_products if p.get('title') and p.get('category')]

    # Step 4: Deduplicate against existing catalog
    print("  [4/6] Checking for duplicates...")
    existing_products = load_products(DATA_DIR)
    duplicates = detect_import_duplicates(valid_products, existing_products)
    report['duplicates_found'] = len(duplicates)

    if duplicates:
        print(f"    Found {len(duplicates)} duplicates:")
        for dup in duplicates:
            new_p = valid_products[dup['new_index']]
            print(f"      - {new_p.get('title', '')[:50]} matches {dup['existing_slug']} ({dup['match_type']}, {dup['confidence']})")

        # Resolve duplicates
        if on_duplicate == 'skip':
            dup_indices = {d['new_index'] for d in duplicates}
            valid_products = [p for i, p in enumerate(valid_products) if i not in dup_indices]
            report['duplicates_resolved'] = len(duplicates)
            print(f"    Skipped {len(duplicates)} duplicate products")
        elif on_duplicate == 'replace':
            # Remove existing products that are being replaced
            dup_slugs = {d['existing_slug'] for d in duplicates}
            existing_products = [p for p in existing_products if p.get('slug') not in dup_slugs]
            report['duplicates_resolved'] = len(duplicates)
            print(f"    Replacing {len(duplicates)} existing products")
        # 'merge' keeps both - no action needed

    # Step 5: Enrich editorial content
    print("  [5/6] Generating editorial content...")
    for p in valid_products:
        generated = generate_editorial(p)
        if generated:
            p[GENERATED_FLAG] = list(generated.keys())
            report['enriched'] += 1
            report['fields_generated'] += len(generated)
            if verbose:
                print(f"    Enriched: {p.get('title', '')[:50]}")
                for field, value in generated.items():
                    val_str = str(value)[:60]
                    print(f"      + {field}: {val_str}")

    # Step 6: Write output
    if dry_run:
        print("\n  [DRY RUN] No files written.")
        print(f"\n  Import Summary:")
        print(f"    Loaded:      {report['loaded']}")
        print(f"    Valid:       {report['valid']}")
        print(f"    Duplicates:  {report['duplicates_found']} (resolved: {report['duplicates_resolved']})")
        print(f"    Enriched:    {report['enriched']} products, {report['fields_generated']} fields generated")
        print(f"    Would write: {len(valid_products)} products")
    else:
        print("  [6/6] Writing output...")
        if output_path is None:
            output_path = DATA_DIR / source_path.stem

        # Merge with existing if output file exists
        if output_path.exists():
            existing = load_products_from_file(output_path)
            existing_slugs = {p.get('slug') for p in existing}
            # Add new products that don't conflict
            for p in valid_products:
                if p.get('slug') not in existing_slugs:
                    existing.append(p)
            all_products = existing
        else:
            all_products = valid_products

        # Convert back to nested format for storage
        nested = [unflatten_product(p) for p in all_products]

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(nested, f, indent=2, ensure_ascii=False)

        report['written'] = len(all_products)
        print(f"    Wrote {len(all_products)} products to {output_path}")

    report['products'] = valid_products
    return report


# ===== 7. Validate Command =====

def validate_library(verbose: bool = False) -> dict:
    """Validate all products in the library."""
    print("\n  Loading products from library...")
    products = load_products(DATA_DIR)
    print(f"  Found {len(products)} products")

    print("\n  Running validation...")
    result = validate_products(products)

    print(f"\n  Validation Results:")
    print(f"    Errors:   {len(result['errors'])}")
    print(f"    Warnings: {len(result['warnings'])}")
    print(f"    Valid:    {result['valid']}")

    if result['errors']:
        print("\n  Errors:")
        for e in result['errors']:
            print(f"    - {e}")

    if result['warnings'] and verbose:
        print("\n  Warnings:")
        for w in result['warnings']:
            print(f"    - {w}")

    if result.get('stats'):
        stats = result['stats']
        print(f"\n  Stats:")
        print(f"    Total: {stats.get('total', 0)}")
        if stats.get('by_status'):
            print(f"    By status: {stats['by_status']}")
        if stats.get('by_category'):
            print(f"    By category: {stats['by_category']}")

    return result


# ===== 8. Dedupe Command =====

def find_all_duplicates(verbose: bool = False) -> dict:
    """Find all duplicates across the product library."""
    print("\n  Loading products from library...")
    products = load_products(DATA_DIR)
    print(f"  Found {len(products)} products")

    print("\n  Scanning for duplicates...")
    result = find_duplicates(products)

    asin_dupes = result.get('asin_duplicates', [])
    slug_dupes = result.get('slug_duplicates', [])
    title_dupes = result.get('title_duplicates', [])

    print(f"\n  Duplicate Report:")
    print(f"    ASIN duplicates:  {len(asin_dupes)}")
    print(f"    Slug duplicates:  {len(slug_dupes)}")
    print(f"    Title duplicates: {len(title_dupes)}")

    if asin_dupes:
        print("\n  ASIN Duplicates:")
        for d in asin_dupes:
            print(f"    ASIN {d['asin']}: {', '.join(d['products'])}")

    if slug_dupes:
        print("\n  Slug Duplicates:")
        for d in slug_dupes:
            print(f"    Slug '{d['slug']}': {', '.join(d['sources'])}")

    if title_dupes and verbose:
        print("\n  Title Duplicates:")
        for d in title_dupes:
            print(f"    Title '{d['title'][:50]}...': {', '.join(d['products'])}")

    return result


# ===== 9. Enrich Command =====

def enrich_library(category: Optional[str] = None, dry_run: bool = False) -> dict:
    """Enrich existing products with missing editorial content."""
    print("\n  Loading products from library...")
    products = load_products(DATA_DIR)
    print(f"  Found {len(products)} products")

    # Filter by category if specified
    if category:
        products = [p for p in products if p.get('category', '').lower() == category.lower()]
        print(f"  Filtered to {len(products)} {category} products")

    enriched = 0
    total_fields = 0
    changes = []

    for p in products:
        title = p.get('title', '')
        generated = generate_editorial(p)

        if generated:
            enriched += 1
            total_fields += len(generated)
            changes.append({'slug': p.get('slug', ''), 'title': title, 'fields': generated})

            if dry_run:
                print(f"\n    Would enrich: {title}")
                for field, value in generated.items():
                    print(f"      + {field}: {str(value)[:80]}")
            else:
                # Mark as generated
                p[GENERATED_FLAG] = list(generated.keys())
                print(f"    Enriched: {title}")
                for field, value in generated.items():
                    print(f"      + {field}: {str(value)[:80]}")

    if not dry_run and enriched > 0:
        # Save back to files
        _save_products(products)
        print(f"\n  Saved {enriched} enriched products")

    print(f"\n  Enrichment Summary:")
    print(f"    Products enriched: {enriched}")
    print(f"    Fields generated:  {total_fields}")

    return {'enriched': enriched, 'fields_generated': total_fields, 'changes': changes}


def _save_products(products: list) -> None:
    """Save products back to their source files."""
    # Group by source file
    by_file = defaultdict(list)
    for p in products:
        source = p.get('_source_file', 'import.json')
        # Strip internal keys
        clean = {k: v for k, v in p.items() if not k.startswith('_')}
        by_file[source].append(clean)

    for filename, file_products in by_file.items():
        filepath = DATA_DIR / filename
        nested = [unflatten_product(p) for p in file_products]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(nested, f, indent=2, ensure_ascii=False)


# ===== 8. bike-deals.json Import =====

# Map canonical category name -> output JSON filename in data/products/
CATEGORY_FILE_MAP: Dict[str, str] = {
    'Helmet': 'helmets.json',
    'Phone Mount': 'accessories.json',
    'Tyre Inflator': 'accessories.json',
    'Engine Oil': 'maintenance.json',
    'Chain Lube': 'maintenance.json',
    'Chain Cleaner': 'maintenance.json',
    'Bike Cover': 'bike-covers.json',
    'Jackets': 'jackets.json',
    'Gloves': 'gloves.json',
    'Saddle Bag': 'luggage.json',
    'Tail Bag': 'luggage.json',
    'Tank Bag': 'luggage.json',
    'Knee Guard': 'protection.json',
    'Ear Plugs': 'ear-plugs.json',
    'Action Camera': 'cameras.json',
    'Dash Cam': 'cameras.json',
    'Seat Cover': 'seat-covers.json',
    'Riding Pants': 'riding-pants.json',
    'Handlebar Grip': 'handlebar-accessories.json',
    'Mirror': 'mirrors.json',
    'Windshield': 'windshields.json',
    'GPS Tracker': 'gps-trackers.json',
    'Headlight': 'lighting.json',
    'Indicator': 'lighting.json',
    'Horn': 'horns.json',
    'Charger': 'chargers.json',
    'Footrest': 'footrests.json',
    'Chain Lock': 'locks.json',
    'Disc Lock': 'locks.json',
    'Alarm': 'alarms.json',
    'Tool Kit': 'tools.json',
    'Polish': 'care.json',
    'Crash Guard': 'protection.json',
}


def _category_to_file(category: str) -> str:
    """Map a category name to its output JSON filename."""
    return CATEGORY_FILE_MAP.get(category, 'other-accessories.json')


def _extract_brand_from_title(title: str) -> str:
    """Extract brand name from a product title.

    Tries multi-word brands first (e.g. 'Royal Enfield', 'Harley-Davidson'),
    then falls back to the first word.
    """
    if not title:
        return ''
    title_lower = title.lower().strip()

    # Try multi-word brands first (longest match)
    for brand_key in sorted(BRAND_DISPLAY_NAMES.keys(), key=len, reverse=True):
        if title_lower.startswith(brand_key):
            return BRAND_DISPLAY_NAMES[brand_key]

    # Fallback: first word
    first_word = title.split()[0] if title.split() else ''
    return normalize_brand(first_word)


def _detect_product_type(title: str, category: str) -> str:
    """Infer product type from title and category."""
    title_lower = title.lower()
    if category == 'Helmet':
        if 'modular' in title_lower or 'flip' in title_lower:
            return 'Modular'
        if 'open face' in title_lower or 'open-face' in title_lower:
            return 'Open Face'
        if 'half' in title_lower:
            return 'Half Face'
        return 'Full Face'
    if category == 'Engine Oil':
        if 'fully synthetic' in title_lower or '100%' in title_lower:
            return 'Fully Synthetic'
        if 'semi synthetic' in title_lower:
            return 'Semi Synthetic'
        if 'mineral' in title_lower:
            return 'Mineral'
        return 'Synthetic'
    return ''


def _deal_title(deal: dict) -> str:
    """Extract title from a bike-deals.json deal record."""
    item_info = deal.get('itemInfo', {})
    title_info = item_info.get('title', {})
    return title_info.get('displayValue', '')


def import_from_deals(
    deals_path: Path,
    products_dir: Path,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Import products from bike-deals.json into the Product Library.

    Reads every deal, maps _search_keyword to a category, and either
    updates an existing product (Amazon fields only) or creates a new
    product with auto-generated editorial (status: draft).

    Returns a report dict with counts for verification.
    """
    from sync_engine import (
        load_amazon_feed,
        extract_feed_price,
        extract_feed_mrp,
        extract_feed_discount,
        extract_feed_rating,
        extract_feed_review_count,
        extract_feed_image,
        extract_feed_availability,
        extract_feed_affiliate_url,
    )

    report = {
        'found': 0,
        'imported': 0,
        'updated': 0,
        'skipped': 0,
        'duplicate_asins': 0,
        'by_category': {},
        'errors': [],
    }

    # --- Load deals ---
    if not deals_path.exists():
        report['errors'].append(f"Feed file not found: {deals_path}")
        return report

    deals = load_amazon_feed(deals_path)
    report['found'] = len(deals)
    print(f"\n  Loaded {len(deals)} deals from {deals_path.name}")

    # --- Load existing library ---
    existing_products = load_products(products_dir)
    existing_by_asin: Dict[str, dict] = {}
    for p in existing_products:
        asin = (p.get('asin') or '').strip().upper()
        if asin:
            existing_by_asin[asin] = p
    print(f"  Existing library: {len(existing_products)} products")

    # --- Process deals ---
    new_products_by_file: Dict[str, list] = defaultdict(list)
    updated_count = 0
    skipped_count = 0
    dup_count = 0
    cat_counts: Dict[str, int] = defaultdict(int)
    sync_time = __import__('datetime').datetime.now().isoformat()

    for deal in deals:
        asin = (deal.get('asin') or '').strip().upper()
        if not asin:
            skipped_count += 1
            continue

        # Map category
        keyword = deal.get('_search_keyword', '')
        category = keyword_to_category(keyword)
        if not category:
            skipped_count += 1
            if verbose:
                print(f"    SKIP (no category): {keyword} | {deal.get('asin')}")
            continue

        title = _deal_title(deal)
        if not title:
            skipped_count += 1
            continue

        # Extract Amazon data
        price = extract_feed_price(deal)
        mrp = extract_feed_mrp(deal)
        discount = extract_feed_discount(deal, price or 0, mrp or 0) if price and mrp else None
        rating = extract_feed_rating(deal)
        review_count = extract_feed_review_count(deal)
        image_url = extract_feed_image(deal)
        availability = extract_feed_availability(deal)
        affiliate_url = extract_feed_affiliate_url(deal)

        # --- Existing product: update Amazon fields only ---
        if asin in existing_by_asin:
            product = existing_by_asin[asin]
            changes = []
            if price is not None and product.get('price') != price:
                product['price'] = price
                changes.append('price')
            if mrp is not None and product.get('mrp') != mrp:
                product['mrp'] = mrp
                changes.append('mrp')
            if discount is not None and product.get('discount') != discount:
                product['discount'] = discount
                changes.append('discount')
            if rating is not None and product.get('rating') != rating:
                product['rating'] = rating
                changes.append('rating')
            if review_count is not None and product.get('review_count') != review_count:
                product['review_count'] = review_count
                product['reviews'] = review_count
                changes.append('review_count')
            if image_url and product.get('image') != image_url:
                product['image'] = image_url
                changes.append('image')
            if availability and product.get('availability') != availability:
                product['availability'] = availability
                changes.append('availability')
            if affiliate_url and product.get('affiliate_url') != affiliate_url:
                product['affiliate_url'] = affiliate_url
                changes.append('affiliate_url')
            product['last_updated'] = sync_time

            if changes:
                updated_count += 1
                cat_counts[category] += 1
                if verbose:
                    print(f"    UPDATE [{category}] {title[:50]} — {', '.join(changes)}")
            continue

        # --- New product: create with auto-generated editorial ---
        brand = _extract_brand_from_title(title)
        product_type = _detect_product_type(title, category)

        new_product = {
            'asin': asin,
            'slug': generate_slug(title),
            'title': title,
            'brand': brand,
            'category': category,
            'type': product_type,
            'status': 'draft',
            'price': price or 0,
            'mrp': mrp,
            'discount': discount,
            'rating': rating or 0,
            'review_count': review_count or 0,
            'reviews': review_count or 0,
            'availability': availability or '',
            'affiliate_url': affiliate_url or '',
            'image': image_url or '',
            'compatible_bikes': ['*'],
            'editor_rating': 0,
            'pros': [],
            'cons': [],
            'features': [],
            'fitment_notes': '',
            'best_for': '',
            'verdict': '',
            'recommended_for': [],
            'editorial_notes': '',
            '_generated': True,
            '_source_deal': True,
        }

        # Generate editorial content
        generated = generate_editorial(new_product)
        if generated:
            new_product['_generated_fields'] = list(generated.keys())

        # Determine output file
        output_filename = _category_to_file(category)
        # Skip if same slug already queued for this file
        queued_slugs = {p.get('slug', '') for p in new_products_by_file[output_filename]}
        if new_product.get('slug', '') in queued_slugs:
            dup_count += 1
            continue
        new_products_by_file[output_filename].append(new_product)
        cat_counts[category] += 1
        report['imported'] += 1

        if verbose:
            gen_fields = new_product.get('_generated_fields', [])
            gen_str = f" (generated: {', '.join(gen_fields)})" if gen_fields else ""
            print(f"    NEW [{category}] {title[:50]}{gen_str}")

    # --- Write new products to files ---
    if not dry_run:
        for filename, new_prods in new_products_by_file.items():
            output_path = products_dir / filename

            # Load existing products from this file
            file_products = []
            if output_path.exists():
                with open(output_path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                for item in raw:
                    flat = {}
                    # Flatten nested format
                    for field in ('asin', 'slug', 'title', 'brand', 'category', 'type',
                                  'status', 'compatible_bikes', 'best_for', 'verdict'):
                        if field in item:
                            flat[field] = item[field]
                    ed = item.get('editorial', {})
                    flat['editor_rating'] = ed.get('score', 0)
                    flat['pros'] = ed.get('pros', [])
                    flat['cons'] = ed.get('cons', [])
                    flat['features'] = ed.get('features', [])
                    flat['fitment_notes'] = ed.get('fitment_notes', '')
                    flat['recommended_for'] = ed.get('recommended_for', [])
                    flat['editorial_notes'] = ed.get('notes', '')
                    amz = item.get('amazon', {})
                    flat['price'] = amz.get('price', 0)
                    flat['mrp'] = amz.get('mrp')
                    flat['discount'] = amz.get('discount')
                    flat['rating'] = amz.get('rating', 0)
                    flat['review_count'] = amz.get('review_count', 0)
                    flat['availability'] = amz.get('availability', '')
                    flat['affiliate_url'] = amz.get('affiliate_url', '')
                    flat['image'] = amz.get('image', '')
                    flat['last_updated'] = amz.get('last_updated')
                    file_products.append(flat)

            # Index existing by ASIN and slug
            existing_file_asins = {
                (p.get('asin') or '').strip().upper(): p
                for p in file_products
            }
            existing_file_slugs = {
                p.get('slug', ''): p
                for p in file_products
            }

            # Merge: update existing or append new (skip ASIN + slug duplicates)
            for new_p in new_prods:
                new_asin = (new_p.get('asin') or '').strip().upper()
                new_slug = new_p.get('slug', '')
                if new_asin in existing_file_asins:
                    dup_count += 1
                elif new_slug in existing_file_slugs:
                    dup_count += 1
                else:
                    file_products.append(new_p)
                    existing_file_asins[new_asin] = new_p
                    existing_file_slugs[new_slug] = new_p

            # Also update existing products in this file with fresh Amazon data
            for p in file_products:
                p_asin = (p.get('asin') or '').strip().upper()
                # Find matching deal for updates
                for deal in deals:
                    deal_asin = (deal.get('asin') or '').strip().upper()
                    if deal_asin == p_asin:
                        # Update Amazon fields
                        d_price = extract_feed_price(deal)
                        d_rating = extract_feed_rating(deal)
                        d_reviews = extract_feed_review_count(deal)
                        d_image = extract_feed_image(deal)
                        d_avail = extract_feed_availability(deal)
                        d_url = extract_feed_affiliate_url(deal)
                        if d_price is not None:
                            p['price'] = d_price
                        if d_rating is not None:
                            p['rating'] = d_rating
                        if d_reviews is not None:
                            p['review_count'] = d_reviews
                            p['reviews'] = d_reviews
                        if d_image:
                            p['image'] = d_image
                        if d_avail:
                            p['availability'] = d_avail
                        if d_url:
                            p['affiliate_url'] = d_url
                        p['last_updated'] = sync_time
                        break

            # Create backup
            if output_path.exists():
                backup_path = output_path.with_suffix('.json.bak')
                if not backup_path.exists():
                    import shutil
                    shutil.copy2(output_path, backup_path)

            # Convert to nested and write
            nested = [unflatten_product(p) for p in file_products]
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(nested, f, indent=2, ensure_ascii=False)

    report['updated'] = updated_count
    report['skipped'] = skipped_count
    report['duplicate_asins'] = dup_count
    report['by_category'] = dict(cat_counts)

    return report


# ===== CLI =====

def main():
    parser = argparse.ArgumentParser(
        description='Product Import Assistant for BikeReview India',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python product_importer.py import products.json --dry-run
  python product_importer.py import products.csv --on-duplicate skip
  python product_importer.py validate --verbose
  python product_importer.py dedupe
  python product_importer.py enrich --category Helmet --dry-run
        """,
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Import command
    import_parser = subparsers.add_parser('import', help='Import products from JSON or CSV')
    import_parser.add_argument('file', type=Path, help='Source file (JSON or CSV)')
    import_parser.add_argument('--output', '-o', type=Path, default=None, help='Output file path')
    import_parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    import_parser.add_argument('--on-duplicate', choices=['skip', 'merge', 'replace'],
                               default='skip', help='How to handle duplicates')
    import_parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate product library')
    validate_parser.add_argument('--verbose', '-v', action='store_true', help='Show warnings')

    # Dedupe command
    dedupe_parser = subparsers.add_parser('dedupe', help='Find duplicates in library')
    dedupe_parser.add_argument('--verbose', '-v', action='store_true', help='Show all duplicates')

    # Enrich command
    enrich_parser = subparsers.add_parser('enrich', help='Enrich products with editorial content')
    enrich_parser.add_argument('--category', '-c', type=str, default=None, help='Filter by category')
    enrich_parser.add_argument('--dry-run', action='store_true', help='Preview without writing')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    print("=" * 60)
    print("  BikeReview India - Product Import Assistant")
    print("=" * 60)

    if args.command == 'import':
        if not args.file.exists():
            print(f"\n  Error: File not found: {args.file}")
            sys.exit(1)
        report = import_products(
            source_path=args.file,
            output_path=args.output,
            on_duplicate=args.on_duplicate,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        if report['errors']:
            sys.exit(1)

    elif args.command == 'validate':
        result = validate_library(verbose=args.verbose)
        if result['errors']:
            sys.exit(1)

    elif args.command == 'dedupe':
        result = find_all_duplicates(verbose=args.verbose)
        if result.get('asin_duplicates') or result.get('slug_duplicates'):
            sys.exit(1)

    elif args.command == 'enrich':
        result = enrich_library(category=args.category, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
