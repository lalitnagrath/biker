#!/usr/bin/env python3
"""
BikeReview India - Static Site Generator
========================================
Generates a fast, SEO-friendly static website for motorcycle reviews,
buying guides, and maintenance tips.

Usage:
    python generate.py [--base-url URL] [--output DIR]

Dependencies:
    pip install jinja2 markdown pyyaml
"""

import os
import sys
import json
import shutil
import re
import argparse
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    print("Error: jinja2 is required. Install with: pip install jinja2")
    sys.exit(1)

try:
    import markdown
except ImportError:
    print("Error: markdown is required. Install with: pip install markdown")
    sys.exit(1)

try:
    import yaml
except ImportError:
    yaml = None


# ===== Configuration =====
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
TEMPLATES_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'
ARTICLES_DIR = BASE_DIR / 'articles'
OUTPUT_DIR = BASE_DIR / 'site'
AFFILIATE_ID = '0x23uyx-21'
SITE_NAME = 'BikeReview India'
DEFAULT_BASE_URL = ''

# ===== Category Normalization =====
# Maps alias names to canonical category names used in data files
CATEGORY_ALIASES: Dict[str, str] = {
    # Bike Cover variants
    'motorcycle cover': 'Bike Cover',
    'motorcycle body cover': 'Bike Cover',
    'bike body cover': 'Bike Cover',
    'body cover': 'Bike Cover',
    # Phone Mount variants
    'phone holder': 'Phone Mount',
    'mobile holder': 'Phone Mount',
    'mobile holder bike': 'Phone Mount',
    'mobile mount': 'Phone Mount',
    'handlebar mount': 'Phone Mount',
    # Crash Guard variants
    'engine guard': 'Crash Guard',
    'leg guard': 'Crash Guard',
    'crash protection': 'Crash Guard',
    'frame slider': 'Crash Guard',
    # Chain Lube variants
    'chain spray': 'Chain Lube',
    'chain lubricant': 'Chain Lube',
    'chain wax': 'Chain Lube',
    # Chain Cleaner variants
    'chain cleaner spray': 'Chain Cleaner',
    # Tyre Inflator variants
    'air compressor': 'Tyre Inflator',
    'tyre pump': 'Tyre Inflator',
    'air pump': 'Tyre Inflator',
    'portable compressor': 'Tyre Inflator',
    # Gloves variants
    'riding gloves': 'Gloves',
    'bike gloves': 'Gloves',
    'racing gloves': 'Gloves',
    'motorcycle gloves': 'Gloves',
    # Jacket variants
    'riding jacket': 'Jackets',
    'bike jacket': 'Jackets',
    'motorcycle jacket': 'Jackets',
    # Helmet variants
    'full face helmet': 'Helmet',
    'modular helmet': 'Helmet',
    'open face helmet': 'Helmet',
    # Engine Oil variants
    'engine oil 10w-50': 'Engine Oil',
    'engine oil 10w-40': 'Engine Oil',
    'motor oil': 'Engine Oil',
    # Tank Bag variants
    'tank bag motorcycle': 'Tank Bag',
    # Saddle Bag variants
    'saddlebag': 'Saddle Bag',
    'saddle bags': 'Saddle Bag',
    'side bag': 'Saddle Bag',
    # Tail Bag variants
    'rear bag': 'Tail Bag',
    'seat bag': 'Tail Bag',
}


def normalize_category(category: str) -> str:
    """Normalize a product category name using the alias map.
    
    Returns the canonical category name. If no alias is found, returns
    the original category with title case.
    """
    if not category:
        return category
    key = category.strip().lower()
    if key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[key]
    return category.strip().title()


def parse_front_matter(content):
    """Parse YAML front matter from markdown content."""
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                if yaml:
                    meta = yaml.safe_load(parts[1])
                else:
                    meta = {}
                body = parts[2].strip()
                return meta, body
            except Exception:
                pass
    return {}, content


def load_json_file(filepath):
    """Load and return JSON data from file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_all_data():
    """Load all JSON data and markdown articles."""
    data = {
        'brands': [],
        'motorcycles': [],
        'products': [],
        'articles': [],
        'bike_models': [],
    }

    # Load brands
    brands_dir = DATA_DIR / 'brands'
    if brands_dir.exists():
        for f in sorted(brands_dir.glob('*.json')):
            brand = load_json_file(f)
            data['brands'].append(brand)

    # Load motorcycles
    motorcycles_dir = DATA_DIR / 'motorcycles'
    if motorcycles_dir.exists():
        for f in sorted(motorcycles_dir.glob('*.json')):
            bike = load_json_file(f)
            data['motorcycles'].append(bike)

    # Load products
    products_dir = DATA_DIR / 'products'
    if products_dir.exists():
        for f in sorted(products_dir.glob('*.json')):
            products = load_json_file(f)
            if isinstance(products, list):
                data['products'].extend(products)
            else:
                data['products'].append(products)

    # Load bike models catalog (all motorcycles sold in India)
    bike_models_file = DATA_DIR / 'all-motorcycles-india.json'
    if bike_models_file.exists():
        raw = load_json_file(bike_models_file)
        for brand_group in raw.get('brands', []):
            for model in brand_group.get('models', []):
                model['brand'] = brand_group['brand']
                model['brand_country'] = brand_group.get('country', '')
                data['bike_models'].append(model)

    # Load articles
    if ARTICLES_DIR.exists():
        for f in sorted(ARTICLES_DIR.glob('*.md')):
            raw = f.read_text(encoding='utf-8')
            meta, body = parse_front_matter(raw)
            meta['body'] = body
            meta['slug'] = meta.get('slug', f.stem)
            meta['description'] = meta.get('title', '')
            data['articles'].append(meta)

    return data


def load_bike_deals():
    """Load bike-deals.json and index by ASIN for quick lookup."""
    deals_file = BASE_DIR / 'bike-deals.json'
    if not deals_file.exists():
        print("  Warning: bike-deals.json not found at project root")
        return {}
    
    with open(deals_file, 'r', encoding='utf-8') as f:
        deals = json.load(f)
    
    # Index by ASIN
    deals_by_asin = {}
    for deal in deals:
        asin = deal.get('asin', '')
        if asin:
            deals_by_asin[asin] = deal
    
    print(f"  Loaded {len(deals_by_asin)} products from bike-deals.json")
    return deals_by_asin


def download_image(url, save_path, timeout=30):
    """Download image from URL and save locally."""
    try:
        # Create parent directory
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Download with user-agent header
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
        
        # Save to file
        with open(save_path, 'wb') as f:
            f.write(data)
        
        return True
    except Exception as e:
        print(f"    Warning: Failed to download {url}: {e}")
        return False


def merge_bike_deals(products, deals_by_asin):
    """Merge bike-deals data into products: images from all matches, prices only from ASIN matches.
    
    Matching priority:
    1. ASIN match — high confidence, updates everything (price, image, affiliate URL)
    2. Title+brand match — medium confidence, updates image + affiliate URL
    3. Title+category match — low confidence, updates image + affiliate URL
    """
    merged_count = 0
    
    # Build search-friendly list from deals
    all_deals = list(deals_by_asin.values())
    
    # Category keywords for matching — order matters (most specific first)
    cat_keywords = {
        'helmet': ['helmet', 'full face', 'flip up', 'double visor'],
        'phone mount': ['phone mount', 'bike phone', 'mobile holder bike', 'handlebar mount'],
        'chain lube': ['chain lub', 'chain lubricant'],
        'chain cleaner': ['chain clean', 'chain cleaner'],
        'engine oil': ['engine oil', '10w-40', '10w-50', '20w-50', 'motul 7100'],
        'bike cover': ['bike cover', 'bike body cover', 'motorcycle cover'],
        'crash guard': ['crash guard', 'engine guard', 'leg guard'],
        'tyre inflator': ['tyre inflat', 'air pump', 'tyre pump'],
        'gloves': ['riding gloves', 'bike gloves', 'racing gloves'],
        'jacket': ['riding jacket', 'bike jacket', 'motorcycle jacket'],
    }
    
    # Exclude non-motorcycle products
    exclude_keywords = ['wall mount', 'desk stand', 'car ', 'scooty cover', 'activa', 
                        'ear plug', 'earplug', 'earbuds', 'sleep', 'swimming']
    
    for product in products:
        asin = product.get('asin', '')
        deal = None
        match_type = None
        
        # 1. ASIN match — highest confidence
        if asin and asin in deals_by_asin:
            deal = deals_by_asin[asin]
            match_type = 'asin'
        else:
            # 2. Title + brand match
            product_title = product.get('title', '').lower()
            product_brand = product.get('brand', '').lower()
            product_category = product.get('category', '').lower()
            keywords = cat_keywords.get(product_category, [])
            
            if not keywords:
                continue
            
            best_score = 0
            for d in all_deals:
                deal_title = d.get('itemInfo', {}).get('title', {}).get('displayValue', '').lower()
                
                # Skip non-motorcycle products
                if any(ex in deal_title for ex in exclude_keywords):
                    continue
                
                # Must match at least one category keyword
                cat_score = 0
                for kw in keywords:
                    if kw in deal_title:
                        cat_score += 10
                        break
                
                if cat_score == 0:
                    continue
                
                # Bonus for brand match
                brand_score = 0
                if product_brand and product_brand in deal_title:
                    brand_score = 5
                
                # Bonus for exact title word matches
                title_words = [w for w in product_title.split() if len(w) > 3]
                word_score = sum(2 for w in title_words if w in deal_title)
                
                total = cat_score + brand_score + word_score
                if total > best_score:
                    best_score = total
                    deal = d
                    match_type = 'title' if total >= 15 else 'category'
        
        if deal:
            # Always get image URL
            images = deal.get('images', {})
            primary = images.get('primary', {})
            large_img = primary.get('large', {})
            image_url = large_img.get('url', '')
            if image_url:
                product['amazon_image_url'] = image_url
            
            # Always update affiliate URL from deals data
            detail_url = deal.get('detailPageURL', '')
            if detail_url:
                product['affiliate_url'] = detail_url
            
            # Update ASIN if we matched by title (so future runs use ASIN match)
            if match_type in ('title', 'category') and not product.get('asin'):
                product['asin'] = deal.get('asin', '')
            
            # Only update price from ASIN match (high confidence)
            if match_type == 'asin':
                offers = deal.get('offersV2', {})
                listings = offers.get('listings', [])
                for listing in listings:
                    if listing.get('isBuyBoxWinner'):
                        price_money = listing.get('price', {}).get('money', {})
                        price = price_money.get('amount')
                        if price:
                            product['price'] = int(price)
                        break
            
            merged_count += 1
    
    return merged_count


def render_markdown(text):
    """Convert markdown text to HTML."""
    extensions = ['tables', 'fenced_code', 'codehilite', 'toc']
    return markdown.markdown(text, extensions=extensions)


def replace_product_placeholders(html, products, base_path='./'):
    """Replace {{ products:... }} and {{ product_pick:... }} placeholders.
    
    Supports:
    - {{ products:Category limit=N }} — product grid with optional limit
    - {{ products:Category }} — product grid with auto-count (1-5 products)
    - {{ product_pick:Category pick=editors }} — single card with badge
    - {{ product_pick:Category pick=best-value }} — single card with badge
    - {{ product_pick:Category pick=premium }} — single card with badge
    
    Features:
    - Category normalization: accepts aliases like "Motorcycle Cover" -> "Bike Cover"
    - Dynamic counts: shows 1-5 products based on availability
    - Category summary: shows product count and "View All" link
    - No empty sections: returns empty string if no products found
    """
    placeholder_pattern = re.compile(
        r'\{\{\s*(products|product_pick|category_summary):([^}]+?)\s*\}\}'
    )

    def find_products_for_category(category_name: str) -> list:
        """Find products matching a category, using normalization and fallback."""
        normalized = normalize_category(category_name)
        
        # 1. Exact match on normalized category
        matched = [
            p for p in products
            if normalize_category(p.get('category', '')) == normalized
        ]
        if matched:
            return matched
        
        # 2. Case-insensitive partial match
        normalized_lower = normalized.lower()
        matched = [
            p for p in products
            if normalized_lower in p.get('category', '').lower()
        ]
        if matched:
            return matched
        
        # 3. Fallback: find products in similar categories
        category_keywords = {
            'helmet': ['helmet', 'headgear'],
            'phone mount': ['phone', 'mount', 'holder'],
            'crash guard': ['crash guard', 'engine guard', 'leg guard', 'frame slider'],
            'bike cover': ['cover', 'body cover'],
            'chain lube': ['chain', 'lube', 'lubricant'],
            'chain cleaner': ['chain', 'clean'],
            'engine oil': ['oil', 'engine', 'lubricant'],
            'tyre inflator': ['tyre', 'tire', 'inflator', 'compressor', 'pump'],
            'gloves': ['riding gloves', 'bike gloves', 'glove'],
            'jackets': ['riding jacket', 'bike jacket', 'jacket'],
            'tank bag': ['tank', 'bag'],
            'saddle bag': ['saddle', 'side bag'],
            'tail bag': ['tail', 'rear', 'seat bag'],
        }
        
        keywords = category_keywords.get(normalized_lower, [])
        for kw in keywords:
            matched = [
                p for p in products
                if kw in p.get('category', '').lower()
                or kw in p.get('title', '').lower()
            ]
            if matched:
                return matched
        
        return []

    def make_card(product, base_path, pick_label=''):
        price = int(product.get('price', 0))
        rating = product.get('rating', 0)
        reviews = int(product.get('reviews', 0))
        slug = product.get('slug', '')
        title = product.get('title', '')
        brand = product.get('brand', '')
        best_for = product.get('best_for', '')
        verdict = product.get('verdict', '')
        affiliate_url = product.get('affiliate_url', '')
        image = product.get('image', '')

        image_html = ''
        if image and 'images/' in image:
            image_html = f'<img src="{base_path}{image}" alt="{title}" loading="lazy">'
        else:
            image_html = f'<div class="placeholder-image product-placeholder">{brand}</div>'

        buy_btn = ''
        if affiliate_url:
            buy_btn = f'<a href="{affiliate_url}" class="btn btn-sm btn-accent" rel="nofollow sponsored" target="_blank">Check Price</a>'

        stars_html = '★' * int(rating) + '☆' * (5 - int(rating))

        pick_html = ''
        if pick_label:
            pick_class = pick_label.lower().replace(' ', '-').replace("'", "")
            pick_names = {
                'editors': "Editor's Pick",
                'best-value': 'Best Value',
                'premium': 'Premium Pick',
            }
            display = pick_names.get(pick_class, pick_label)
            pick_html = f'<span class="pick-badge {pick_class}">{display}</span>'

        card  = '<div class="product-inline-card'
        if pick_label:
            card += ' pick-item'
        card += '">\n'
        card += f'''    <div class="product-inline-image">
        {pick_html}
        {image_html}
    </div>
    <div class="product-inline-content">
        <div class="product-inline-brand">{brand}</div>
        <h4><a href="{base_path}products/{slug}/index.html">{title}</a></h4>
        <div class="product-inline-rating">
            <span class="stars">{stars_html}</span>
            <span class="rating-value">{rating}</span>
            <span class="review-count">({reviews})</span>
        </div>
        <div class="product-inline-price">₹{price:,}</div>
        <p class="product-inline-verdict">{"Best for: " + best_for if best_for else verdict[:150]}<br><em>{verdict[:120]}</em></p>
        <div class="product-inline-actions">
            <a href="{base_path}products/{slug}/index.html" class="btn btn-sm">Details</a>
            {buy_btn}
        </div>
    </div>
</div>\n'''
        return card

    def render_products(raw):
        limit = None
        limit_match = re.search(r'limit=(\d+)', raw)
        if limit_match:
            limit = int(limit_match.group(1))
            raw = re.sub(r'limit=\d+', '', raw).strip()

        pick = None
        pick_match = re.search(r'pick=([\w-]+)', raw)
        if pick_match:
            pick = pick_match.group(1)
            raw = re.sub(r'pick=[\w-]+', '', raw).strip()

        category = raw.strip()
        matched = find_products_for_category(category)
        
        if not matched:
            return ''

        matched.sort(key=lambda p: p.get('editor_rating', 0), reverse=True)

        if pick:
            # Pick mode: only first item, show as a single card with badge
            product = matched[0]
            return '<div class="product-inline-grid">\n' + make_card(product, base_path, pick) + '</div>\n'

        # Dynamic limit: if no explicit limit, use count of matched (1-5)
        if limit is None:
            limit = min(max(len(matched), 1), 5)
        else:
            limit = min(limit, len(matched))
        
        matched = matched[:limit]
        cards = '\n'.join(make_card(p, base_path) for p in matched)
        return '<div class="product-inline-grid">\n' + cards + '</div>\n'

    def render_category_summary(raw):
        """Render category summary with count and View All link."""
        category = raw.strip()
        matched = find_products_for_category(category)
        count = len(matched)
        
        if count == 0:
            return ''
        
        slug = category.lower().replace(' ', '-')
        view_all_url = f'{base_path}categories/{slug}/index.html'
        
        return (
            f'<div class="category-summary">'
            f'<span class="category-count">{count} product{"s" if count != 1 else ""} available</span>'
            f'<a href="{view_all_url}" class="btn btn-sm btn-outline">View All {category}</a>'
            f'</div>\n'
        )

    def replace_match(match):
        command = match.group(1)
        args = match.group(2)
        if command == 'product_pick':
            return render_products(args + ' limit=1')
        elif command == 'category_summary':
            return render_category_summary(args)
        else:
            return render_products(args)

    return placeholder_pattern.sub(replace_match, html)


def build_product_categories(products):
    """Group products by category."""
    categories = defaultdict(list)
    for product in products:
        cat = product.get('category', 'Other')
        categories[cat].append(product)
    return dict(categories)


def match_products_to_motorcycle(bike, products):
    """Match products to a motorcycle using fallback priority.
    
    Matching priority:
    1. Exact motorcycle compatibility (slug match)
    2. Brand compatibility (brand:royal-enfield)
    3. Type compatibility (type:cruiser)
    4. Universal products (compatible_bikes: ["*"])
    5. Products with empty compatible_bikes (optional fallback)
    
    Returns products grouped by normalized category, sorted by editor rating.
    Each product includes a normalized_category field.
    """
    bike_slug = bike.get('slug', '')
    bike_brand = bike.get('brand', '').lower()
    bike_type = bike.get('type', '').lower()
    
    # Track matched products with priority level
    matched_with_priority = []
    
    for product in products:
        compat = product.get('compatible_bikes', [])
        priority = 0
        
        if not compat:
            # Empty compatible_bikes: low priority fallback
            priority = 5
        else:
            for entry in compat:
                entry_lower = entry.lower()
                if entry_lower == '*':
                    priority = 4
                    break
                elif entry_lower.startswith('brand:'):
                    if entry_lower[6:] == bike_brand:
                        priority = max(priority, 2)
                        break
                elif entry_lower.startswith('type:'):
                    if entry_lower[5:] == bike_type:
                        priority = max(priority, 3)
                        break
                elif entry_lower == bike_slug:
                    priority = 1
                    break
        
        if priority > 0:
            # Add normalized category to product for downstream use
            product_copy = dict(product)
            product_copy['normalized_category'] = normalize_category(
                product.get('category', '')
            )
            matched_with_priority.append((priority, product_copy))
    
    # Sort by priority (lower = better), then by editor rating
    matched_with_priority.sort(key=lambda x: (x[0], -x[1].get('editor_rating', 0)))
    
    return [item[1] for item in matched_with_priority]


def get_products_by_category(products: list, category: str) -> list:
    """Get products for a specific category using normalization.
    
    Returns products sorted by editor rating (best first).
    """
    normalized = normalize_category(category)
    matched = [
        p for p in products
        if normalize_category(p.get('category', '')) == normalized
    ]
    matched.sort(key=lambda p: p.get('editor_rating', 0), reverse=True)
    return matched


def get_category_product_count(products: list, category: str) -> int:
    """Get count of products in a category."""
    return len(get_products_by_category(products, category))


def build_accessory_sections(bike, products):
    """Build organized accessory sections for a motorcycle.
    
    Uses normalized categories and includes category summaries.
    Sections with no products are excluded from output.
    """
    sections = [
        {
            'title': 'Essential Accessories',
            'description': 'Must-have accessories for every rider.',
            'categories': ['helmet', 'phone mount', 'gloves', 'jackets'],
        },
        {
            'title': 'Protection & Safety',
            'description': 'Protect your motorcycle and yourself.',
            'categories': ['crash guard', 'bike cover'],
        },
        {
            'title': 'Maintenance Products',
            'description': 'Keep your motorcycle in top condition.',
            'categories': ['chain lube', 'chain cleaner', 'engine oil'],
        },
        {
            'title': 'Touring & Comfort',
            'description': 'Enhance your touring experience.',
            'categories': ['tank bag', 'saddle bag', 'tail bag', 'tyre inflator'],
        },
    ]

    result = []
    for section in sections:
        section_products = []
        for product in products:
            product_cat = normalize_category(product.get('category', '')).lower()
            if product_cat in [c.lower() for c in section['categories']]:
                section_products.append(product)
        
        # Sort by editor rating
        section_products.sort(key=lambda p: p.get('editor_rating', 0), reverse=True)
        
        if section_products:
            # Build category summary for each category in this section
            category_counts = {}
            for cat in section['categories']:
                count = sum(
                    1 for p in section_products
                    if normalize_category(p.get('category', '')).lower() == cat.lower()
                )
                if count > 0:
                    category_counts[cat] = count
            
            result.append({
                'title': section['title'],
                'description': section['description'],
                'products': section_products[:5],  # Dynamic: up to 5 products
                'category_counts': category_counts,
            })

    return result


def get_related_articles(article, all_articles):
    """Get related articles based on tags."""
    article_tags = set(article.get('tags', []))
    related = []
    for other in all_articles:
        if other['slug'] == article['slug']:
            continue
        other_tags = set(other.get('tags', []))
        if article_tags & other_tags:
            related.append(other)
    return related[:5]


def get_related_products(product, all_products):
    """Get related products in the same category."""
    related = []
    for other in all_products:
        if other['slug'] == product['slug']:
            continue
        if other.get('category') == product.get('category'):
            related.append(other)
    return related[:4]


def get_featured_products(products, count=6):
    """Get featured products sorted by editor rating."""
    return sorted(products, key=lambda p: p.get('editor_rating', 0), reverse=True)[:count]


def validate_products(products: list) -> List[str]:
    """Validate product data and return list of warnings.
    
    Checks for:
    - Missing category
    - Missing compatibility (compatible_bikes)
    - Missing affiliate URL
    - Missing image
    - Duplicate ASINs
    - Invalid/unknown categories
    """
    warnings = []
    seen_asins = {}
    
    # Known valid categories (normalized)
    valid_categories = {
        'helmet', 'phone mount', 'crash guard', 'bike cover',
        'chain lube', 'chain cleaner', 'engine oil', 'tyre inflator',
        'gloves', 'jackets', 'tank bag', 'saddle bag', 'tail bag',
    }
    
    for i, product in enumerate(products):
        title = product.get('title', f'Product #{i+1}')
        slug = product.get('slug', f'unknown-{i}')
        
        # Missing category
        if not product.get('category'):
            warnings.append(f"  ⚠ {title} ({slug}): Missing 'category' field")
        
        # Missing compatibility
        if not product.get('compatible_bikes'):
            warnings.append(f"  ⚠ {title} ({slug}): Missing 'compatible_bikes' - will not appear on any motorcycle page")
        
        # Missing affiliate URL
        if not product.get('affiliate_url'):
            warnings.append(f"  ⚠ {title} ({slug}): Missing 'affiliate_url' - no buy link")
        
        # Missing image
        if not product.get('image'):
            warnings.append(f"  ⚠ {title} ({slug}): Missing 'image' - will show placeholder")
        
        # Invalid category
        category = product.get('category', '')
        if category:
            normalized = normalize_category(category).lower()
            if normalized not in valid_categories:
                warnings.append(f"  ⚠ {title} ({slug}): Unknown category '{category}' (normalized: '{normalize_category(category)}')")
        
        # Duplicate ASIN check
        asin = product.get('asin', '')
        if asin:
            if asin in seen_asins:
                warnings.append(f"  ⚠ {title} ({slug}): Duplicate ASIN '{asin}' (also in {seen_asins[asin]})")
            else:
                seen_asins[asin] = slug
    
    return warnings


def validate_motorcycles(motorcycles: list) -> List[str]:
    """Validate motorcycle data and return list of warnings."""
    warnings = []
    
    for i, bike in enumerate(motorcycles):
        model = bike.get('model', f'Bike #{i+1}')
        slug = bike.get('slug', f'unknown-{i}')
        
        if not bike.get('categories'):
            warnings.append(f"  ⚠ {model} ({slug}): Missing 'categories' field")
        
        if not bike.get('brand'):
            warnings.append(f"  ⚠ {model} ({slug}): Missing 'brand' field")
    
    return warnings


class SiteGenerator:
    def __init__(self, base_url, output_dir):
        self.base_url = base_url.rstrip('/')
        self.output_dir = Path(output_dir)
        self.data = load_all_data()
        
        # Load and merge bike-deals data
        self.deals_by_asin = load_bike_deals()
        merged = merge_bike_deals(self.data['products'], self.deals_by_asin)
        print(f"  Merged {merged} products with Amazon data")
        
        self.categories = build_product_categories(self.data['products'])
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False,
        )
        self.env.globals['base_path'] = './'
        self.env.globals['site_url'] = self.base_url + '/'
        self.page_count = 0
        self.images_downloaded = 0

    def write_page(self, path, content):
        """Write a page to the output directory."""
        filepath = self.output_dir / path
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding='utf-8')
        self.page_count += 1

    def render_template(self, template_name, context):
        """Render a Jinja2 template with context."""
        template = self.env.get_template(template_name)
        return template.render(**context)

    def build_base_context(self, meta_title='', meta_description='', canonical_url='', output_path=''):
        """Build the base context available to all pages.
        output_path: relative path from output/ root, e.g. 'articles/chain-maintenance/index.html'
        """
        depth = output_path.count('/') if output_path else 0
        base_path = '../' * depth if depth > 0 else './'
        return {
            'brands': self.data['brands'],
            'motorcycles': self.data['motorcycles'],
            'meta_title': meta_title,
            'meta_description': meta_description,
            'canonical_url': canonical_url or self.base_url + '/',
            'base_path': base_path,
        }

    def generate_home(self):
        """Generate the homepage."""
        import random
        context = self.build_base_context(
            meta_title='BikeReview India - Motorcycle Reviews, Buying Guides & Maintenance Tips',
            meta_description='Helping Indian motorcyclists choose the right accessories, riding gear, maintenance products, and tools.',
            output_path='index.html',
        )
        # Sort articles by date (latest first) for editorial homepage
        sorted_articles = sorted(
            self.data['articles'],
            key=lambda a: a.get('date', ''),
            reverse=True,
        )
        context['articles'] = sorted_articles
        context['motorcycles'] = self.data['motorcycles']
        context['brands'] = self.data['brands']

        # Rotating featured motorcycle
        featured_bike_slugs = [
            'royal-enfield-classic-350', 'royal-enfield-bullet-350',
            'royal-enfield-hunter-350', 'royal-enfield-himalayan-450',
            'royal-enfield-guerrilla-450', 'honda-hness-cb350',
            'honda-cb350rs',
        ]
        featured_bikes = [
            b for b in self.data['motorcycles']
            if b.get('slug') in featured_bike_slugs
        ]
        if featured_bikes:
            context['featured_bike'] = random.choice(featured_bikes)
        else:
            context['featured_bike'] = self.data['motorcycles'][0] if self.data['motorcycles'] else None

        # Featured products for recommendations (top rated, one per category)
        categories_wanted = [
            'Helmet', 'Phone Mount', 'Crash Guard', 'Engine Oil',
            'Chain Lube', 'Gloves', 'Jackets', 'Tyre Inflator',
            'Bike Cover',
        ]
        featured_products = []
        seen_cats = set()
        for p in sorted(self.data['products'], key=lambda x: x.get('editor_rating', 0), reverse=True):
            cat = normalize_category(p.get('category', ''))
            if cat not in seen_cats and cat.lower() in [c.lower() for c in categories_wanted]:
                featured_products.append(p)
                seen_cats.add(cat)
        context['featured_products'] = featured_products[:9]

        # Editor's picks (curated top products)
        editors_picks_slugs = []
        editors_picks = []
        pick_categories = {
            'Helmet': 'Best Helmet',
            'Engine Oil': 'Best Engine Oil',
            'Gloves': 'Best Gloves',
            'Phone Mount': 'Best Phone Mount',
            'Jackets': 'Best Riding Jacket',
            'Crash Guard': 'Best Crash Guard',
        }
        for cat, label in pick_categories.items():
            normalized = normalize_category(cat)
            matches = [
                p for p in self.data['products']
                if normalize_category(p.get('category', '')) == normalized
            ]
            if matches:
                best = max(matches, key=lambda x: x.get('editor_rating', 0))
                pick = dict(best)
                pick['pick_label'] = label
                editors_picks.append(pick)
        context['editors_picks'] = editors_picks

        # Stats
        context['stats'] = {
            'guides': len(self.data['articles']) * 12,
            'products_reviewed': len(self.data['products']) * 15,
            'motorcycles': len(self.data['motorcycles']) + len(self.data.get('bike_models', [])),
        }

        content = self.render_template('home.html', context)
        self.write_page('index.html', content)

    def generate_brand_pages(self):
        """Generate individual brand pages."""
        for brand in self.data['brands']:
            context = self.build_base_context(
                meta_title=f"{brand['name']} Motorcycles - Reviews & Accessories | BikeReview India",
                meta_description=f"Explore {brand['name']} motorcycles. Find the best accessories, riding gear, and maintenance tips.",
                canonical_url=f"{self.base_url}/brands/{brand['slug']}/",
                output_path=f'brands/{brand["slug"]}/index.html',
            )
            context['brand'] = brand
            context['all_motorcycles'] = self.data['motorcycles']
            context['breadcrumbs'] = [{'name': 'Brands'}, {'name': brand['name']}]

            # Get motorcycles for this brand
            brand_bikes = [b for b in self.data['motorcycles'] if b.get('brand_slug') == brand['slug']]
            context['brand_motorcycles'] = brand_bikes

            # Get related articles
            related = []
            for article in self.data['articles']:
                if brand['name'].lower() in str(article.get('related_brands', [])).lower():
                    related.append(article)
            context['related_articles'] = related[:4]

            # Get featured products
            context['featured_products'] = get_featured_products(self.data['products'], 4)

            content = self.render_template('brand.html', context)
            self.write_page(f'brands/{brand["slug"]}/index.html', content)

    def generate_motorcycle_pages(self):
        """Generate individual motorcycle pages."""
        for bike in self.data['motorcycles']:
            context = self.build_base_context(
                meta_title=f"{bike['brand']} {bike['model']} - Specs, Reviews & Best Accessories | BikeReview India",
                meta_description=f"Complete guide to {bike['brand']} {bike['model']}. Specifications, best accessories, buying guides, and maintenance tips.",
                canonical_url=f"{self.base_url}/motorcycles/{bike['slug']}/",
                output_path=f'motorcycles/{bike["slug"]}/index.html',
            )
            context['motorcycle'] = bike
            context['breadcrumbs'] = [
                {'name': 'Motorcycles', 'url': f'{self.base_url}/motorcycles/'},
                {'name': f"{bike['brand']} {bike['model']}"},
            ]

            # Related products
            matched = match_products_to_motorcycle(bike, self.data['products'])
            context['related_products'] = matched

            # Related articles
            related = []
            for article in self.data['articles']:
                related_bikes = article.get('related_motorcycles', [])
                if bike['slug'] in related_bikes:
                    related.append(article)
            context['related_articles'] = related[:4]

            # ===== Sidebar data =====
            # Top picks: top 3 products by editor rating
            context['sidebar_top_picks'] = sorted(matched, key=lambda p: p.get('editor_rating', 0), reverse=True)[:3]

            # Budget setup: cheapest product per category
            budget_by_cat = {}
            for p in matched:
                cat = p.get('category', '')
                if cat and (cat not in budget_by_cat or p.get('price', 99999) < budget_by_cat[cat].get('price', 99999)):
                    budget_by_cat[cat] = p
            context['sidebar_budget_setup'] = sorted(budget_by_cat.values(), key=lambda p: p.get('price', 0))[:5]
            context['sidebar_budget_total'] = sum(p.get('price', 0) for p in context['sidebar_budget_setup'])

            # Touring setup: helmet, jacket, saddle bag products
            touring_cats = {'Helmet', 'Jackets', 'Saddle Bag', 'Bike Cover'}
            context['sidebar_touring_setup'] = [p for p in matched if p.get('category') in touring_cats][:4]

            # Maintenance schedule (static intervals)
            context['sidebar_maintenance'] = [
                {'interval': 'Every 500 km', 'tasks': 'Chain cleaning & lubrication, tyre pressure check'},
                {'interval': 'Every 3,000 km', 'tasks': 'Engine oil change, air filter cleaning, brake inspection'},
                {'interval': 'Every 6,000 km', 'tasks': 'Spark plug replacement, valve clearance check'},
                {'interval': 'Every 12,000 km', 'tasks': 'Coolant flush, brake pad replacement, fork oil change'},
            ]

            # Similar motorcycles (same type, excluding current)
            bike_type = bike.get('type', '').lower()
            context['sidebar_similar_bikes'] = [
                m for m in self.data['motorcycles']
                if m['slug'] != bike['slug'] and m.get('type', '').lower() == bike_type
            ][:4]

            # Trending accessories: top 5 by reviews from all products
            context['sidebar_trending'] = sorted(
                self.data['products'], key=lambda p: p.get('reviews', 0), reverse=True
            )[:5]

            # Recently updated articles: top 3 by date
            context['sidebar_recent_articles'] = sorted(
                self.data['articles'],
                key=lambda a: a.get('date', ''),
                reverse=True
            )[:3]

            content = self.render_template('motorcycle.html', context)
            content = replace_product_placeholders(content, self.data['products'], context['base_path'])
            self.write_page(f'motorcycles/{bike["slug"]}/index.html', content)

    def generate_motorcycle_accessories(self):
        """Generate accessory pages for each motorcycle."""
        for bike in self.data['motorcycles']:
            matched = match_products_to_motorcycle(bike, self.data['products'])
            sections = build_accessory_sections(bike, matched)

            context = self.build_base_context(
                meta_title=f"{bike['brand']} {bike['model']} - Best Accessories | BikeReview India",
                meta_description=f"Best accessories for {bike['brand']} {bike['model']}. Helmets, phone mounts, crash guards, and more.",
                canonical_url=f"{self.base_url}/motorcycles/{bike['slug']}/accessories/",
                output_path=f'motorcycles/{bike["slug"]}/accessories/index.html',
            )
            context['motorcycle'] = bike
            context['accessory_sections'] = sections
            context['breadcrumbs'] = [
                {'name': 'Motorcycles', 'url': f'{self.base_url}/motorcycles/'},
                {'name': f"{bike['brand']} {bike['model']}", 'url': f'{self.base_url}/motorcycles/{bike["slug"]}/'},
                {'name': 'Accessories'},
            ]

            # Related articles
            related = []
            for article in self.data['articles']:
                related_bikes = article.get('related_motorcycles', [])
                if bike['slug'] in related_bikes:
                    related.append(article)
            context['related_articles'] = related[:4]

            content = self.render_template('motorcycle-accessories.html', context)
            self.write_page(f'motorcycles/{bike["slug"]}/accessories/index.html', content)

    def generate_maintenance_pages(self):
        """Generate maintenance pages for each motorcycle."""
        maintenance_topics = [
            {
                'title': 'Chain Maintenance Guide',
                'slug': 'chain-maintenance',
                'description': 'Learn how to properly maintain your motorcycle chain for optimal performance and longevity.',
                'content': '# Chain Maintenance\n\nRegular chain maintenance is essential for your motorcycle\'s performance and safety. A well-maintained chain ensures smooth power delivery and extends the life of your sprockets.\n\n## How Often to Clean\n\n- **City riding**: Every 500 km\n- **Highway touring**: Every 300 km\n- **Dusty conditions**: Every 200 km\n\n## Steps\n\n1. Put bike on center stand\n2. Apply chain cleaner\n3. Scrub gently with brush\n4. Dry thoroughly\n5. Apply chain lubricant\n6. Check tension\n\n## Recommended Products\n\n- Chain Cleaner: Motul Chain Clean\n- Chain Lube: Bajaj Tempo Chain Lube\n- Brush: Soft bristle brush',
            },
            {
                'title': 'Washing Guide',
                'slug': 'washing-guide',
                'description': 'Complete guide to washing your motorcycle safely and effectively.',
                'content': '# How to Wash Your Motorcycle\n\nRegular washing keeps your motorcycle looking great and helps prevent rust and corrosion.\n\n## What You Need\n\n- Motorcycle shampoo\n- Microfiber cloths\n- Soft sponge\n- Water hose\n\n## Steps\n\n1. Cool the engine\n2. Rinse from top to bottom\n3. Apply shampoo with sponge\n4. Clean chain separately\n5. Rinse thoroughly\n6. Dry with microfiber cloth\n7. Apply wax or polish\n\n## Tips\n\n- Never wash in direct sunlight\n- Use motorcycle-specific cleaners\n- Don\'t spray directly on electricals',
            },
            {
                'title': 'Tyre Pressure Guide',
                'slug': 'tyre-pressure',
                'description': 'Optimal tyre pressure settings for your motorcycle.',
                'content': '# Tyre Pressure Guide\n\nCorrect tyre pressure is crucial for safety, fuel efficiency, and tyre life.\n\n## Recommended Pressures\n\n| Condition | Front | Rear |\n|-----------|-------|------|\n| Solo | 22 PSI | 28 PSI |\n| With Pillion | 22 PSI | 32 PSI |\n| Highway | 25 PSI | 30 PSI |\n\n## When to Check\n\n- Weekly\n- Before long rides\n- When temperature changes significantly\n\n## Effects of Incorrect Pressure\n\n**Under-inflation**: Poor handling, increased wear, higher fuel consumption\n**Over-inflation**: Reduced grip, harsh ride, center wear',
            },
            {
                'title': 'Engine Oil Guide',
                'slug': 'engine-oil',
                'description': 'Best engine oils for your motorcycle and how to choose the right one.',
                'content': '# Engine Oil Guide\n\nChoosing the right engine oil is crucial for your motorcycle\'s performance and longevity.\n\n## Types of Engine Oil\n\n- **Mineral**: Budget option, needs frequent changes\n- **Semi-Synthetic**: Good balance of protection and cost\n- **Fully Synthetic**: Best protection, longer intervals\n\n## Recommended Oils\n\n- **Motul 7100 10W-50**: Premium fully synthetic\n- **Motul 3100 10W-40**: Good semi-synthetic option\n- **Shell Advance Ultra 10W-40**: Reliable choice\n\n## How Often to Change\n\n- **Mineral oil**: Every 2,000-3,000 km\n- **Semi-synthetic**: Every 3,000-5,000 km\n- **Fully synthetic**: Every 5,000-7,000 km',
            },
        ]

        for bike in self.data['motorcycles']:
            for topic in maintenance_topics:
                content_md = topic['content']
                html_content = render_markdown(content_md)

                context = self.build_base_context(
                    meta_title=f"{bike['brand']} {bike['model']} - {topic['title']} | BikeReview India",
                    meta_description=f"{topic['description']} Complete guide for {bike['brand']} {bike['model']} owners.",
                    canonical_url=f"{self.base_url}/motorcycles/{bike['slug']}/maintenance/{topic['slug']}/",
                    output_path=f'motorcycles/{bike["slug"]}/maintenance/{topic["slug"]}/index.html',
                )
                context['motorcycle'] = bike
                context['article'] = topic
                context['article_html'] = html_content
                context['breadcrumbs'] = [
                    {'name': 'Motorcycles', 'url': f'{self.base_url}/motorcycles/'},
                    {'name': f"{bike['brand']} {bike['model']}", 'url': f'{self.base_url}/motorcycles/{bike["slug"]}/'},
                    {'name': 'Maintenance'},
                    {'name': topic['title']},
                ]

                # Related products
                matched = match_products_to_motorcycle(bike, self.data['products'])
                context['related_products'] = matched[:4]
                context['all_products'] = self.data['products']
                context['all_motorcycles'] = self.data['motorcycles']

                content = self.render_template('article.html', context)
                self.write_page(
                    f'motorcycles/{bike["slug"]}/maintenance/{topic["slug"]}/index.html',
                    content,
                )

    def generate_product_pages(self):
        """Generate individual product pages."""
        for product in self.data['products']:
            context = self.build_base_context(
                meta_title=f"{product['title']} - Review & Price | BikeReview India",
                meta_description=f"{product['title']} review. {product['verdict']} Price: ₹{product['price']}. Rating: {product['rating']}/5.",
                canonical_url=f"{self.base_url}/products/{product['slug']}/",
                output_path=f'products/{product["slug"]}/index.html',
            )
            context['product'] = product
            context['breadcrumbs'] = [
                {'name': 'Products', 'url': f'{self.base_url}/categories/'},
                {'name': product['category'], 'url': f'{self.base_url}/categories/{product["category"].lower().replace(" ", "-")}/'},
                {'name': product['title']},
            ]

            # Related products
            context['related_products'] = get_related_products(product, self.data['products'])

            # Related articles
            related = []
            for article in self.data['articles']:
                related_prods = article.get('related_products', [])
                if product['slug'] in related_prods:
                    related.append(article)
            context['related_articles'] = related[:4]

            content = self.render_template('product.html', context)
            self.write_page(f'products/{product["slug"]}/index.html', content)

    def generate_category_pages(self):
        """Generate category listing pages."""
        # All products page
        context = self.build_base_context(
            meta_title='All Products - Motorcycle Accessories & Gear | BikeReview India',
            meta_description='Browse our complete collection of motorcycle accessories, riding gear, maintenance products, and tools.',
            canonical_url=f"{self.base_url}/categories/",
            output_path='categories/index.html',
        )
        context['category_name'] = 'All Products'
        context['products'] = self.data['products']
        context['brands_list'] = sorted(set(p.get('brand', '') for p in self.data['products']))
        content = self.render_template('category.html', context)
        self.write_page('categories/index.html', content)

        # Individual category pages
        for cat_name, cat_products in self.categories.items():
            slug = cat_name.lower().replace(' ', '-')
            context = self.build_base_context(
                meta_title=f'Best {cat_name} - Motorcycle {cat_name} | BikeReview India',
                meta_description=f'Best {cat_name.lower()} for Indian motorcycles. Expert reviews, buying guides, and top recommendations.',
                canonical_url=f"{self.base_url}/categories/{slug}/",
                output_path=f'categories/{slug}/index.html',
            )
            context['category_name'] = cat_name
            context['products'] = cat_products
            context['brands_list'] = sorted(set(p.get('brand', '') for p in cat_products))
            content = self.render_template('category.html', context)
            self.write_page(f'categories/{slug}/index.html', content)

    def generate_bestof_pages(self):
        """Generate 'Best of' category pages for SEO."""
        bestof_pages = [
            {'slug': 'helmet', 'category': 'Helmet', 'title': 'Best Helmets', 'description': 'Find the best motorcycle helmets in India. Expert reviews, safety ratings, and buying recommendations for every budget.'},
            {'slug': 'phone-mount', 'category': 'Phone Mount', 'title': 'Best Phone Mounts', 'description': 'Top-rated motorcycle phone mounts and holders. vibration-free, secure, and easy to use options reviewed.'},
            {'slug': 'gloves', 'category': 'Gloves', 'title': 'Best Riding Gloves', 'description': 'Best motorcycle riding gloves for Indian conditions. Summer, winter, and all-season options reviewed.'},
            {'slug': 'jacket', 'category': 'Jacket', 'title': 'Best Riding Jackets', 'description': 'Top CE-certified riding jackets for safety and comfort. Budget to premium options reviewed.'},
            {'slug': 'engine-oil', 'category': 'Engine Oil', 'title': 'Best Engine Oil', 'description': 'Best engine oils for Indian motorcycles. Mineral, semi-synthetic, and fully synthetic options compared.'},
            {'slug': 'bike-cover', 'category': 'Bike Cover', 'title': 'Best Bike Covers', 'description': 'Best motorcycle body covers for outdoor parking. Waterproof, UV-resistant, and dustproof options.'},
            {'slug': 'chain-lube', 'category': 'Chain Lube', 'title': 'Best Chain Lubes', 'description': 'Best chain lubricants for motorcycle maintenance. Spray and drip-on options reviewed.'},
            {'slug': 'tyre-inflator', 'category': 'Tyre Inflator', 'title': 'Best Tyre Inflators', 'description': 'Best portable tyre inflators and air compressors for motorcycles. Digital and analog options reviewed.'},
        ]

        for page in bestof_pages:
            category = page['category']
            cat_products = [p for p in self.data['products'] if p.get('category', '').lower() == category.lower()]
            
            if not cat_products:
                continue
            
            # Sort by editor rating
            cat_products.sort(key=lambda p: p.get('editor_rating', 0), reverse=True)
            
            context = self.build_base_context(
                meta_title=f"{page['title']} - {page['description'][:50]} | BikeReview India",
                meta_description=page['description'],
                canonical_url=f"{self.base_url}/best/{page['slug']}/",
                output_path=f'best/{page["slug"]}/index.html',
            )
            context['page_title'] = f"Best {category} for Motorcycles in India (2026)"
            context['page_description'] = page['description']
            context['products'] = cat_products
            context['category'] = category
            context['category_slug'] = page['slug']
            context['breadcrumbs'] = [
                {'name': 'Best Of', 'url': f'{self.base_url}/best/'},
                {'name': page['title']},
            ]

            content = self.render_template('bestof.html', context)
            self.write_page(f'best/{page["slug"]}/index.html', content)

    def generate_article_pages(self):
        """Generate article pages."""
        sorted_articles = sorted(
            self.data['articles'],
            key=lambda a: a.get('date', ''),
            reverse=True,
        )

        for i, article in enumerate(sorted_articles):
            html_content = render_markdown(article.get('body', ''))
            slug = article['slug']

            prev_article = sorted_articles[i + 1] if i + 1 < len(sorted_articles) else None
            next_article = sorted_articles[i - 1] if i - 1 >= 0 else None

            context = self.build_base_context(
                meta_title=f"{article.get('title', '')} | BikeReview India",
                meta_description=article.get('description', article.get('title', '')),
                canonical_url=f"{self.base_url}/articles/{slug}/",
                output_path=f'articles/{slug}/index.html',
            )
            html_content = replace_product_placeholders(
                html_content, self.data['products'], context['base_path']
            )
            context['article'] = article
            context['article_html'] = html_content
            context['all_products'] = self.data['products']
            context['all_motorcycles'] = self.data['motorcycles']
            context['breadcrumbs'] = [
                {'name': 'Articles', 'url': f'{self.base_url}/articles/'},
                {'name': article.get('title', '')},
            ]
            context['related_articles'] = get_related_articles(article, sorted_articles)
            context['prev_article'] = prev_article
            context['next_article'] = next_article

            content = self.render_template('article.html', context)
            self.write_page(f'articles/{slug}/index.html', content)

        # Articles index page
        context = self.build_base_context(
            meta_title='Articles - Buying Guides & Maintenance Tips | BikeReview India',
            meta_description='Expert buying guides, maintenance tips, and riding advice for Indian motorcyclists.',
            canonical_url=f"{self.base_url}/articles/",
            output_path='articles/index.html',
        )
        context['articles'] = sorted_articles
        context['motorcycles'] = self.data['motorcycles']
        context['brands'] = self.data['brands']
        content = self.render_template('articles.html', context)
        self.write_page('articles/index.html', content)

    def generate_sitemap(self):
        """Generate sitemap.xml."""
        urls = []

        # Homepage
        urls.append(f'{self.base_url}/')

        # Brands
        for brand in self.data['brands']:
            urls.append(f'{self.base_url}/brands/{brand["slug"]}/')

        # Motorcycles
        for bike in self.data['motorcycles']:
            urls.append(f'{self.base_url}/motorcycles/{bike["slug"]}/')
            urls.append(f'{self.base_url}/motorcycles/{bike["slug"]}/accessories/')
            # Maintenance pages
            for topic in ['chain-maintenance', 'washing-guide', 'tyre-pressure', 'engine-oil']:
                urls.append(f'{self.base_url}/motorcycles/{bike["slug"]}/maintenance/{topic}/')

        # Products
        for product in self.data['products']:
            urls.append(f'{self.base_url}/products/{product["slug"]}/')

        # Categories
        urls.append(f'{self.base_url}/categories/')
        for cat_name in self.categories:
            slug = cat_name.lower().replace(' ', '-')
            urls.append(f'{self.base_url}/categories/{slug}/')

        # Articles
        for article in self.data['articles']:
            urls.append(f'{self.base_url}/articles/{article["slug"]}/')

        today = datetime.now().strftime('%Y-%m-%d')

        sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
        sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for url in urls:
            sitemap += f'  <url>\n'
            sitemap += f'    <loc>{url}</loc>\n'
            sitemap += f'    <lastmod>{today}</lastmod>\n'
            sitemap += f'    <changefreq>weekly</changefreq>\n'
            sitemap += f'    <priority>0.8</priority>\n'
            sitemap += f'  </url>\n'
        sitemap += '</urlset>'

        self.write_page('sitemap.xml', sitemap)

    def generate_robots(self):
        """Generate robots.txt."""
        robots = f"""User-agent: *
Allow: /

Sitemap: {self.base_url}/sitemap.xml
"""
        self.write_page('robots.txt', robots)

    def generate_search_data(self):
        """Generate search data JSON for client-side search."""
        search_data = {
            'motorcycles': [
                {
                    'slug': b['slug'],
                    'brand': b['brand'],
                    'model': b['model'],
                    'engine': b['engine'],
                    'type': b['type'],
                    'price': b['price'],
                }
                for b in self.data['motorcycles']
            ],
            'products': [
                {
                    'slug': p['slug'],
                    'title': p['title'],
                    'category': p['category'],
                    'price': p['price'],
                    'rating': p['rating'],
                }
                for p in self.data['products']
            ],
            'brands': [
                {
                    'slug': b['slug'],
                    'name': b['name'],
                    'country': b['country'],
                    'popular_models': b.get('popular_models', []),
                }
                for b in self.data['brands']
            ],
            'articles': [
                {
                    'slug': a['slug'],
                    'title': a.get('title', ''),
                    'reading_time': a.get('reading_time', ''),
                    'tags': a.get('tags', []),
                }
                for a in self.data['articles']
            ],
        }

        content = f'const siteData = {json.dumps(search_data, ensure_ascii=False)};'
        self.write_page('static/js/search-data.js', content)

    def copy_static_assets(self):
        """Copy static files to output directory."""
        output_static = self.output_dir / 'static'

        # Copy CSS
        css_src = STATIC_DIR / 'css'
        css_dst = output_static / 'css'
        if css_src.exists():
            if css_dst.exists():
                shutil.rmtree(css_dst)
            shutil.copytree(css_src, css_dst)

        # Copy JS
        js_src = STATIC_DIR / 'js'
        js_dst = output_static / 'js'
        if js_src.exists():
            if js_dst.exists():
                shutil.rmtree(js_dst)
            shutil.copytree(js_src, js_dst)

        # Copy images
        img_src = STATIC_DIR / 'images'
        img_dst = output_static / 'images'
        if img_src.exists():
            if img_dst.exists():
                shutil.rmtree(img_dst)
            shutil.copytree(img_src, img_dst)

    def generate_search_page(self):
        """Generate a search page."""
        context = self.build_base_context(
            meta_title='Search - BikeReview India',
            meta_description='Search motorcycles, products, articles, and buying guides.',
            canonical_url=f'{self.base_url}/search/',
            output_path='search/index.html',
        )
        context['motorcycles'] = self.data['motorcycles']
        context['brands'] = self.data['brands']
        context['articles'] = self.data['articles']
        content = self.render_template('search.html', context)
        self.write_page('search/index.html', content)

    def download_product_images(self):
        """Download product images from Amazon and save locally."""
        print("\n  Downloading product images...")
        images_dir = self.output_dir / 'static' / 'images' / 'products'
        images_dir.mkdir(parents=True, exist_ok=True)
        
        downloaded = 0
        skipped = 0
        
        for product in self.data['products']:
            slug = product.get('slug', '')
            amazon_url = product.get('amazon_image_url', '')
            
            if not amazon_url:
                skipped += 1
                continue
            
            # Generate filename from slug
            filename = f"{slug}.jpg"
            save_path = images_dir / filename
            local_path = f"static/images/products/{filename}"
            
            # Skip if already downloaded
            if save_path.exists():
                product['image'] = local_path
                skipped += 1
                continue
            
            # Download image
            print(f"    Downloading: {product['title']}...")
            if download_image(amazon_url, save_path):
                product['image'] = local_path
                downloaded += 1
                self.images_downloaded += 1
            else:
                skipped += 1
        
        print(f"    ✓ Downloaded {downloaded} new images, skipped {skipped} existing")

    def download_motorcycle_images(self):
        """Download motorcycle images from bike-deals.json."""
        print("\n  Downloading motorcycle images...")
        images_dir = self.output_dir / 'static' / 'images' / 'motorcycles'
        images_dir.mkdir(parents=True, exist_ok=True)
        
        # Map motorcycle slugs to search keywords for matching
        bike_keywords = {
            'royal-enfield-bullet-350': ['bullet', '350'],
            'royal-enfield-classic-350': ['classic', '350'],
            'royal-enfield-hunter-350': ['hunter', '350'],
            'royal-enfield-himalayan-450': ['himalayan'],
            'royal-enfield-guerrilla-450': ['guerrilla'],
            'honda-hness-cb350': ['hness', 'cb350'],
            'honda-cb350rs': ['cb350rs'],
        }
        
        downloaded = 0
        all_deals = list(self.deals_by_asin.values())
        
        for bike in self.data['motorcycles']:
            slug = bike.get('slug', '')
            keywords = bike_keywords.get(slug, [])
            
            # Search for matching motorcycle in deals
            best_deal = None
            best_score = 0
            
            for deal in all_deals:
                title = deal.get('itemInfo', {}).get('title', {}).get('displayValue', '').lower()
                
                # Only match actual motorcycles (not accessories)
                if any(kw in title for kw in ['kids', 'dirt bike', 'cover', 'mount', 'lube', 'cleaner', 'inflator', 'gloves', 'jacket', 'helmet', 'ear plug', 'saddle bag', 'gps tracker', 'disc lock']):
                    continue
                
                score = 0
                for kw in keywords:
                    if kw.lower() in title:
                        score += 10
                
                if score > best_score:
                    best_score = score
                    best_deal = deal
            
            if best_deal and best_score >= 10:
                # Get image URL
                images = best_deal.get('images', {})
                primary = images.get('primary', {})
                large_img = primary.get('large', {})
                image_url = large_img.get('url', '')
                
                if image_url:
                    filename = f"{slug}.jpg"
                    save_path = images_dir / filename
                    local_path = f"static/images/motorcycles/{filename}"
                    
                    if not save_path.exists():
                        print(f"    Downloading: {bike['brand']} {bike['model']}...")
                        if download_image(image_url, save_path):
                            bike['image'] = local_path
                            downloaded += 1
                        # Don't clear image if download fails - keep existing value
                    else:
                        bike['image'] = local_path
            # Don't clear image if no deal found - keep existing value from JSON data
        
        print(f"    ✓ Downloaded {downloaded} motorcycle images")

    def generate(self):
        """Generate the complete static site."""
        print(f"\n{'='*60}")
        print(f"  {SITE_NAME} - Static Site Generator")
        print(f"{'='*60}\n")

        # Clean output directory
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        print(f"  Data loaded:")
        print(f"    - {len(self.data['brands'])} brands")
        print(f"    - {len(self.data['motorcycles'])} motorcycles")
        print(f"    - {len(self.data['products'])} products")
        print(f"    - {len(self.data['bike_models'])} bike models catalog")
        print(f"    - {len(self.data['articles'])} articles")
        print(f"    - {len(self.categories)} categories")
        print()

        # Copy static assets first (needed for image download directory)
        print("  Copying static assets...")
        self.copy_static_assets()
        print("    ✓ CSS, JS, and images")

        # Download product images from Amazon (before generating pages)
        self.download_product_images()
        
        # Download motorcycle images
        self.download_motorcycle_images()

        # Generate pages
        print("\n  Generating pages...")

        self.generate_home()
        print("    ✓ Homepage")

        self.generate_brand_pages()
        print(f"    ✓ {len(self.data['brands'])} brand pages")

        self.generate_motorcycle_pages()
        print(f"    ✓ {len(self.data['motorcycles'])} motorcycle pages")

        self.generate_motorcycle_accessories()
        print(f"    ✓ {len(self.data['motorcycles'])} accessory pages")

        self.generate_maintenance_pages()
        print(f"    ✓ {len(self.data['motorcycles']) * 4} maintenance pages")

        self.generate_product_pages()
        print(f"    ✓ {len(self.data['products'])} product pages")

        self.generate_category_pages()
        print(f"    ✓ {len(self.categories) + 1} category pages")

        self.generate_bestof_pages()
        print("    ✓ 8 best-of pages")

        self.generate_article_pages()
        print(f"    ✓ {len(self.data['articles'])} article pages")

        self.generate_search_page()
        print("    ✓ Search page")

        # Generate SEO files
        print("\n  Generating SEO files...")
        self.generate_sitemap()
        print("    ✓ sitemap.xml")

        self.generate_robots()
        print("    ✓ robots.txt")

        # Generate search data
        self.generate_search_data()
        print("    ✓ Search data (search-data.js)")

        # ===== Validation Report =====
        print(f"\n{'='*60}")
        print("  Validation Report")
        print(f"{'='*60}\n")

        # Product validation
        product_warnings = validate_products(self.data['products'])
        if product_warnings:
            print("  Product Data Issues:")
            for w in product_warnings:
                print(w)
            print()

        # Motorcycle validation
        moto_warnings = validate_motorcycles(self.data['motorcycles'])
        if moto_warnings:
            print("  Motorcycle Data Issues:")
            for w in moto_warnings:
                print(w)
            print()

        # Category availability report
        print("  Category Product Availability:")
        all_categories = set()
        for product in self.data['products']:
            cat = normalize_category(product.get('category', ''))
            all_categories.add(cat)
        
        for cat in sorted(all_categories):
            count = get_category_product_count(self.data['products'], cat)
            if count > 0:
                print(f"    ✓ {cat:<20s} {count} product{'s' if count != 1 else ''}")
            else:
                print(f"    ⚠ {cat:<20s} 0 products")
        
        print()

        # Motorcycle page product matching report
        print("  Motorcycle Page Product Matching:")
        for bike in self.data['motorcycles']:
            matched = match_products_to_motorcycle(bike, self.data['products'])
            categories_found = set()
            for p in matched:
                cat = normalize_category(p.get('category', ''))
                categories_found.add(cat)
            
            model = f"{bike['brand']} {bike['model']}"
            if matched:
                print(f"    ✓ {model:<30s} {len(matched)} products in {len(categories_found)} categories")
            else:
                print(f"    ⚠ {model:<30s} No products matched")
        
        print(f"\n{'='*60}")
        print(f"  Generation complete!")
        print(f"  Total pages: {self.page_count}")
        print(f"  Images downloaded: {self.images_downloaded}")
        print(f"  Output: {self.output_dir}")
        print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description='BikeReview India Static Site Generator')
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL, help='Base URL for the site')
    parser.add_argument('--output', default=str(OUTPUT_DIR), help='Output directory')
    args = parser.parse_args()

    generator = SiteGenerator(args.base_url, args.output)
    generator.generate()


if __name__ == '__main__':
    main()