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

import url_builders
from product_library import (
    load_products as load_product_library,
    approved_products,
    get_quality_dashboard,
    print_quality_dashboard,
    category_display,
    category_slug,
)
from product_engine import (
    normalize_category,
    categories_match,
    compatibility_priority,
    is_compatible_with_bike,
    get_compatibility_label,
    get_fitment_details,
    ranking_score,
    enforce_brand_diversity,
    find_products_by_category,
    select_product_count,
    recommend_products,
    recommend_for_category,
    recommend_for_motorcycle,
    recommend_sidebar_products,
    filter_compatible_products,
    group_products_by_category,
    count_products_by_category,
    best_per_category,
    category_to_guide_url,
    deduplicate_products,
    assign_editorial_tiers,
    get_editorial_recommendation,
    validate_category_products as _validate_category_products,
    validate_motorcycle_products as _validate_motorcycle_products,
    CATEGORY_KEYWORDS,
    CATEGORY_GUIDE_SLUGS,
    VALID_CATEGORIES,
    MIN_PRODUCTS,
    PREFERRED_PRODUCTS,
    MAX_PRODUCTS,
)

HELMET_ICON = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14a8 8 0 0 1 16 0"/><path d="M4 14c0-4.4 3.6-8 8-8s8 3.6 8 8"/><path d="M4 14v2a2 2 0 0 0 2 2h1"/><path d="M18 14c0 0 2 0 2 2v1"/><line x1="10" y1="18" x2="14" y2="18"/><path d="M6 10h12" stroke-dasharray="2 2"/></svg>'
HELMET_ICON_SM = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14a8 8 0 0 1 16 0"/><path d="M4 14c0-4.4 3.6-8 8-8s8 3.6 8 8"/><path d="M4 14v2a2 2 0 0 0 2 2h1"/><path d="M18 14c0 0 2 0 2 2v1"/><line x1="10" y1="18" x2="14" y2="18"/><path d="M6 10h12" stroke-dasharray="2 2"/></svg>'

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
AFFILIATE_ID = 'xuy0834-21'
SITE_NAME = 'BikeReview India'
DEFAULT_BASE_URL = ''

# Category aliases, normalize_category, and VALID_CATEGORIES
# are now imported from product_engine.py


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

    # Load products via the product library (handles nested JSON + flattening)
    products_dir = DATA_DIR / 'products'
    data['products'] = load_product_library(products_dir)

    # Attach a baseline editorial recommendation tier to every product so no
    # template ever falls back to a misleading "0/5" or "(0 reviews)".  Tiers
    # are derived deterministically from real recommendation-engine signals
    # (editorial signal, value for money, brand, availability) - never from a
    # fabricated Amazon rating.  Pages may later refine tiers per candidate
    # pool via _attach_editorial().
    for _p in data['products']:
        _tier = get_editorial_recommendation(_p)
        if _tier:
            _p['editorial'] = _tier
        else:
            _p.pop('editorial', None)

    # Print quality dashboard
    dashboard = get_quality_dashboard()
    if dashboard:
        print_quality_dashboard(dashboard)

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


# Identity fields that define a product and must NEVER be overwritten
# once the product object has been created.
_IDENTITY_FIELDS = ('asin', 'affiliate_url', 'amazon_url')

_ASIN_RE = re.compile(r'(?:/dp/|/gp/product/|asin=)([A-Z0-9]{10})', re.IGNORECASE)
_ASIN_RE_URL2 = re.compile(r'([A-Z0-9]{10})(?:[/?]|$)')


def _extract_asin(value):
    """Extract a 10-char Amazon ASIN from a string (URL or raw ASIN)."""
    if not value:
        return ''
    m = _ASIN_RE.search(value)
    if m:
        return m.group(1).upper()
    m = _ASIN_RE_URL2.search(value)
    if m:
        return m.group(1).upper()
    return ''


def _normalize_title(title):
    """Normalize a title for exact-match comparison.

    Lowercases, collapses whitespace, and strips noise tokens that vary
    between the catalog and Amazon listings (certifications, marketing
    copy, color/style suffixes) so two names referring to the same product
    match exactly.
    """
    if not title:
        return ''
    t = title.lower()
    # Remove common marketing / certification noise
    noise = [
        'isi certified', 'isi', 'dot certified', 'dot', 'ece', 'certified',
        'with', 'full face', 'open face', 'flip up', 'modular', 'half face',
        'motorcycle', 'helmet', 'bike', 'for', 'and', 'the',
    ]
    for n in noise:
        t = t.replace(n, ' ')
    # Keep alphanumerics + spaces only
    t = re.sub(r'[^a-z0-9 ]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _parse_model(title):
    """Extract the product model token from a title.

    Models are typically the distinctive capitalized word/phrase unique to
    the product (e.g. 'raider super', 'ray super', 'aster dx'). We take the
    normalized title with the brand and generic category words removed.
    """
    if not title:
        return ''
    t = _normalize_title(title)
    return t


def merge_bike_deals(products, deals_by_asin):
    """Enrich products with Amazon image/price data WITHOUT altering identity.

    Product identity (asin, affiliate_url, amazon_url) is fixed at creation
    and must NEVER change. Fuzzy/similarity matching has been removed entirely:
    a deal is only allowed to enrich a product when ONE of these holds:

      1. Same ASIN (product.asin == deal.asin)
      2. Same extracted Amazon ASIN (ASIN parsed from product.affiliate_url /
         amazon_url equals deal.asin)
      3. Exact normalized title match
      4. Same brand AND same parsed model

    Otherwise the product is left untouched. It is better to have no
    affiliate URL than to attach the wrong Amazon product.

    Only MISSING, non-identity fields are filled in:
      - amazon_image_url (image)  — from deal images
      - price                     — from deal Buy Box (only on a confident match)

    Identity fields on the product are never written or overwritten.
    """
    merged_count = 0

    # Build a fast index of deals for exact-match strategies.
    deals_by_asin_lc = {a.lower(): d for a, d in deals_by_asin.items()}
    deals_by_title = {}
    deals_by_brand_model = {}
    for d in deals_by_asin.values():
        dt = d.get('itemInfo', {}).get('title', {}).get('displayValue', '')
        ntitle = _normalize_title(dt)
        if ntitle:
            deals_by_title.setdefault(ntitle, d)
        dbrand = (d.get('brand') or '').strip().lower()
        dmodel = _parse_model(dt)
        if dbrand and dmodel:
            deals_by_brand_model.setdefault((dbrand, dmodel), d)

    def find_matching_deal(product):
        """Return (deal, match_type) or (None, None) using only exact matches."""
        # 1. Same ASIN
        asin = (product.get('asin') or '').strip().upper()
        if asin and asin.lower() in deals_by_asin_lc:
            return deals_by_asin_lc[asin.lower()], 'asin'

        # 2. Same extracted Amazon ASIN (from an existing affiliate/amazon URL)
        for field in ('affiliate_url', 'amazon_url'):
            url = product.get(field, '')
            extracted = _extract_asin(url)
            if extracted and extracted.lower() in deals_by_asin_lc:
                return deals_by_asin_lc[extracted.lower()], 'url_asin'

        # 3. Exact normalized title
        ptitle = _normalize_title(product.get('title', ''))
        if ptitle and ptitle in deals_by_title:
            return deals_by_title[ptitle], 'title'

        # 4. Same brand + same parsed model
        pbrand = (product.get('brand') or '').strip().lower()
        pmodel = _parse_model(product.get('title', ''))
        if pbrand and pmodel and (pbrand, pmodel) in deals_by_brand_model:
            return deals_by_brand_model[(pbrand, pmodel)], 'brand_model'

        return None, None

    for product in products:
        deal, match_type = find_matching_deal(product)

        if not deal:
            # No confident match — leave the product untouched.
            continue

        # Enrich ONLY missing, non-identity fields.
        images = deal.get('images', {})
        primary = images.get('primary', {})
        large_img = primary.get('large', {})
        image_url = large_img.get('url', '')
        if image_url and not product.get('amazon_image_url') and not product.get('image'):
            product['amazon_image_url'] = image_url

        # Price: ALWAYS refreshed from a confident (ASIN-level) match.
        # A newer Buy Box price must replace any stale cached value; we never
        # keep an old price just because one was already present.
        if match_type in ('asin', 'url_asin'):
            offers = deal.get('offersV2', {})
            listings = offers.get('listings', [])
            new_price = None
            new_mrp = None
            for listing in listings:
                if listing.get('isBuyBoxWinner'):
                    price_money = listing.get('price', {}).get('money', {})
                    amount = price_money.get('amount')
                    if amount:
                        new_price = int(float(amount))
                    saving = listing.get('savingBasis', {})
                    mrp_amount = saving.get('money', {}).get('amount')
                    if mrp_amount:
                        new_mrp = int(float(mrp_amount))
                    break
            if new_price:
                now_iso = datetime.now().isoformat()
                # Preserve an existing structured pricing object if present.
                existing = product.get('pricing') or {}
                product['pricing'] = {
                    'current': new_price,
                    'mrp': new_mrp,
                    'discount_percent': int(round((new_mrp - new_price) / new_mrp * 100))
                    if (new_mrp and new_mrp > new_price) else existing.get('discount_percent'),
                    'currency': existing.get('currency', 'INR'),
                    'last_updated': now_iso,
                    'source': 'amazon_sync',
                }
                product['price'] = new_price
                if new_mrp:
                    product['mrp'] = new_mrp

        merged_count += 1

    return merged_count


def render_markdown(text):
    """Convert markdown text to HTML."""
    extensions = ['tables', 'fenced_code', 'codehilite', 'toc']
    return markdown.markdown(text, extensions=extensions)


def replace_product_placeholders(html, products, base_path='./', exclude_slugs=None):
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
    - Cross-section deduplication: exclude_slugs prevents products already
      shown in other sections from appearing again
    """
    if exclude_slugs is None:
        exclude_slugs = set()
    placeholder_pattern = re.compile(
        r'\{\{\s*(products|product_pick|category_summary):([^}]+?)\s*\}\}'
    )

    def find_products_for_category(category_name: str) -> list:
        """Find products matching a category, using product_engine search."""
        return find_products_by_category(products, category_name)

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

        # Per AI_INSTRUCTIONS.md: never render a product card without a real image
        if not image or 'images/' not in image:
            return ''
        
        image_html = f'<img src="{base_path}{image}" alt="{title}" loading="lazy">'

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
        <h4><a href="{url_builders.product_url(slug, base_path)}">{title}</a></h4>
        <div class="product-inline-rating">
            <span class="stars">{stars_html}</span>
            <span class="rating-value">{rating}</span>
            <span class="review-count">({reviews})</span>
        </div>
        <div class="product-inline-price">₹{price:,}</div>
        <p class="product-inline-verdict">{"Best for: " + best_for if best_for else verdict[:150]}<br><em>{verdict[:120]}</em></p>
        <div class="product-inline-actions">
            <a href="{url_builders.product_url(slug, base_path)}" class="btn btn-sm">Details</a>
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

        # Filter out products already shown in other sections
        if exclude_slugs:
            matched = [p for p in matched if p.get('slug') not in exclude_slugs]
            if not matched:
                return ''

        # Use product_engine ranking (editorial signal + rating + reviews + price)
        matched.sort(key=lambda p: ranking_score(p), reverse=True)

        # Enforce brand diversity: max 2 from same brand
        matched = enforce_brand_diversity(matched, max_per_brand=2)

        if pick:
            # Pick mode: only first item, show as a single card with badge
            product = matched[0]
            return '<div class="product-inline-grid">\n' + make_card(product, base_path, pick) + '</div>\n'

        # Use select_product_count from product_engine for consistent count management
        if limit is None:
            limit = select_product_count(len(matched))
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
        
        view_all_url = url_builders.category_url(category, base_path)
        
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
    """Group products by normalized category (delegates to product_engine).

    Excludes non-motorcycle categories (e.g., bicycle_helmet, fashion_jacket)
    that are intentionally routed out of the motorcycle taxonomy.
    """
    grouped = group_products_by_category(products)
    excluded = {'bicycle_helmet', 'fashion_jacket'}
    return {cat: prods for cat, prods in grouped.items() if cat not in excluded}


def match_products_to_motorcycle(bike, products):
    """Match products to a motorcycle using product_engine.

    Delegates entirely to product_engine.filter_compatible_products.
    Returns products sorted by compatibility priority + ranking score.
    """
    return filter_compatible_products(products, bike)


def get_products_by_category(products: list, category: str) -> list:
    """Get products for a specific category, sorted by ranking score.
    
    Delegates to product_engine.find_products_by_category for search,
    then sorts by ranking_score.
    """
    matched = find_products_by_category(products, category)
    matched.sort(key=lambda p: ranking_score(p), reverse=True)
    return matched


def get_category_product_count(products: list, category: str) -> int:
    """Get count of products in a category."""
    return count_products_by_category(products, category)




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



def get_featured_products(products, count=6):
    """Get featured products using product_engine recommendation.
    
    Uses recommend_products (no bike context) for consistent scoring,
    brand diversity, and count management.
    """
    # Use a broad category search to get top products across all categories
    ranked = recommend_products(products, 'helmet')
    # If we need more products, also search other popular categories
    if len(ranked) < count:
        for cat in ['phone mount', 'chain lube', 'engine oil']:
            extra = recommend_products(products, cat)
            seen = {p.get('slug') for p in ranked}
            for p in extra:
                if p.get('slug') not in seen:
                    ranked.append(p)
                    seen.add(p.get('slug'))
                    if len(ranked) >= count:
                        break
            if len(ranked) >= count:
                break
    return ranked[:count]


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
    
    for i, product in enumerate(products):
        title = product.get('title', f'Product #{i+1}')
        slug = product.get('slug', f'unknown-{i}')
        
        # Missing category
        if not product.get('category'):
            warnings.append(f"  ! {title} ({slug}): Missing 'category' field")
        
        # Missing compatibility
        if not product.get('compatible_bikes'):
            warnings.append(f"  ! {title} ({slug}): Missing 'compatible_bikes' - will not appear on any motorcycle page")
        
        # Missing affiliate URL
        if not product.get('affiliate_url'):
            warnings.append(f"  ! {title} ({slug}): Missing 'affiliate_url' - no buy link")
        
        # Missing image
        if not product.get('image'):
            warnings.append(f"  ! {title} ({slug}): Missing 'image' - will show placeholder")
        
        # Invalid category
        category = product.get('category', '')
        if category:
            normalized = normalize_category(category).lower()
            if normalized not in VALID_CATEGORIES:
                warnings.append(f"  ! {title} ({slug}): Unknown category '{category}' (normalized: '{normalize_category(category)}')")
        
        # Duplicate ASIN check
        asin = product.get('asin', '')
        if asin:
            if asin in seen_asins:
                warnings.append(f"  ! {title} ({slug}): Duplicate ASIN '{asin}' (also in {seen_asins[asin]})")
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
            warnings.append(f"  ! {model} ({slug}): Missing 'categories' field")
        
        if not bike.get('brand'):
            warnings.append(f"  ! {model} ({slug}): Missing 'brand' field")
    
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
        self.env.globals['category_to_guide_url'] = category_to_guide_url
        self.env.globals['URL'] = url_builders.URL
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

        # ===== Navigation context =====
        # Motorcycles grouped by brand for mega menu
        motorcycles_by_brand = {}
        for bike in self.data['motorcycles']:
            brand = bike.get('brand', 'Other')
            if brand not in motorcycles_by_brand:
                motorcycles_by_brand[brand] = []
            motorcycles_by_brand[brand].append({
                'model': bike.get('model', ''),
                'slug': bike.get('slug', ''),
            })
        # Sort brands and models
        sorted_nav_brands = {}
        for brand in sorted(motorcycles_by_brand.keys()):
            sorted_nav_brands[brand] = sorted(motorcycles_by_brand[brand], key=lambda b: b['model'])

        # Accessory categories for nav dropdown
        # Only include categories that actually have products
        accessory_nav_items = []
        seen_cats = set()
        for product in self.data['products']:
            cat = normalize_category(product.get('category', ''))
            slug = category_slug(cat)
            if cat not in seen_cats:
                accessory_nav_items.append({'name': cat, 'slug': slug})
                seen_cats.add(cat)

        # Guide categories for nav (article category index pages)
        guide_categories = []

        # Accessory brands only (exclude motorcycle manufacturers)
        motorcycle_brand_names = {
            'Royal Enfield', 'Honda', 'Bajaj', 'Hero', 'TVS', 'Yamaha',
            'KTM', 'Suzuki', 'Triumph', 'Harley-Davidson', 'Kawasaki',
        }
        accessory_brands = [
            b for b in self.data['brands']
            if b['name'] not in motorcycle_brand_names
        ][:15]

        garage_bikes = []
        for bike in self.data['motorcycles']:
            garage_bikes.append({
                'slug': bike.get('slug', ''),
                'brand': bike.get('brand', ''),
                'model': bike.get('model', ''),
            })
        garage_bikes.sort(key=lambda b: (b['brand'], b['model']))

        return {
            'brands': self.data['brands'],
            'motorcycles': self.data['motorcycles'],
            'nav_motorcycles_by_brand': sorted_nav_brands,
            'nav_accessory_categories': accessory_nav_items,
            'nav_guide_categories': guide_categories,
            'nav_accessory_brands': accessory_brands,
            'garage_bikes': garage_bikes,
            'meta_title': meta_title,
            'meta_description': meta_description,
            'canonical_url': canonical_url or self.base_url + '/',
            'base_path': base_path,
        }

    def _attach_editorial(self, products, category=None, bike=None):
        """Attach an editorial recommendation tier to each product in place.

        The tier is derived deterministically from the recommendation engine
        (editorial signal, value for money, compatibility, brand, availability)
        via assign_editorial_tiers.  No Amazon rating is used and no value is
        ever hardcoded.  Products that do not rank in the top tiers receive no
        'editorial' key, so templates render NO stars for them.

        Returns the slug -> tier dict for convenience.
        """
        tiers = assign_editorial_tiers(products, category, bike)
        for p in products:
            slug = p.get('slug') or p.get('asin') or ''
            if slug in tiers:
                p['editorial'] = tiers[slug]
            else:
                p.pop('editorial', None)
        return tiers

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

        # ===== Motorcycle manufacturer brands only (exclude accessory brands) =====
        motorcycle_brand_names = {
            'Royal Enfield', 'Honda', 'Bajaj', 'Hero', 'TVS', 'Yamaha',
            'KTM', 'Suzuki', 'Triumph', 'Harley-Davidson', 'Kawasaki',
        }
        motorcycle_brands = [
            b for b in self.data['brands']
            if b['name'] in motorcycle_brand_names
        ]
        context['motorcycle_brands'] = motorcycle_brands

        # ===== Enrich motorcycle data with accessory counts =====
        enriched_bikes = []
        for bike in self.data['motorcycles']:
            b = dict(bike)
            matched = match_products_to_motorcycle(bike, self.data['products'])
            b['accessory_count'] = len(matched)
            enriched_bikes.append(b)
        context['motorcycles'] = enriched_bikes

        # ===== Featured motorcycles (8-12 popular bikes) =====
        popular_slugs = [
            'royal-enfield-classic-350', 'royal-enfield-hunter-350',
            'royal-enfield-himalayan-450', 'royal-enfield-bullet-350',
            'honda-hness-cb350', 'honda-cb350rs',
            'bajaj-pulsar-ns200', 'yamaha-mt-15',
            'tvS-apache-rtr-200', 'royal-enfield-guerrilla-450',
            'hero-xpulse-200', 'bajaj-pulsar-n250',
        ]
        featured_bikes = [
            b for b in enriched_bikes
            if b.get('slug') in popular_slugs
        ]
        if len(featured_bikes) < 8:
            featured_bikes = enriched_bikes[:12]
        context['featured_bikes'] = featured_bikes[:12]

        # ===== Popular searches (for smart search suggestions) =====
        context['popular_searches'] = [
            'Hunter 350', 'Classic 350', 'CB350', 'Himalayan 450',
            'NS200', 'MT15', 'Apache RTR 200', 'Bullet 350',
        ]

        # ===== Trending buying guides =====
        context['trending_guides'] = [
            {'title': 'Best Helmets', 'slug': 'helmet', 'icon': HELMET_ICON_SM, 'description': 'Full face, flip-up & modular helmets reviewed'},
            {'title': 'Best Phone Mounts', 'slug': 'phone-mount', 'icon': '&#128241;', 'description': 'Vibration-free handlebar phone holders'},
            {'title': 'Best Engine Oil', 'slug': 'engine-oil', 'icon': '&#128737;', 'description': 'Mineral, semi-synthetic & fully synthetic oils'},
            {'title': 'Best Chain Lube', 'slug': 'chain-lube', 'icon': '&#9881;', 'description': 'Keep your chain running smoothly'},
            {'title': 'Best Tyre Inflators', 'slug': 'tyre-inflator', 'icon': '&#128295;', 'description': 'Portable digital & analog inflators'},
        ]

        # ===== Comparisons data =====
        comparisons = []
        comparison_pairs = [
            ('royal-enfield-hunter-350', 'honda-hness-cb350', 'Hunter 350 vs CB350'),
            ('royal-enfield-classic-350', 'bajaj-pulsar-n250', 'Classic 350 vs Pulsar'),
            ('bajaj-pulsar-ns200', 'tvS-apache-rtr-200', 'NS200 vs RTR 200'),
            ('yamaha-mt-15', 'yamaha-r15', 'MT15 vs R15'),
            ('hero-xpulse-200', 'royal-enfield-himalayan-450', 'XPulse vs Himalayan'),
        ]
        bike_map = {b['slug']: b for b in enriched_bikes}
        for slug1, slug2, label in comparison_pairs:
            b1 = bike_map.get(slug1)
            b2 = bike_map.get(slug2)
            if b1 and b2:
                comparisons.append({
                    'label': label,
                    'bike1': b1,
                    'bike2': b2,
                })
        context['comparisons'] = comparisons

        # Featured products for recommendations (top rated, one per category)
        # Uses product_engine.best_per_category — single source of truth.
        # Covers one quality product from every major supported category.
        categories_wanted = [
            'Helmet', 'Gloves', 'Jackets', 'Phone Mount',
            'Engine Oil', 'Chain Lube', 'Chain Cleaner', 'Bike Cover',
            'Disc Lock', 'Tank Bag', 'Saddle Bag', 'USB Charger',
            'Crash Guard', 'Leg Guard', 'Tyre Inflator', 'Action Camera',
        ]
        featured_products = best_per_category(
            self.data['products'], categories_wanted
        )
        context['featured_products'] = featured_products

        # Track slugs already used in featured_products to avoid duplicates
        featured_slugs = {p.get('slug') for p in featured_products}

        # Editor's picks (curated top products per category)
        # Must not duplicate products already shown in featured_products.
        # One pick per major category that has quality products.
        editors_picks = []
        pick_categories = {
            'Helmet': 'Best Helmet',
            'Gloves': 'Best Riding Gloves',
            'Jackets': 'Best Riding Jacket',
            'Phone Mount': 'Best Phone Mount',
            'Engine Oil': 'Best Engine Oil',
            'Chain Lube': 'Best Chain Lube',
            'Chain Cleaner': 'Best Chain Cleaner',
            'Bike Cover': 'Best Bike Cover',
            'Disc Lock': 'Best Disc Lock',
            'Tank Bag': 'Best Tank Bag',
            'Saddle Bag': 'Best Saddle Bag',
            'USB Charger': 'Best USB Charger',
            'Crash Guard': 'Best Crash Guard',
            'Leg Guard': 'Best Leg Guard',
            'Tyre Inflator': 'Best Tyre Inflator',
            'Action Camera': 'Best Action Camera',
        }
        for cat, label in pick_categories.items():
            rec = recommend_for_category(self.data['products'], cat)
            pick = None
            for candidate in [rec['editors_choice'], rec['best_value'],
                              rec['premium_pick'], rec['most_popular']]:
                if candidate and candidate.get('slug') not in featured_slugs:
                    pick = candidate
                    break
            if pick:
                pick = dict(pick)
                pick['pick_label'] = label
                editors_picks.append(pick)
                featured_slugs.add(pick.get('slug'))
        context['editors_picks'] = editors_picks

        # ===== Dynamic stats (never hardcoded) =====
        context['stats'] = {
            'guides': len(self.data['articles']),
            'products_reviewed': len(self.data['products']),
            'motorcycles': len(self.data['motorcycles']),
            'brands': len(self.data['brands']),
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

    def generate_brand_listing(self):
        """Generate brands index page."""
        context = self.build_base_context(
            meta_title='Motorcycle Brands in India - Reviews & Guides | BikeReview India',
            meta_description='Browse all motorcycle brands in India. Find models, specifications, prices, and best accessories.',
            canonical_url=f"{self.base_url}/brands/",
            output_path='brands/index.html',
        )
        context['brands'] = sorted(self.data['brands'], key=lambda x: x['name'])
        content = self.render_template('brands.html', context)
        self.write_page('brands/index.html', content)

    def generate_motorcycle_listing(self):
        """Generate motorcycles index page."""
        context = self.build_base_context(
            meta_title='All Motorcycles in India - Specs, Prices & Accessories | BikeReview India',
            meta_description='Browse all motorcycles available in India. Find specifications, prices, best accessories, and buying guides.',
            canonical_url=f"{self.base_url}/motorcycles/",
            output_path='motorcycles/index.html',
        )
        context['motorcycles'] = sorted(self.data['motorcycles'], key=lambda x: (x['brand'], x['model']))
        content = self.render_template('motorcycles.html', context)
        self.write_page('motorcycles/index.html', content)

    def build_motorcycle_editorial(self, bike: dict, base_path: str = '') -> dict:
        """Build bike-specific editorial content from motorcycle data.

        Generates natural, rider-focused content that avoids generic
        AI-sounding phrases. Every piece of content answers a real
        rider question.
        """
        model = bike['model']
        brand = bike['brand']
        btype = bike.get('type', '')
        engine_cc = float(re.search(r'(\d+\.?\d*)', bike.get('engine', '0')).group(1))
        power_bhp = float(re.search(r'(\d+\.?\d*)', bike.get('power', '0')).group(1))
        weight_kg = float(re.search(r'(\d+\.?\d*)', bike.get('weight', '0')).group(1))
        seat = bike.get('seat_height', '')
        mileage_str = bike.get('mileage', '')
        mileage_val = float(re.search(r'(\d+)', mileage_str).group(1)) if re.search(r'(\d+)', mileage_str) else 0
        price_num = bike.get('price_numeric', 0)

        editorial = {}

        # ===== Not Ideal For =====
        not_ideal_map = {
            'Adventure': [
                'Riders who only commute in city traffic',
                'Buyers on a tight budget',
            ],
            'Cruiser': [
                'Sport riding and track day enthusiasts',
                'Off-road adventure seekers',
            ],
            'Sport': [
                'Daily long-distance commuters',
                'Riders who prioritize comfort over speed',
            ],
            'Naked': [
                'Highway touring without aftermarket windscreen',
                'Off-road adventures',
            ],
            'Retro Classic': [
                'Riders seeking modern electronics',
                'Sport-oriented riders',
            ],
            'Scooter': [
                'Highway touring riders',
                'Off-road enthusiasts',
            ],
            'Commuter': [
                'Highway touring enthusiasts',
                'Performance-oriented riders',
            ],
        }
        editorial['not_ideal_for'] = not_ideal_map.get(btype, [
            'Long-distance touring without mods',
            'Off-road adventures',
        ])

        # ===== Riding Use Cases =====
        use_cases = []

        # Daily Riding
        daily_desc = {
            'Cruiser': f'The relaxed riding position makes the {model} comfortable for daily commutes. The torquey engine pulls through traffic without needing to rev hard.',
            'Sport': f'The aggressive riding position can get tiring in heavy traffic, but the {model} shines on short city rides where its sharp handling stands out.',
            'Adventure': f'Daily commuting on the {model} is comfortable thanks to the upright seating. The wide handlebars give good leverage in traffic, though the size takes some getting used to.',
            'Naked': f'The {model} feels at home in city traffic. Upright ergonomics, light clutch, and responsive throttle make daily riding effortless.',
            'Retro Classic': f'The {model} handles daily commuting well with its comfortable seat and manageable power. The classic design turns heads even in bumper-to-bumper traffic.',
            'Commuter': f'Built for this. The {model} sips fuel, navigates tight lanes easily, and requires minimal maintenance. This is what it was designed for.',
        }
        use_cases.append({
            'icon': '&#128663;',
            'title': 'Daily Riding',
            'description': daily_desc.get(btype, f'Well-suited for daily commuting with comfortable ergonomics and good fuel efficiency.'),
        })

        # Highway Riding
        highway_desc = {
            'Adventure': f'Designed for highway miles. The {model} stays stable at speed, and the wind protection reduces fatigue on long stretches.',
            'Cruiser': f'Highway cruising is where the {model} excels. The relaxed position, strong mid-range, and planted feel at speed make long highway days enjoyable.',
            'Sport': f'The {model} is fast on the highway, but wind blast becomes a factor after a couple of hours. A windscreen helps, but this bike rewards shorter highway stints.',
            'Naked': f'Capable on the highway for moderate distances. Without a windscreen, you will feel the wind at higher speeds. Add a fly screen for better highway comfort.',
            'Retro Classic': f'The {model} can handle highway rides, but it is not a tourer. Stick to moderate distances and the engine will reward you with its characterful thump.',
            'Commuter': f'Highway rides are possible but keep them short. The {model} lacks the power and wind protection for sustained high-speed cruising.',
        }
        use_cases.append({
            'icon': '&#128740;',
            'title': 'Highway Riding',
            'description': highway_desc.get(btype, f'Capable on highways for moderate distances. Consider adding a windscreen for better comfort.'),
        })

        # Touring
        touring_desc = {
            'Adventure': f'The {model} is built for touring. Comfortable seat, large tank, and luggage-ready design mean you can load up and ride for days.',
            'Cruiser': f'Long rides on the {model} are a pleasure. The relaxed riding position, ample torque, and comfortable seat make it a solid touring machine.',
            'Sport': f'The {model} can tour, but it requires planning. A comfortable seat, tank bag, and regular breaks make multi-day rides manageable.',
            'Naked': f'With saddlebags and a comfortable seat, the {model} handles touring duties. It is more of a weekend getaway bike than a cross-country tourer.',
            'Retro Classic': f'The {model} has character for days, but touring requires some mods. A better seat and saddlebags turn it into a capable weekend tourer.',
            'Commuter': f'The {model} is not built for touring. Short weekend rides are fine, but anything longer will leave you wanting more comfort and power.',
        }
        use_cases.append({
            'icon': '&#127758;',
            'title': 'Touring',
            'description': touring_desc.get(btype, f'With proper accessories like saddlebags and a comfortable seat, the {model} can handle touring duties.'),
        })

        # City Riding
        city_desc = {
            'Naked': f'Excellent in the city. The {model} is nimble, easy to filter with, and the upright position gives you great visibility in traffic.',
            'Adventure': f'Manageable in the city, but the size can be a handful in tight spaces. The wide bars need some care between buses and autos.',
            'Cruiser': f'The {model} cruises through city traffic comfortably. The low seat height inspires confidence, and the torque means you do not need to downshift constantly.',
            'Sport': f'City riding is doable but not ideal. The aggressive position gets tiring, and the engine runs hot in slow traffic.',
            'Retro Classic': f'The {model} is a city-friendly bike. Manageable weight, comfortable seat, and good low-end make it easy to ride in urban conditions.',
            'Commuter': f'This is the {model}\u2019s natural habitat. Light, fuel-efficient, and easy to manoeuvre through traffic. It is why millions of Indians ride one.',
        }
        use_cases.append({
            'icon': '&#127961;',
            'title': 'City Riding',
            'description': city_desc.get(btype, f'Good city motorcycle with manageable power and comfortable ergonomics for daily use.'),
        })

        editorial['riding_use_cases'] = use_cases

        # ===== Buyer Setups =====
        # Tailored based on bike type and price
        is_premium = price_num > 250000
        is_budget = price_num < 100000

        setups = []

        # Budget Rider
        budget_items = ['Helmet (ISI certified)', 'Phone Mount', 'Chain Lube']
        budget_cost = '2,500 - 3,000'
        if engine_cc <= 150:
            budget_desc = f'Just the basics to keep your {model} safe and maintained. A good helmet, phone mount for navigation, and chain lube for regular upkeep.'
        else:
            budget_desc = f'Start with the essentials. A certified helmet, phone mount for navigation, and chain lube to keep the drivetrain happy.'
        setups.append({
            'icon': '&#128665;',
            'name': 'Budget Rider',
            'budget': 'Under &#8377;3,000',
            'description': budget_desc,
            'included': budget_items,
            'estimated_cost': f'\u20b9{budget_cost}',
            'who': 'Students, first-time buyers, daily commuters on a budget',
        })

        # Daily Commuter
        commuter_items = ['Helmet', 'Phone Mount', 'Bike Cover', 'Chain Lube']
        commuter_cost = '3,500 - 5,000'
        if mileage_val >= 50:
            commuter_desc = f'Protect your daily ride. A proper helmet, phone mount for Google Maps, bike cover for parking, and chain lube to keep that excellent mileage consistent.'
        else:
            commuter_desc = f'Everything you need for the daily grind. Safety gear, navigation, and basic maintenance products to keep the {model} running smoothly.'
        setups.append({
            'icon': '&#128665;',
            'name': 'Daily Commuter',
            'budget': 'Under &#8377;5,000',
            'description': commuter_desc,
            'included': commuter_items,
            'estimated_cost': f'\u20b9{commuter_cost}',
            'who': 'Office goers, daily riders, anyone riding 20+ km daily',
        })

        # Weekend Rider
        weekend_items = ['Everything in Commuter', 'Crash Guard', 'Riding Gloves', 'Tyre Inflator']
        weekend_cost = '8,000 - 10,000'
        weekend_desc = f'For Saturday morning rides and Sunday coffee runs. Crash protection, proper gloves, and a tyre inflator for peace of mind on longer rides.'
        setups.append({
            'icon': '&#127754;',
            'name': 'Weekend Rider',
            'budget': 'Under &#8377;10,000',
            'description': weekend_desc,
            'included': weekend_items,
            'estimated_cost': f'\u20b9{weekend_cost}',
            'who': 'Weekend warriors, scenic route riders, motorcycle enthusiasts',
        })

        # Touring
        touring_items = ['Everything in Weekend', 'Riding Jacket', 'Saddle Bag', 'Tank Bag']
        touring_cost = '15,000 - 20,000'
        if btype in ['Adventure', 'Cruiser']:
            touring_desc_text = f'The {model} is ready for long hauls. Luggage, riding gear, and protection for you and the bike on multi-day trips.'
        else:
            touring_desc_text = f'Make the {model} tour-ready. Luggage solutions, riding jacket, and gear to handle long highway stretches comfortably.'
        setups.append({
            'icon': '&#127758;',
            'name': 'Touring',
            'budget': 'Under &#8377;20,000',
            'description': touring_desc_text,
            'included': touring_items,
            'estimated_cost': f'\u20b9{touring_cost}',
            'who': 'Touring enthusiasts, long-distance riders, road trip lovers',
        })

        # Premium
        premium_items = ['Premium Helmet', 'Premium Crash Guard', 'All Riding Gear', 'Full Luggage Set']
        premium_desc = f'No compromises. The best gear and accessories for the {model} \u2014 because you and your bike deserve it.'
        setups.append({
            'icon': '&#128081;',
            'name': 'Premium',
            'budget': 'No Limit',
            'description': premium_desc,
            'included': premium_items,
            'estimated_cost': '\u20b925,000+',
            'who': 'Riders who want the absolute best',
        })

        editorial['buyer_setups'] = setups

        # ===== Pro Tip (Must-Have section) =====
        if btype in ['Sport']:
            editorial['pro_tip'] = 'Helmet first, always. Then a crash guard \u2014 these bikes get dropped in parking lots. After that, riding gloves and a phone mount round out the essentials.'
        elif btype in ['Adventure']:
            editorial['pro_tip'] = 'Start with a quality helmet and crash guards. Adventure bikes take spills on trails, so protection is non-negotiable. Add a phone mount and tyre inflator next.'
        elif btype in ['Cruiser']:
            editorial['pro_tip'] = 'A good helmet is your first purchase. Then a crash guard to protect those chrome bits. Saddlebags and a backrest come next for comfortable two-up riding.'
        elif engine_cc <= 125:
            editorial['pro_tip'] = 'Helmet is mandatory and non-negotiable. Add a bike cover for parking and chain lube for maintenance. Keep it simple \u2014 this bike does not need much.'
        else:
            editorial['pro_tip'] = 'Buy your helmet and crash guard first \u2014 they protect you and the bike. Then add a phone mount for navigation and a bike cover for parking.'

        # ===== Must-Have Descriptions =====
        # Keys must be canonical snake_case categories.
        must_have_desc = {
            'helmet': 'Non-negotiable. A good helmet is the single most important piece of gear you will ever buy. Do not cheap out here.',
            'phone_mount': 'Mount your phone for navigation without holding it. Get a vibration-free mount \u2014 it protects your phone camera from the bike\'s vibrations.',
            'crash_guard': 'One tip-over in a parking lot can cost thousands in repairs. A crash guard pays for itself the first time the bike goes down.',
            'engine_oil': 'The lifeblood of your engine. Use the manufacturer-recommended grade \u2014 wrong oil grades cause long-term damage that warranty will not cover.',
            'chain_lube': 'A dry chain wears out fast and affects performance. Lube it every 500 km and it will last significantly longer.',
            'bike_cover': 'Sun, rain, and dust are your paint\'s enemies. A breathable cover keeps the {model} looking fresh, especially if you park outdoors.',
            'gloves': 'Your hands are the first thing to hit the ground in a fall. Good gloves also reduce fatigue on longer rides.',
            'jackets': 'A proper riding jacket with armour protects your shoulders, elbows, and back. Mesh for summer, waterproof for monsoon.',
            'tyre_inflator': 'A flat tyre on the side of the road is every rider\'s nightmare. A portable inflator takes up no space and saves you every time.',
            'chain_cleaner': 'Degreaser removes grime before you lube. A clean chain lasts longer and delivers power more smoothly.',
            'tank_bag': 'Keep essentials within reach \u2014 phone, wallet, keys, water. Magnetic tank bags are quick on and off.',
            'saddle_bag': 'Soft or hard saddlebags carry more than a backpack ever will. Essential for touring and daily commuting.',
            'usb_charger': 'Keep your phone and GPS charged on long rides. Wire it straight from the battery \u2014 no draining the bike\'s electronics.',
            'disc_lock': 'A visible disc lock is the cheapest insurance against parking-lot theft. Get one with an alarm.',
            'chain_lock': 'Chain your bike to something fixed. A heavy-duty chain lock stops casual theft and deters opportunists.',
        }
        editorial['must_have_descriptions'] = must_have_desc

        # ===== FAQ Items =====
        faq_items = []

        faq_items.append({
            'question': f'What is the on-road price of {brand} {model}?',
            'answer': f'The {brand} {model} is priced at \u20b9{bike["price"]} ex-showroom. On-road prices vary by city \u2014 expect roughly 10-15% more depending on your state\'s road tax and insurance.',
        })

        faq_items.append({
            'question': f'What is the real-world mileage of {model}?',
            'answer': f'The {model} delivers around {mileage_str} according to ARAI tests. In real-world city conditions, expect 10-15% less. Highway riding usually gets closer to the claimed figure.',
        })

        # Long rides FAQ
        if btype in ['Adventure', 'Cruiser']:
            faq_items.append({
                'question': f'Is {model} good for long rides?',
                'answer': f'Yes. The {model} is built for long-distance riding. { "The upright seating and wind protection keep fatigue low on highway stretches." if btype == "Adventure" else "The relaxed position and torquey engine make highway cruising effortless." }',
            })
        else:
            faq_items.append({
                'question': f'Is {model} good for long rides?',
                'answer': f'The {model} handles moderate long-distance rides well. For multi-day touring, invest in a comfortable seat, windscreen, and luggage. It is not a dedicated tourer, but with the right setup, it gets the job done.',
            })

        # Best accessories FAQ
        guide_links = []
        for guide_cat in ['helmet', 'phone_mount', 'engine_oil', 'chain_lube']:
            url = category_to_guide_url(guide_cat, base_path)
            if url != '#':
                guide_links.append(f'<a href="{url}">{category_display(guide_cat).lower()} guide</a>')
        guide_text = ', '.join(guide_links) if guide_links else 'our buying guides'
        faq_items.append({
            'question': f'What are the best accessories for {model}?',
            'answer': f'Start with a helmet, phone mount, and essential maintenance products. Browse {guide_text} for category-specific recommendations.',
        })

        # Service interval FAQ
        faq_items.append({
            'question': f'How often should I service my {model}?',
            'answer': f'Follow the manufacturer\'s schedule \u2014 typically every {bike.get("service_interval", "3,000 km")}. Regular oil changes, chain maintenance, and brake checks keep the bike running right.',
        })

        # ABS FAQ
        faq_items.append({
            'question': f'Does {model} have ABS?',
            'answer': f'Yes, the {model} comes with {bike.get("abs", "single-channel")} ABS. { "Dual-channel ABS is a significant safety advantage \u2014 both wheels are covered." if "dual" in bike.get("abs", "").lower() else "Single-channel ABS covers the front wheel, which is where most braking happens." }',
        })

        # Seat height FAQ
        seat_mm = int(re.search(r'(\d+)', seat).group(1)) if re.search(r'(\d+)', seat) else 0
        if seat_mm >= 800:
            seat_answer = f'The {model} has a seat height of {seat}. Riders under 5\'6" may want to test sit before buying \u2014 flat feet at stops inspire confidence.'
        else:
            seat_answer = f'The {model} has a seat height of {seat}. This should work comfortably for most Indian riders.'
        faq_items.append({
            'question': f'What is the seat height of {model}?',
            'answer': seat_answer,
        })

        # Beginners FAQ
        if btype in ['Sport']:
            faq_items.append({
                'question': f'Is {model} good for beginners?',
                'answer': f'The {model} has {power_bhp} bhp \u2014 it is a serious machine. Experienced riders will love it, but complete beginners should consider starting with something smaller and upgrading once they have the basics down.',
            })
        elif btype in ['Adventure'] and engine_cc > 400:
            faq_items.append({
                'question': f'Is {model} good for beginners?',
                'answer': f'The {model} is a large, powerful motorcycle. Riders with some experience will handle it well, but beginners should look at smaller adventure bikes first and work their way up.',
            })
        else:
            faq_items.append({
                'question': f'Is {model} good for beginners?',
                'answer': f'Yes. The {model} is well-balanced with manageable power, making it suitable for new riders. Just invest in proper safety gear and take it easy while you build confidence.',
            })

        # Touring FAQ
        if btype in ['Adventure', 'Cruiser']:
            faq_items.append({
                'question': f'Is {model} good for touring?',
                'answer': f'Absolutely. The {model} is designed for touring with comfortable ergonomics and a large fuel tank. {"Load up the saddlebags and hit the highway \u2014 this is what it was built for." if btype == "Adventure" else "The relaxed position and strong mid-range make long highway days enjoyable."}',
            })
        else:
            faq_items.append({
                'question': f'Is {model} good for touring?',
                'answer': f'The {model} can tour, but it needs some setup. A comfortable seat, windscreen, and saddlebags make a big difference. It is more suited for weekend trips than cross-country adventures.',
            })

        # Top speed FAQ (using actual power data instead of hardcoded 120-130)
        if power_bhp >= 40:
            top_speed = '150+ km/h'
        elif power_bhp >= 25:
            top_speed = '120-140 km/h'
        elif power_bhp >= 15:
            top_speed = '100-120 km/h'
        elif power_bhp >= 10:
            top_speed = '85-100 km/h'
        else:
            top_speed = '80-90 km/h'
        faq_items.append({
            'question': f'What is the top speed of {model}?',
            'answer': f'The {model} can reach around {top_speed} depending on rider weight, road conditions, and wind. These are approximate figures \u2014 we do not recommend testing top speed on public roads.',
        })

        editorial['faq_items'] = faq_items

        # ===== New Owner Tips =====
        new_owner_tips = []

        # First service tip
        new_owner_tips.append({
            'icon': '&#9881;',
            'title': 'First Service',
            'description': f'Schedule your first service at {bike.get("service_interval", "500-1000 km")}. Do not skip it — the first service breaks in the engine properly.',
            'link': f'motorcycles/{bike.get("slug", "")}/maintenance/engine-oil/index.html',
            'link_text': 'Engine Oil Guide',
        })

        # Break-in period tip
        if engine_cc > 150:
            new_owner_tips.append({
                'icon': '&#128161;',
                'title': 'Break-In Period',
                'description': 'Keep RPMs under 4000 for the first 500 km. Vary your speed, do not cruise at constant RPM, and avoid hard acceleration. This sets up your engine for years of reliable service.',
                'link': '',
                'link_text': '',
            })

        # Basic maintenance tip
        new_owner_tips.append({
            'icon': '&#128295;',
            'title': 'Basic Maintenance',
            'description': 'Check tyre pressure weekly. A properly inflated tyre improves mileage, handling, and safety. Keep the chain clean and lubed every 500 km.',
            'link': f'motorcycles/{bike.get("slug", "")}/maintenance/tyre-pressure/index.html',
            'link_text': 'Tyre Pressure Guide',
        })

        # Insurance tip
        new_owner_tips.append({
            'icon': '&#128179;',
            'title': 'Insurance',
            'description': 'Get comprehensive insurance for at least the first year. Third-party only covers damage to others, not your bike. Add zero-depreciation if available.',
            'link': '',
            'link_text': '',
        })

        # Parking tip
        if btype in ['Sport', 'Naked']:
            new_owner_tips.append({
                'icon': '&#128205;',
                'title': 'Parking',
                'description': 'Always use the side stand on level ground. These bikes are top-heavy and prone to tip-overs in parking lots. A crash guard is cheap insurance.',
                'link': '',
                'link_text': '',
            })

        editorial['new_owner_tips'] = new_owner_tips

        return editorial

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

            # Build bike-specific editorial content
            editorial = self.build_motorcycle_editorial(bike, context['base_path'])

            # Match products to motorcycle (used for main content + sidebar)
            matched = match_products_to_motorcycle(bike, self.data['products'])

            # Related articles
            related = []
            for article in self.data['articles']:
                related_bikes = article.get('related_motorcycles', [])
                if bike['slug'] in related_bikes:
                    related.append(article)
            context['related_articles'] = related[:4]

            # ===== NEW HUB PAGE DATA =====

            # Quick Specs card data
            context['quick_specs'] = {
                'price': bike.get('price'),
                'mileage': bike.get('mileage'),
                'power': bike.get('power'),
                'torque': bike.get('torque'),
                'weight': bike.get('weight'),
                'fuel_tank': bike.get('fuel_tank') or bike.get('fuel_capacity'),
                'seat_height': bike.get('seat_height', 'N/A'),
                'abs': bike.get('abs', 'N/A'),
                'service_interval': bike.get('service_interval', 'N/A'),
                'variants': bike.get('variants', []),
            }

            # Quick Accessory Navigation (links include ?bike= for deep-linking into guides)
            bike_slug = bike['slug']
            context['accessory_nav'] = [
                {'name': 'Helmet', 'icon': HELMET_ICON_SM, 'slug': category_slug('helmet'), 'guide_url': category_to_guide_url('helmet', context['base_path'], bike_slug)},
                {'name': 'Phone Mount', 'icon': '&#128241;', 'slug': category_slug('phone_mount'), 'guide_url': category_to_guide_url('phone_mount', context['base_path'], bike_slug)},
                {'name': 'Engine Oil', 'icon': '&#128737;', 'slug': category_slug('engine_oil'), 'guide_url': category_to_guide_url('engine_oil', context['base_path'], bike_slug)},
                {'name': 'Chain Lube', 'icon': '&#9881;', 'slug': category_slug('chain_lube'), 'guide_url': category_to_guide_url('chain_lube', context['base_path'], bike_slug)},
                {'name': 'Tyre Inflator', 'icon': '&#128295;', 'slug': category_slug('tyre_inflator'), 'guide_url': category_to_guide_url('tyre_inflator', context['base_path'], bike_slug)},
            ]

            # Must Have Accessories — 15 categories across 5 groups
            # Uses recommend_for_motorcycle from product_engine for scoring and deduplication
            must_have_data = recommend_for_motorcycle(
                self.data['products'], bike, editorial=editorial,
            )
            seen_slugs = set()
            for item in must_have_data:
                for p in item['products']:
                    seen_slugs.add(p['slug'])
                guide_url = category_to_guide_url(item['category'], context['base_path'], bike_slug)
                if guide_url == '#':
                    # Try first actual product category as fallback
                    product_cats = set()
                    for p in item['products']:
                        cat = p.get('category', '')
                        if cat:
                            product_cats.add(cat)
                    if product_cats:
                        first_cat = sorted(product_cats)[0]
                        guide_url = url_builders.category_url(first_cat, context['base_path'])
                item['guide_url'] = guide_url
            context['must_have_data'] = must_have_data

            # ===== Sidebar products (excludes products shown in Must Have) =====
            sidebar_products = recommend_sidebar_products(
                self.data['products'], bike=bike, max_products=5,
            )
            sidebar_products = [
                sp for sp in sidebar_products
                if sp['product'].get('slug') not in seen_slugs
            ]
            for sp in sidebar_products:
                seen_slugs.add(sp['product'].get('slug'))
            context['sidebar_products'] = sidebar_products
            # Debug output
            bike_name = f"{bike.get('brand', '')} {bike.get('model', '')}"
            print(f"    Sidebar [{bike_name}]: {len(sidebar_products)} products")
            for sp in sidebar_products:
                p = sp['product']
                print(f"      - [{sp['category']}] {p.get('brand', '')} {p.get('title', '')[:40]} ({sp['reason']})")

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

            # Related guides from bike's related_articles list
            related_guides = []
            for article in self.data['articles']:
                if article.get('slug') in bike.get('related_articles', []):
                    related_guides.append(article)
            context['related_guides'] = related_guides[:5]

            # Common problems
            context['common_problems'] = bike.get('common_problems', [])

            # Buying advice - use editorial version if available, fallback to JSON
            raw_advice = bike.get('buying_advice', {})
            context['buying_advice'] = {
                'buy_first': raw_advice.get('buy_first', ['Helmet', 'Crash Guard', 'Bike Cover']),
                'avoid': raw_advice.get('avoid', ['Cheap helmet replicas', 'Non-ISI certified gear', 'Generic chain lubes']),
                'oem_vs_aftermarket': raw_advice.get('oem_vs_aftermarket', ''),
                'money_saving_tips': raw_advice.get('money_saving_tips', []),
                'common_mistakes': raw_advice.get('common_mistakes', []),
            }

            # Editorial content (riding use cases, not ideal for, buyer setups, etc.)
            context['editorial'] = editorial

            # Maintenance schedule for timeline
            context['maintenance_schedule'] = [
                {'interval': '500 km', 'task': 'First Service', 'description': 'Basic inspection, chain lube, tyre pressure check'},
                {'interval': '3,000 km', 'task': 'Oil Change', 'description': 'Engine oil replacement, air filter cleaning'},
                {'interval': '6,000 km', 'task': 'Chain Service', 'description': 'Chain and sprocket inspection, valve clearance check'},
                {'interval': '12,000 km', 'task': 'Brake Inspection', 'description': 'Brake pad replacement, fork oil change'},
            ]

            # Build recommended products for ownership hub
            # Use the exact same structure as motorcycle.html
            recommended_products = {}
            
            # Get picks for each category
            engine_oil_rec = recommend_for_category(matched, 'Engine Oil', bike)
            bike_cover_rec = recommend_for_category(matched, 'Bike Cover', bike)
            phone_mount_rec = recommend_for_category(matched, 'Phone Mount', bike)
            helmet_rec = recommend_for_category(matched, 'Helmet', bike)
            
            # Maintenance Essentials
            if engine_oil_rec.get('editors_choice') or engine_oil_rec.get('best_value') or engine_oil_rec.get('premium_pick'):
                recommended_products['maintenance_essentials'] = {}
                if engine_oil_rec.get('editors_choice'):
                    recommended_products['maintenance_essentials']['editor_choice'] = {
                        'image': engine_oil_rec['editors_choice'].get('image', ''),
                        'name': engine_oil_rec['editors_choice'].get('title', ''),
                        'rating': engine_oil_rec['editors_choice'].get('rating', 0),
                        'price': engine_oil_rec['editors_choice'].get('price', 0),
                        'summary': engine_oil_rec['editors_choice'].get('verdict', ''),
                        'url': '',
                    }
                if engine_oil_rec.get('best_value'):
                    recommended_products['maintenance_essentials']['best_value'] = {
                        'image': engine_oil_rec['best_value'].get('image', ''),
                        'name': engine_oil_rec['best_value'].get('title', ''),
                        'rating': engine_oil_rec['best_value'].get('rating', 0),
                        'price': engine_oil_rec['best_value'].get('price', 0),
                        'summary': engine_oil_rec['best_value'].get('verdict', ''),
                        'url': '',
                    }
                if engine_oil_rec.get('premium_pick'):
                    recommended_products['maintenance_essentials']['premium_pick'] = {
                        'image': engine_oil_rec['premium_pick'].get('image', ''),
                        'name': engine_oil_rec['premium_pick'].get('title', ''),
                        'rating': engine_oil_rec['premium_pick'].get('rating', 0),
                        'price': engine_oil_rec['premium_pick'].get('price', 0),
                        'summary': engine_oil_rec['premium_pick'].get('verdict', ''),
                        'url': '',
                    }
            
            # Protection
            if bike_cover_rec.get('editors_choice') or bike_cover_rec.get('best_value'):
                recommended_products['protection'] = {}
                if bike_cover_rec.get('editors_choice'):
                    recommended_products['protection']['editor_choice'] = {
                        'image': bike_cover_rec['editors_choice'].get('image', ''),
                        'name': bike_cover_rec['editors_choice'].get('title', ''),
                        'rating': bike_cover_rec['editors_choice'].get('rating', 0),
                        'price': bike_cover_rec['editors_choice'].get('price', 0),
                        'summary': bike_cover_rec['editors_choice'].get('verdict', ''),
                        'url': '',
                    }
                if bike_cover_rec.get('best_value'):
                    recommended_products['protection']['best_value'] = {
                        'image': bike_cover_rec['best_value'].get('image', ''),
                        'name': bike_cover_rec['best_value'].get('title', ''),
                        'rating': bike_cover_rec['best_value'].get('rating', 0),
                        'price': bike_cover_rec['best_value'].get('price', 0),
                        'summary': bike_cover_rec['best_value'].get('verdict', ''),
                        'url': '',
                    }
            
            # Daily Riding
            if phone_mount_rec.get('editors_choice') or phone_mount_rec.get('best_value') or phone_mount_rec.get('premium_pick'):
                recommended_products['daily_riding'] = {}
                if phone_mount_rec.get('editors_choice'):
                    recommended_products['daily_riding']['editor_choice'] = {
                        'image': phone_mount_rec['editors_choice'].get('image', ''),
                        'name': phone_mount_rec['editors_choice'].get('title', ''),
                        'rating': phone_mount_rec['editors_choice'].get('rating', 0),
                        'price': phone_mount_rec['editors_choice'].get('price', 0),
                        'summary': phone_mount_rec['editors_choice'].get('verdict', ''),
                        'url': '',
                    }
                if phone_mount_rec.get('best_value'):
                    recommended_products['daily_riding']['best_value'] = {
                        'image': phone_mount_rec['best_value'].get('image', ''),
                        'name': phone_mount_rec['best_value'].get('title', ''),
                        'rating': phone_mount_rec['best_value'].get('rating', 0),
                        'price': phone_mount_rec['best_value'].get('price', 0),
                        'summary': phone_mount_rec['best_value'].get('verdict', ''),
                        'url': '',
                    }
                if phone_mount_rec.get('premium_pick'):
                    recommended_products['daily_riding']['premium_pick'] = {
                        'image': phone_mount_rec['premium_pick'].get('image', ''),
                        'name': phone_mount_rec['premium_pick'].get('title', ''),
                        'rating': phone_mount_rec['premium_pick'].get('rating', 0),
                        'price': phone_mount_rec['premium_pick'].get('price', 0),
                        'summary': phone_mount_rec['premium_pick'].get('verdict', ''),
                        'url': '',
                    }
            
            # Riding Gear
            if helmet_rec.get('editors_choice') or helmet_rec.get('best_value') or helmet_rec.get('premium_pick'):
                recommended_products['riding_gear'] = {}
                if helmet_rec.get('editors_choice'):
                    recommended_products['riding_gear']['editor_choice'] = {
                        'image': helmet_rec['editors_choice'].get('image', ''),
                        'name': helmet_rec['editors_choice'].get('title', ''),
                        'rating': helmet_rec['editors_choice'].get('rating', 0),
                        'price': helmet_rec['editors_choice'].get('price', 0),
                        'summary': helmet_rec['editors_choice'].get('verdict', ''),
                        'url': '',
                    }
                if helmet_rec.get('best_value'):
                    recommended_products['riding_gear']['best_value'] = {
                        'image': helmet_rec['best_value'].get('image', ''),
                        'name': helmet_rec['best_value'].get('title', ''),
                        'rating': helmet_rec['best_value'].get('rating', 0),
                        'price': helmet_rec['best_value'].get('price', 0),
                        'summary': helmet_rec['best_value'].get('verdict', ''),
                        'url': '',
                    }
                if helmet_rec.get('premium_pick'):
                    recommended_products['riding_gear']['premium_pick'] = {
                        'image': helmet_rec['premium_pick'].get('image', ''),
                        'name': helmet_rec['premium_pick'].get('title', ''),
                        'rating': helmet_rec['premium_pick'].get('rating', 0),
                        'price': helmet_rec['premium_pick'].get('price', 0),
                        'summary': helmet_rec['premium_pick'].get('verdict', ''),
                        'url': '',
                    }
            
            # Apply correct recommended products structure to context
            context['recommended_products'] = recommended_products
            
            # Riding Gear - Helmet category picks
            helmet_rec = recommend_for_category(matched, 'Helmet', bike)
            if helmet_rec.get('editors_choice'):
                if 'riding_gear' not in recommended_products:
                    recommended_products['riding_gear'] = {}
                recommended_products['riding_gear']['editor_choice'] = {
                    'image': helmet_rec['editors_choice'].get('image', ''),
                    'name': helmet_rec['editors_choice'].get('title', ''),
                    'rating': helmet_rec['editors_choice'].get('rating', 0),
                    'price': helmet_rec['editors_choice'].get('price', 0),
                    'summary': helmet_rec['editors_choice'].get('verdict', ''),
                    'url': '',
                }
            if helmet_rec.get('best_value'):
                if 'riding_gear' not in recommended_products:
                    recommended_products['riding_gear'] = {}
                recommended_products['riding_gear']['best_value'] = {
                    'image': helmet_rec['best_value'].get('image', ''),
                    'name': helmet_rec['best_value'].get('title', ''),
                    'rating': helmet_rec['best_value'].get('rating', 0),
                    'price': helmet_rec['best_value'].get('price', 0),
                    'summary': helmet_rec['best_value'].get('verdict', ''),
                    'url': '',
                }
            if helmet_rec.get('premium_pick'):
                if 'riding_gear' not in recommended_products:
                    recommended_products['riding_gear'] = {}
                recommended_products['riding_gear']['premium_pick'] = {
                    'image': helmet_rec['premium_pick'].get('image', ''),
                    'name': helmet_rec['premium_pick'].get('title', ''),
                    'rating': helmet_rec['premium_pick'].get('rating', 0),
                    'price': helmet_rec['premium_pick'].get('price', 0),
                    'summary': helmet_rec['premium_pick'].get('verdict', ''),
                    'url': '',
                }
            
            # Build recommended products for ownership hub
            # Use the exact same structure as home.html
            # Get picks for each category
            engine_oil_rec = recommend_for_category(matched, 'Engine Oil', bike)
            bike_cover_rec = recommend_for_category(matched, 'Bike Cover', bike)
            phone_mount_rec = recommend_for_category(matched, 'Phone Mount', bike)
            helmet_rec = recommend_for_category(matched, 'Helmet', bike)
            
            # Build the structure matching the template expectations
            # Each section must contain editor_choice, best_value, and optionally premium_pick
            
            # Maintenance Essentials (Engine Oil)
            if engine_oil_rec.get('editors_choice') or engine_oil_rec.get('best_value') or engine_oil_rec.get('premium_pick'):
                recommended_products['maintenance_essentials'] = {}
                if engine_oil_rec.get('editors_choice'):
                    rec = engine_oil_rec['editors_choice']
                    recommended_products['maintenance_essentials']['editor_choice'] = {
                        'image': rec.get('image', ''),
                        'name': rec.get('title', ''),
                        'rating': rec.get('rating', 0),
                        'price': rec.get('price', 0),
                        'summary': rec.get('verdict', ''),
                        'url': '',
                    }
                if engine_oil_rec.get('best_value'):
                    rec = engine_oil_rec['best_value']
                    recommended_products['maintenance_essentials']['best_value'] = {
                        'image': rec.get('image', ''),
                        'name': rec.get('title', ''),
                        'rating': rec.get('rating', 0),
                        'price': rec.get('price', 0),
                        'summary': rec.get('verdict', ''),
                        'url': '',
                    }
                if engine_oil_rec.get('premium_pick'):
                    rec = engine_oil_rec['premium_pick']
                    recommended_products['maintenance_essentials']['premium_pick'] = {
                        'image': rec.get('image', ''),
                        'name': rec.get('title', ''),
                        'rating': rec.get('rating', 0),
                        'price': rec.get('price', 0),
                        'summary': rec.get('verdict', ''),
                        'url': '',
                    }
            
            # Protection (Bike Cover)
            if bike_cover_rec.get('editors_choice') or bike_cover_rec.get('best_value'):
                recommended_products['protection'] = {}
                if bike_cover_rec.get('editors_choice'):
                    rec = bike_cover_rec['editors_choice']
                    recommended_products['protection']['editor_choice'] = {
                        'image': rec.get('image', ''),
                        'name': rec.get('title', ''),
                        'rating': rec.get('rating', 0),
                        'price': rec.get('price', 0),
                        'summary': rec.get('verdict', ''),
                        'url': '',
                    }
                if bike_cover_rec.get('best_value'):
                    rec = bike_cover_rec['best_value']
                    recommended_products['protection']['best_value'] = {
                        'image': rec.get('image', ''),
                        'name': rec.get('title', ''),
                        'rating': rec.get('rating', 0),
                        'price': rec.get('price', 0),
                        'summary': rec.get('verdict', ''),
                        'url': '',
                    }
            
            # Daily Riding (Phone Mount)
            if phone_mount_rec.get('editors_choice') or phone_mount_rec.get('best_value') or phone_mount_rec.get('premium_pick'):
                recommended_products['daily_riding'] = {}
                if phone_mount_rec.get('editors_choice'):
                    rec = phone_mount_rec['editors_choice']
                    recommended_products['daily_riding']['editor_choice'] = {
                        'image': rec.get('image', ''),
                        'name': rec.get('title', ''),
                        'rating': rec.get('rating', 0),
                        'price': rec.get('price', 0),
                        'summary': rec.get('verdict', ''),
                        'url': '',
                    }
                if phone_mount_rec.get('best_value'):
                    rec = phone_mount_rec['best_value']
                    recommended_products['daily_riding']['best_value'] = {
                        'image': rec.get('image', ''),
                        'name': rec.get('title', ''),
                        'rating': rec.get('rating', 0),
                        'price': rec.get('price', 0),
                        'summary': rec.get('verdict', ''),
                        'url': '',
                    }
                if phone_mount_rec.get('premium_pick'):
                    rec = phone_mount_rec['premium_pick']
                    recommended_products['daily_riding']['premium_pick'] = {
                        'image': rec.get('image', ''),
                        'name': rec.get('title', ''),
                        'rating': rec.get('rating', 0),
                        'price': rec.get('price', 0),
                        'summary': rec.get('verdict', ''),
                        'url': '',
                    }
            
            # Riding Gear (Helmet)
            if helmet_rec.get('editors_choice') or helmet_rec.get('best_value') or helmet_rec.get('premium_pick'):
                recommended_products['riding_gear'] = {}
                if helmet_rec.get('editors_choice'):
                    rec = helmet_rec['editors_choice']
                    recommended_products['riding_gear']['editor_choice'] = {
                        'image': rec.get('image', ''),
                        'name': rec.get('title', ''),
                        'rating': rec.get('rating', 0),
                        'price': rec.get('price', 0),
                        'summary': rec.get('verdict', ''),
                        'url': '',
                    }
                if helmet_rec.get('best_value'):
                    rec = helmet_rec['best_value']
                    recommended_products['riding_gear']['best_value'] = {
                        'image': rec.get('image', ''),
                        'name': rec.get('title', ''),
                        'rating': rec.get('rating', 0),
                        'price': rec.get('price', 0),
                        'summary': rec.get('verdict', ''),
                        'url': '',
                    }
                if helmet_rec.get('premium_pick'):
                    rec = helmet_rec['premium_pick']
                    recommended_products['riding_gear']['premium_pick'] = {
                        'image': rec.get('image', ''),
                        'name': rec.get('title', ''),
                        'rating': rec.get('rating', 0),
                        'price': rec.get('price', 0),
                        'summary': rec.get('verdict', ''),
                        'url': '',
                    }
            
            context['recommended_products'] = recommended_products

            # Remove None values from recommended products and empty categories
            for category in ['maintenance_essentials', 'protection', 'daily_riding', 'riding_gear']:
                if category in context['recommended_products']:
                    for subcat in list(context['recommended_products'][category].keys()):
                        if context['recommended_products'][category][subcat] is None:
                            del context['recommended_products'][category][subcat]
                    if not context['recommended_products'][category]:
                        del context['recommended_products'][category]
            for category in ['maintenance_essentials', 'protection', 'daily_riding', 'riding_gear']:
                if category in context['recommended_products']:
                    for subcat in list(context['recommended_products'][category].keys()):
                        if context['recommended_products'][category][subcat] is None:
                            del context['recommended_products'][category][subcat]
                    if not context['recommended_products'][category]:
                        del context['recommended_products'][category]

            content = self.render_template('motorcycle.html', context)
            content = replace_product_placeholders(
                content, self.data['products'], context['base_path'],
                exclude_slugs=seen_slugs,
            )
            self.write_page(f'motorcycles/{bike["slug"]}/index.html', content)

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

                # Sidebar products (same engine as articles)
                sidebar_products = recommend_sidebar_products(
                    self.data['products'], bike=bike, max_products=4,
                )
                context['sidebar_products'] = sidebar_products
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
                {'name': product['category'], 'url': url_builders.category_url(product['category'], self.base_url + '/')},
                {'name': product['title']},
            ]

            # Sidebar products (same engine as articles and motorcycle pages)
            sidebar_products = recommend_sidebar_products(
                self.data['products'], product=product, max_products=4,
            )
            context['sidebar_products'] = sidebar_products
            # Debug output
            print(f"    Sidebar [product: {product.get('slug', '')}]: {len(sidebar_products)} products")
            for sp in sidebar_products:
                p = sp['product']
                print(f"      - [{sp['category']}] {p.get('brand', '')} {p.get('title', '')[:40]} ({sp['reason']})")

            # Related articles
            related = []
            for article in self.data['articles']:
                related_prods = article.get('related_products', [])
                if product['slug'] in related_prods:
                    related.append(article)
            context['related_articles'] = related[:4]

            content = self.render_template('product.html', context)
            self.write_page(f'products/{product["slug"]}/index.html', content)

    def _category_filter_config(self, cat_name):
        """Return category-specific filter options."""
        slug_lower = category_slug(cat_name)
        configs = {
            'helmet': {
                'filters': [
                    {'key': 'budget', 'label': 'Budget', 'options': ['Under ₹1500', '₹1500-3000', '₹3000-5000', '₹5000+']},
                    {'key': 'brand', 'label': 'Brand', 'dynamic': True},
                    {'key': 'type', 'label': 'Type', 'options': ['Full Face', 'Modular', 'Open Face', 'Half Face']},
                    {'key': 'isi', 'label': 'ISI Certified', 'type': 'checkbox'},
                    {'key': 'ece', 'label': 'ECE 22.06', 'type': 'checkbox'},
                    {'key': 'bluetooth', 'label': 'Bluetooth Ready', 'type': 'checkbox'},
                    {'key': 'pinlock', 'label': 'Pinlock Ready', 'type': 'checkbox'},
                    {'key': 'weight', 'label': 'Weight', 'options': ['Under 1400g', '1400-1600g', '1600g+']},
                    {'key': 'material', 'label': 'Material', 'options': ['ABS', 'Polycarbonate', 'Fiberglass', 'Carbon Fiber']},
                ]
            },
            'gloves': {
                'filters': [
                    {'key': 'budget', 'label': 'Budget', 'options': ['Under ₹500', '₹500-1000', '₹1000-2000', '₹2000+']},
                    {'key': 'brand', 'label': 'Brand', 'dynamic': True},
                    {'key': 'summer', 'label': 'Summer', 'type': 'checkbox'},
                    {'key': 'winter', 'label': 'Winter', 'type': 'checkbox'},
                    {'key': 'waterproof', 'label': 'Waterproof', 'type': 'checkbox'},
                    {'key': 'touchscreen', 'label': 'Touchscreen', 'type': 'checkbox'},
                    {'key': 'ce_protection', 'label': 'CE Protection', 'type': 'checkbox'},
                    {'key': 'leather', 'label': 'Leather', 'type': 'checkbox'},
                    {'key': 'mesh', 'label': 'Mesh', 'type': 'checkbox'},
                ]
            },
            'jackets': {
                'filters': [
                    {'key': 'budget', 'label': 'Budget', 'options': ['Under ₹2000', '₹2000-5000', '₹5000-10000', '₹10000+']},
                    {'key': 'brand', 'label': 'Brand', 'dynamic': True},
                    {'key': 'mesh', 'label': 'Mesh', 'type': 'checkbox'},
                    {'key': 'touring', 'label': 'Touring', 'type': 'checkbox'},
                    {'key': 'waterproof', 'label': 'Waterproof', 'type': 'checkbox'},
                    {'key': 'ce_level_2', 'label': 'CE Level 2', 'type': 'checkbox'},
                    {'key': 'rain', 'label': 'Rain', 'type': 'checkbox'},
                ]
            },
            'phone_mount': {
                'filters': [
                    {'key': 'budget', 'label': 'Budget', 'options': ['Under ₹500', '₹500-1000', '₹1000-2000', '₹2000+']},
                    {'key': 'brand', 'label': 'Brand', 'dynamic': True},
                    {'key': 'wireless_charging', 'label': 'Wireless Charging', 'type': 'checkbox'},
                    {'key': 'metal', 'label': 'Metal', 'type': 'checkbox'},
                    {'key': 'mirror_mount', 'label': 'Mirror Mount', 'type': 'checkbox'},
                    {'key': 'handlebar', 'label': 'Handlebar', 'type': 'checkbox'},
                ]
            },
            'chain_lube': {
                'filters': [
                    {'key': 'budget', 'label': 'Budget', 'options': ['Under ₹300', '₹300-500', '₹500-1000', '₹1000+']},
                    {'key': 'brand', 'label': 'Brand', 'dynamic': True},
                    {'key': 'wet_lube', 'label': 'Wet Lube', 'type': 'checkbox'},
                    {'key': 'dry_lube', 'label': 'Dry Lube', 'type': 'checkbox'},
                    {'key': 'ceramic', 'label': 'Ceramic', 'type': 'checkbox'},
                ]
            },
            'engine_oil': {
                'filters': [
                    {'key': 'budget', 'label': 'Budget', 'options': ['Under ₹300', '₹300-600', '₹600-1000', '₹1000+']},
                    {'key': 'brand', 'label': 'Brand', 'dynamic': True},
                    {'key': '10w30', 'label': '10W30', 'type': 'checkbox'},
                    {'key': '10w40', 'label': '10W40', 'type': 'checkbox'},
                    {'key': '15w50', 'label': '15W50', 'type': 'checkbox'},
                    {'key': 'synthetic', 'label': 'Synthetic', 'type': 'checkbox'},
                    {'key': 'semi_synthetic', 'label': 'Semi Synthetic', 'type': 'checkbox'},
                    {'key': 'mineral', 'label': 'Mineral', 'type': 'checkbox'},
                ]
            },
        }
        return configs.get(slug_lower, {
            'filters': [
                {'key': 'budget', 'label': 'Budget', 'options': ['Under ₹500', '₹500-1000', '₹1000-2000', '₹2000-5000', '₹5000+']},
                {'key': 'brand', 'label': 'Brand', 'dynamic': True},
            ]
        })

    def _extract_product_chips(self, product):
        """Extract feature chips from product data."""
        chips = []
        editorial = product.get('editorial', {})
        features = editorial.get('features', [])
        recommended_for = editorial.get('recommended_for', [])
        title = (product.get('title', '') or '').lower()
        ptype = (product.get('type', '') or '').lower()

        # Keyword-based chips
        keywords = {
            'isi': ['isi', 'isi certified'],
            'ece': ['ece', 'ece 22.06'],
            'waterproof': ['waterproof', 'water resistant'],
            'touchscreen': ['touchscreen', 'touch screen'],
            'bluetooth': ['bluetooth', 'intercom'],
            'pinlock': ['pinlock', 'anti-fog'],
            'lightweight': ['lightweight', 'light weight'],
            'mesh': ['mesh'],
            'leather': ['leather'],
            'ce': ['ce', 'ce certified', 'ce approved'],
            'synthetic': ['synthetic', 'fully synthetic'],
            'semi_synthetic': ['semi synthetic', 'semi-synthetic'],
            'mineral': ['mineral'],
            'wireless': ['wireless charging', 'wireless'],
            'metal': ['metal', 'aluminium', 'aluminum'],
            'carbon': ['carbon fiber', 'carbon fibre'],
        }
        for chip_key, kw_list in keywords.items():
            for kw in kw_list:
                if kw in title:
                    chips.append(chip_key.replace('_', ' ').title())
                    break

        # From type field
        type_chips = {
            'full face': 'Full Face',
            'modular': 'Modular',
            'open face': 'Open Face',
            'half face': 'Half Face',
            'mesh': 'Mesh',
            'leather': 'Leather',
        }
        for tc_key, tc_val in type_chips.items():
            if tc_key in ptype:
                if tc_val not in chips:
                    chips.append(tc_val)
                break

        # From editorial recommended_for
        rec_labels = {
            'budget': 'Budget Pick',
            'daily-commute': 'Daily Commute',
            'touring': 'Touring',
            'premium': 'Premium',
            'rain': 'Rain',
            'summer': 'Summer',
            'winter': 'Winter',
        }
        for rec in recommended_for:
            label = rec_labels.get(rec)
            if label and label not in chips:
                chips.append(label)

        return chips[:5]

    def generate_category_pages(self):
        """Generate category listing pages."""
        now = datetime.now()
        today_str = now.strftime('%B %d, %Y')

        # Guide content shared with bestof pages
        # Keys use snake_case (normalized category form) to match cat_name in the loop
        guide_content = {
            'helmet': {
                'buying_guide': {
                    'title': 'How to Choose the Right Motorcycle Helmet',
                    'intro': 'A helmet is the single most important piece of riding gear. Here are the key factors to consider before buying one.',
                    'factors': [
                        {'title': 'Safety Certification', 'text': 'Always choose ISI-certified helmets (IS 4151). DOT and ECE certifications offer additional international safety assurance.'},
                        {'title': 'Helmet Type', 'text': 'Full-face helmets offer maximum protection. Open-face helmets provide better visibility. Modular helmets combine both benefits.'},
                        {'title': 'Fit & Comfort', 'text': 'A helmet should fit snugly without pressure points. It should not rotate when you shake your head.'},
                        {'title': 'Ventilation', 'text': 'Multiple vents keep you cool in Indian summers. Look for chin and forehead vents at minimum.'},
                        {'title': 'Weight', 'text': 'Lighter helmets (under 1400g) reduce neck fatigue. Carbon fiber and composite shells are lighter than ABS.'},
                    ],
                },
                'faqs': [
                    {'question': 'Which is the safest helmet brand in India?', 'answer': 'Studds, Steelbird, Vega, Axor, and LS2 are all reputable brands offering ISI-certified helmets.'},
                    {'question': 'How often should I replace my helmet?', 'answer': 'Replace every 3-5 years or immediately after any impact. The inner foam degrades over time.'},
                    {'question': 'Is a Rs.3000 helmet safe enough?', 'answer': 'Yes, any ISI-certified helmet meets minimum safety standards.'},
                ],
            },
            'gloves': {
                'buying_guide': {
                    'title': 'How to Choose Riding Gloves',
                    'intro': 'Good riding gloves protect your hands in a fall and reduce fatigue on long rides. Here is what to look for.',
                    'factors': [
                        {'title': 'Protection', 'text': 'Look for CE-rated knuckle protection, palm sliders, and reinforced stitching. Leather offers the best abrasion resistance.'},
                        {'title': 'Season', 'text': 'Summer gloves use mesh for airflow. Winter gloves are insulated and often waterproof. All-season gloves compromise on both.'},
                        {'title': 'Fit', 'text': 'Gloves should be snug but not restrictive. Check finger length — too-long fingers bunch up and reduce feel.'},
                        {'title': 'Touchscreen Compatibility', 'text': 'Touchscreen fingertips let you use your phone without removing gloves. Essential for navigation.'},
                        {'title': 'Closure', 'text': 'Hook-and-loop wrist closures are standard. Gauntlet-style gloves go over your jacket for better weather sealing.'},
                    ],
                },
                'faqs': [
                    {'question': 'Are expensive riding gloves worth it?', 'answer': 'Yes. Premium gloves use better materials (leather, Kevlar), have CE-rated protection, and last longer. Budget gloves may lack proper armour.'},
                    {'question': 'Can I use cycling gloves for motorcycle riding?', 'answer': 'No. Cycling gloves lack abrasion resistance and impact protection. Always use gloves designed for motorcycles.'},
                ],
            },
            'jackets': {
                'buying_guide': {
                    'title': 'How to Choose a Riding Jacket',
                    'intro': 'A riding jacket with armour protects your upper body. The right jacket depends on your climate and riding style.',
                    'factors': [
                        {'title': 'Material', 'text': 'Leather offers the best protection but is hot. Textile (mesh, Cordura) is more versatile for Indian weather.'},
                        {'title': 'Armour', 'text': 'CE Level 2 armour at shoulders, elbows, and back is ideal. Level 1 is adequate for city riding.'},
                        {'title': 'Weather', 'text': 'Mesh jackets are best for summer. Waterproof jackets with removable liners work year-round in most climates.'},
                        {'title': 'Fit', 'text': 'Jackets should be snug with armour in place. Sizing varies by brand — always check the size chart.'},
                    ],
                },
                'faqs': [
                    {'question': 'Do I need a riding jacket for city riding?', 'answer': 'Yes. Even at city speeds, a jacket with armour protects your shoulders, elbows, and back in a fall.'},
                    {'question': 'Are mesh jackets safe?', 'answer': 'Modern mesh jackets use high-tenacity fibers that meet CE abrasion standards. They offer good protection with maximum airflow.'},
                ],
            },
        }

        # Budget ranges
        budget_ranges = [
            {'label': 'Under ₹500', 'slug': 'under-500', 'min': 0, 'max': 500, 'meta_desc': 'under ₹500'},
            {'label': '₹500–1000', 'slug': '500-1000', 'min': 500, 'max': 1000, 'meta_desc': '₹500-₹1000'},
            {'label': '₹1000–2000', 'slug': '1000-2000', 'min': 1000, 'max': 2000, 'meta_desc': '₹1000-₹2000'},
            {'label': '₹2000–5000', 'slug': '2000-5000', 'min': 2000, 'max': 5000, 'meta_desc': '₹2000-₹5000'},
            {'label': '₹5000+', 'slug': '5000-plus', 'min': 5000, 'max': 999999, 'meta_desc': 'above ₹5000'},
        ]

        # Common function to build category page context
        def build_category_page(cat_name, cat_products, base_path, is_all_products=False):
            ctx = {}
            ctx['category_name'] = cat_name
            ctx['products'] = cat_products
            ctx['total_products'] = len(cat_products)
            ctx['last_updated'] = today_str
            ctx['brands_list'] = sorted(set(p.get('brand', '') for p in cat_products))
            ctx['budget_ranges'] = budget_ranges
            ctx['is_all_products'] = is_all_products
            ctx['guide_content'] = guide_content.get(cat_name, {})
            ctx['filter_config'] = self._category_filter_config(cat_name)

            # Generate feature chips for each product
            for p in cat_products:
                p['_chips'] = self._extract_product_chips(p)
                p['_has_editorial'] = bool(p.get('editorial', {}).get('score', 0) > 0)
                p['_price'] = p.get('price', 0)
                p['_rating'] = p.get('rating', 0)
                p['_reviews'] = int(p.get('reviews', 0) or 0)

            # Get recommendation data for picks
            rec = recommend_for_category(self.data['products'], cat_name)
            ctx['recommendation'] = rec
            ctx['editors_choice'] = rec.get('editors_choice')
            ctx['best_value'] = rec.get('best_value')
            ctx['premium_pick'] = rec.get('premium_pick')
            ctx['most_popular'] = rec.get('most_popular')
            ctx['badge_data'] = rec.get('badge_data', {})

            # Attach editorial tiers
            self._attach_editorial(cat_products, cat_name)

            return ctx

        # All products page
        context = self.build_base_context(
            meta_title='All Products - Motorcycle Accessories & Gear | BikeReview India',
            meta_description='Browse our complete collection of motorcycle accessories, riding gear, maintenance products, and tools.',
            canonical_url=f"{self.base_url}/categories/",
            output_path='categories/index.html',
        )
        ctx = build_category_page('All Products', self.data['products'], context['base_path'], is_all_products=True)
        context.update(ctx)
        content = self.render_template('category.html', context)
        self.write_page('categories/index.html', content)

        # Individual category pages.
        all_categories = {}
        for p in getattr(self, 'all_products', self.data['products']):
            cat = normalize_category(p.get('category', ''))
            all_categories.setdefault(cat, []).append(p)
        surviving_slugs = {p.get('slug') for p in self.data['products']}
        for cat_name, cat_products in all_categories.items():
            slug = category_slug(cat_name)
            listed = [p for p in cat_products if p.get('slug') in surviving_slugs]
            context = self.build_base_context(
                meta_title=f'Best {cat_name} - Motorcycle {cat_name} | BikeReview India',
                meta_description=f'Best {cat_name.lower()} for Indian motorcycles. Expert reviews, buying guides, and top recommendations.',
                canonical_url=f"{self.base_url}/categories/{slug}/",
                output_path=f'categories/{slug}/index.html',
            )
            ctx = build_category_page(cat_name, listed, context['base_path'])
            context.update(ctx)
            content = self.render_template('category.html', context)
            self.write_page(f'categories/{slug}/index.html', content)

            # Generate budget sub-pages for SEO / crawlable budget URLs
            for br in budget_ranges:
                budget_slug = br['slug']
                if budget_slug == 'under-500':
                    budget_products = [p for p in listed if p.get('price', 0) <= br['max']]
                elif budget_slug == '5000-plus':
                    budget_products = [p for p in listed if p.get('price', 0) >= br['min']]
                else:
                    budget_products = [p for p in listed if br['min'] <= p.get('price', 0) < br['max']]

                budget_context = self.build_base_context(
                    meta_title=f'{br["label"]} {cat_name} - Motorcycle {cat_name} | BikeReview India',
                    meta_description=f'Best {cat_name.lower()} {br["meta_desc"]} for Indian motorcycles.',
                    canonical_url=f"{self.base_url}/categories/{slug}/{budget_slug}/",
                    output_path=f'categories/{slug}/{budget_slug}/index.html',
                )
                bctx = build_category_page(cat_name, budget_products, budget_context['base_path'])
                bctx['active_budget'] = br['slug']
                bctx['canonical_url'] = f"{self.base_url}/categories/{slug}/{budget_slug}/"
                budget_context.update(bctx)
                bcontent = self.render_template('category.html', budget_context)
                self.write_page(f'categories/{slug}/{budget_slug}/index.html', bcontent)

    def generate_bestof_pages(self):
        """Generate 'Best of' category pages for SEO.

        Each guide page is motorcycle-aware:
        - Passes all motorcycles for the selector dropdown
        - Embeds compatibility + fitment data so JS can filter/highlight
        - Assigns recommendation badges (editor's choice, best value, etc.)
        - Provides guide navigation links that preserve bike selection
        - Supports ?bike= query param for direct deep-links from motorcycle pages
        """
        bestof_pages = [
            {'slug': 'helmet', 'category': 'Helmet', 'title': 'Best Helmets', 'description': 'Find the best motorcycle helmets in India. Expert reviews, safety ratings, and buying recommendations for every budget.'},
            {'slug': 'phone-mount', 'category': 'Phone Mount', 'title': 'Best Phone Mounts', 'description': 'Top-rated motorcycle phone mounts and holders. vibration-free, secure, and easy to use options reviewed.'},
            {'slug': 'engine-oil', 'category': 'Engine Oil', 'title': 'Best Engine Oil', 'description': 'Best engine oils for Indian motorcycles. Mineral, semi-synthetic, and fully synthetic options compared.'},
            {'slug': 'chain-lube', 'category': 'Chain Lube', 'title': 'Best Chain Lubes', 'description': 'Best chain lubricants for motorcycle maintenance. Spray and drip-on options reviewed.'},
            {'slug': 'chain-cleaner', 'category': 'Chain Cleaner', 'title': 'Best Chain Cleaners', 'description': 'Best chain cleaners for motorcycle maintenance. Spray and gel options reviewed.'},
            {'slug': 'tyre-inflator', 'category': 'Tyre Inflator', 'title': 'Best Tyre Inflators', 'description': 'Best portable tyre inflators and air compressors for motorcycles. Digital and analog options reviewed.'},
        ]

        # Category-specific guide content for editorial sections
        # This is the single source of truth for buying guide editorial content.
        guide_content = {
            'Helmet': {
                'buying_guide': {
                    'title': 'How to Choose the Right Motorcycle Helmet',
                    'intro': 'A helmet is the single most important piece of riding gear. Here are the key factors to consider before buying one.',
                    'factors': [
                        {'title': 'Safety Certification', 'icon': '&#128737;', 'text': 'Always choose ISI-certified helmets (IS 4151). DOT and ECE certifications offer additional international safety assurance. Avoid non-certified decorative helmets.'},
                        {'title': 'Helmet Type', 'icon': '&#128065;', 'text': 'Full-face helmets offer maximum protection. Open-face helmets provide better visibility and airflow. Modular (flip-up) helmets combine both benefits but are heavier.'},
                        {'title': 'Fit & Comfort', 'icon': '&#128077;', 'text': 'A helmet should fit snugly without pressure points. It should not rotate when you shake your head. Try on helmets at the end of the day when your head is slightly larger.'},
                        {'title': 'Ventilation', 'icon': '&#128168;', 'text': 'Multiple vents with easy-to-use sliders keep you cool in Indian summers. Look for helmets with chin and forehead vents at minimum.'},
                        {'title': 'Visor Quality', 'icon': '&#128065;', 'text': 'Scratch-resistant, optically correct visors reduce eye strain. Anti-fog coating is essential for monsoon riding. Pinlock-ready visors are a worthwhile upgrade.'},
                        {'title': 'Weight', 'icon': '&#9878;', 'text': 'Lighter helmets (under 1400g) reduce neck fatigue on long rides. Carbon fiber and composite shells are lighter than pure ABS polycarbonate.'},
                    ],
                },
                'common_mistakes': [
                    {'title': 'Buying a helmet based on looks alone', 'text': 'Style matters, but safety certification and fit are more important. A flashy non-certified helmet is worse than a basic ISI-certified one.'},
                    {'title': 'Choosing the wrong size', 'text': 'A loose helmet can come off in an accident. Measure your head circumference and refer to the brand size chart. Never buy a helmet hoping it will break in.'},
                    {'title': 'Ignoring visor quality', 'text': 'A scratched or warped visor impairs vision. Replace visors every 12-18 months or immediately if scratched.'},
                    {'title': 'Not replacing after an impact', 'text': 'Helmets absorb impact through shell and foam deformation. After any crash, even a minor one, replace the helmet. Internal damage is not visible.'},
                    {'title': 'Skipping the chin strap check', 'text': 'The chin strap should allow only two fingers between the strap and your chin. Loose straps defeat the purpose of a well-fitted helmet.'},
                ],
                'maintenance_tips': [
                    'Clean the outer shell with mild soap and water. Avoid harsh chemicals that can degrade the shell material.',
                    'Hand-wash removable interior padding regularly with mild detergent. Let it air dry completely before reinstalling.',
                    'Store in a cool, dry place away from direct sunlight. UV exposure degrades the shell over time.',
                    'Replace the visor if scratched or after 18 months of regular use.',
                    'Check chin strap and buckle for wear every 6 months.',
                ],
                'faqs': [
                    {'question': 'Which is the safest helmet brand in India?', 'answer': 'Studds, Steelbird, Vega, Axor, and LS2 are all reputable brands offering ISI-certified helmets. The safest helmet is one that fits you correctly and has proper certification, regardless of brand.'},
                    {'question': 'Is a Rs.3000 helmet safe enough for daily use?', 'answer': 'Yes, any ISI-certified helmet meets minimum safety standards. More expensive helmets offer better comfort, ventilation, and additional certifications, but a basic certified helmet is far safer than a non-certified one.'},
                    {'question': 'How often should I replace my helmet?', 'answer': 'Replace every 3-5 years or immediately after any impact. The inner foam degrades over time even without crashes. Signs to replace: visible cracks, loose padding, or degraded chin strap.'},
                    {'question': 'Are expensive helmets worth it?', 'answer': 'Mid-range helmets (Rs.3000-7000) offer the best balance of safety, comfort, and durability. Premium helmets add lighter materials, advanced ventilation, and dual certifications, which matter for long-distance touring.'},
                    {'question': 'Can I use a half-face helmet for touring?', 'answer': 'Half-face helmets offer less protection and are not recommended for highway or touring use. Full-face helmets provide better wind protection, noise reduction, and impact safety at high speeds.'},
                ],
            },
            'Phone Mount': {
                'buying_guide': {
                    'title': 'How to Choose a Motorcycle Phone Mount',
                    'intro': 'A good phone mount keeps your navigation visible and your phone secure. Here is what matters most.',
                    'factors': [
                        {'title': 'Vibration Dampening', 'icon': '&#128256;', 'text': 'Motorcycle vibrations can damage phone camera stabilizers (OIS). Choose mounts with built-in vibration dampeners, especially if your bike has a single-cylinder engine.'},
                        {'title': 'Mounting Mechanism', 'icon': '&#128274;', 'text': 'X-grip and jaw-grip designs are the most secure. Avoid magnetic-only mounts, which can release on rough roads. Screw-on clamp mounts are the most reliable.'},
                        {'title': 'Handlebar Compatibility', 'icon': '&#128295;', 'text': 'Check your handlebar diameter (typically 22-32mm). Most universal mounts fit this range, but verify before buying. Some bikes need adapters.'},
                        {'title': 'Weather Resistance', 'icon': '&#127783;', 'text': 'Monsoon-proofing is essential in India. Look for waterproof designs or those with a silicone cover. Avoid mounts with exposed metal parts that rust.'},
                        {'title': 'Ease of Use', 'icon': '&#9889;', 'text': 'Quick-release mechanisms let you grab your phone at stops. One-hand operation is ideal. Test the mechanism in the shop before buying.'},
                        {'title': 'Phone Size Support', 'icon': '&#128241;', 'text': 'Ensure the mount supports your phone with its case. Most mounts handle 4-7 inch phones, but large phones with rugged cases need wider grips.'},
                    ],
                },
                'common_mistakes': [
                    {'title': 'Ignoring vibration dampening', 'text': 'Single-cylinder and v-twin motorcycles produce strong vibrations that damage phone cameras. Always choose a mount with a vibration damper.'},
                    {'title': 'Using magnetic mounts', 'text': 'Magnetic mounts look clean but can release on rough roads or during sudden braking. Use mechanical grips for security.'},
                    {'title': 'Not checking handlebar diameter', 'text': 'Not all mounts fit all handlebars. Measure your handlebar diameter before buying to avoid return hassles.'},
                    {'title': 'Cheap plastic clamps', 'text': 'Budget mounts often use brittle plastic that cracks in Indian heat. Invest in reinforced plastic or metal construction.'},
                    {'title': 'Mounting too close to controls', 'text': 'Position the mount where it does not interfere with handlebar movement, cables, or controls. Test full lock-to-lock steering before tightening.'},
                ],
                'maintenance_tips': [
                    'Tighten all screws and clamps before every long ride. Vibrations loosen mounts over time.',
                    'Clean the grip mechanism periodically to remove dust and grit that can reduce holding strength.',
                    'Apply silicone spray to moving parts (jaw-grip springs, quick-release mechanisms) every 3 months.',
                    'Replace rubber or silicone pads when worn, as they reduce grip strength.',
                    'If your mount has a vibration damper, check it for cracks or degradation every 6 months.',
                ],
                'faqs': [
                    {'question': 'Will a phone mount damage my phone camera?', 'text': 'Vibrations from single-cylinder engines can damage OIS (Optical Image Stabilization) in phone cameras over time. Always use a mount with a vibration damper to protect your phone.'},
                    {'question': 'What is the best type of phone mount for motorcycles?', 'answer': 'Jaw-grip or X-grip mounts with vibration dampeners offer the best balance of security and phone protection. Screw-on clamp mounts are the most reliable for rough roads.'},
                    {'question': 'How do I install a phone mount on my motorcycle?', 'answer': 'Most universal mounts clamp onto the handlebar (22-32mm diameter). Loosen the clamp bolt, position the mount, and tighten firmly. Avoid areas near controls or cables.'},
                    {'question': 'Can phone mounts work with waterproof phone cases?', 'answer': 'Yes, but ensure the mount grips wide enough. Most mounts support phones up to 85mm wide. Measure your phone with its case before buying.'},
                ],
            },
            'Engine Oil': {
                'buying_guide': {
                    'title': 'How to Choose the Right Engine Oil',
                    'intro': 'Engine oil is your motorcycle\'s lifeblood. The right oil protects your engine, improves performance, and extends engine life.',
                    'factors': [
                        {'title': 'Oil Grade (Viscosity)', 'icon': '&#128187;', 'text': 'Follow your owner\'s manual. Common grades for Indian bikes: 10W-30 for commuters, 10W-40 for performance bikes, 20W-50 for older engines. Never mix grades.'},
                        {'title': 'Oil Type', 'icon': '&#9881;', 'text': 'Mineral oil is cheapest but needs frequent changes. Semi-synthetic offers better protection at moderate cost. Fully synthetic provides maximum engine protection and longer change intervals.'},
                        {'title': 'Manufacturer Approval', 'icon': '&#10004;', 'text': 'Use oils that meet your motorcycle manufacturer\'s specifications (JASO MA2 for most Indian bikes). Using non-approved oils can void your warranty.'},
                        {'title': 'Change Interval', 'icon': '&#128197;', 'text': 'Mineral oil: every 2000-3000 km. Semi-synthetic: every 3000-4000 km. Fully synthetic: every 5000-6000 km. Always change oil with the filter.'},
                        {'title': 'Brand Reputation', 'icon': '&#127942;', 'text': 'Motul, Shell, Castrol, Liqui Moly, and Motorex are trusted brands in India. Stick to established brands to avoid counterfeit products.'},
                        {'title': 'Engine Condition', 'icon': '&#128295;', 'text': 'Newer engines benefit from synthetic oils. Older engines with higher mileage may perform better with mineral or semi-synthetic oils that have higher zinc content.'},
                    ],
                },
                'common_mistakes': [
                    {'title': 'Using the wrong viscosity grade', 'text': 'Always check your owner\'s manual. Using 20W-50 in a bike designed for 10W-30 increases fuel consumption and reduces cold-start protection.'},
                    {'title': 'Mixing oil brands and types', 'text': 'While technically possible, mixing different oils can reduce performance. Stick to one brand and type between changes.'},
                    {'title': 'Ignoring oil change intervals', 'text': 'Old oil loses its protective properties. Even if the oil looks clean, additives deplete over time. Follow the manufacturer\'s recommended interval.'},
                    {'title': 'Not changing the oil filter', 'text': 'A clogged oil filter restricts oil flow. Always replace the filter when changing oil, even if it looks clean.'},
                    {'title': 'Topping up instead of changing', 'text': 'Topping up oil masks leaks and does not replace degraded oil. If you regularly need to top up, get the engine inspected.'},
                ],
                'maintenance_tips': [
                    'Check oil level with the bike on the center stand, engine off, after 5 minutes of cooling.',
                    'Warm the engine for 2-3 minutes before draining old oil for a more complete drain.',
                    'Use a torque wrench when tightening the drain bolt to avoid stripping threads.',
                    'Keep the oil filler cap clean to prevent dirt from entering the engine.',
                    'Record your oil change date and mileage for accurate change interval tracking.',
                ],
                'faqs': [
                    {'question': 'Which oil is best for Royal Enfield Classic 350?', 'answer': 'Royal Enfield recommends 15W-50 semi-synthetic for the Classic 350. Motul 5100 15W-50 and Shell Advance AX7 15W-50 are popular choices that meet the manufacturer specification.'},
                    {'question': 'How often should I change my motorcycle oil?', 'answer': 'Mineral oil every 2000-3000 km, semi-synthetic every 3000-4000 km, fully synthetic every 5000-6000 km. Always follow your owner\'s manual recommendations.'},
                    {'question': 'Can I use car engine oil in my motorcycle?', 'answer': 'No. Motorcycle engines share oil with the clutch and gearbox, requiring JASO MA/MA2-rated oils. Car oils contain friction modifiers that can damage motorcycle clutches.'},
                    {'question': 'Is fully synthetic oil worth the extra cost?', 'answer': 'For performance bikes and frequent riders, yes. Synthetic oil lasts longer, protects better at extreme temperatures, and maintains viscosity longer. For casual commuters, semi-synthetic offers the best value.'},
                    {'question': 'What happens if I use the wrong oil grade?', 'answer': 'Using a heavier grade reduces fuel efficiency and cold-start protection. Using a lighter grade reduces film strength and increases engine wear. Always use the grade specified in your owner\'s manual.'},
                ],
            },
            'Chain Lube': {
                'buying_guide': {
                    'title': 'How to Choose Motorcycle Chain Lube',
                    'intro': 'A well-lubricated chain transfers power efficiently and lasts longer. Choosing the right lube depends on your riding conditions and maintenance routine.',
                    'factors': [
                        {'title': 'Lube Type', 'icon': '&#128293;', 'text': 'Wax-based lubes are clean and long-lasting. Oil-based lubes penetrate better but attract dirt. O-ring safe lubes are essential for modern sealed chains.'},
                        {'title': 'Application Method', 'icon': '&#128295;', 'text': 'Spray cans are convenient and even. Drip-on bottles offer precise application. Choose based on your comfort and how often you lube.'},
                        {'title': 'Weather Suitability', 'icon': '&#127783;', 'text': 'Wet-weather lubes resist water wash-off. In monsoon-heavy India, water-resistant lubes are essential for daily riders.'},
                        {'title': 'Chain Compatibility', 'icon': '&#9881;', 'text': 'Always use O-ring/X-ring safe lubes. petroleum-based solvents damage chain seals, leading to premature chain failure.'},
                        {'title': 'Dust Attraction', 'icon': '&#128168;', 'text': 'Sticky lubes attract dust and grit, accelerating chain wear. Wax-based and dry lubes attract less debris, important for dusty Indian roads.'},
                        {'title': 'Drying Time', 'icon': '&#9203;', 'text': 'Fast-drying lubes let you ride sooner after application. Some lubes need 30 minutes to set. Choose based on your maintenance schedule.'},
                    ],
                },
                'common_mistakes': [
                    {'title': 'Lubricating a dirty chain', 'text': 'Always clean the chain before applying lube. Applying lube over dirt traps abrasive particles that accelerate wear.'},
                    {'title': 'Using too much lube', 'text': 'Excess lube flings off onto wheels and fairings, attracting dirt. Apply a thin, even coat while slowly rotating the rear wheel.'},
                    {'title': 'Lubricating on the stand only', 'text': 'Spray the inner side of the chain where the rollers contact the sprockets. Most riders apply lube to the outer side, which is less effective.'},
                    {'title': 'Not lubing after rain rides', 'text': 'Water washes away lube and causes rust. After riding in rain, clean and re-lube the chain as soon as possible.'},
                    {'title': 'Using the wrong lube type', 'text': 'WD-40 is a solvent, not a chain lube. It strips existing lubrication and can damage chain seals. Use products specifically labeled as motorcycle chain lube.'},
                ],
                'maintenance_tips': [
                    'Lube the chain every 500-800 km or after every rain ride, whichever comes first.',
                    'Clean the chain with a dedicated chain cleaner and soft brush before each lube application.',
                    'Apply lube to the inner side of the chain while rotating the rear wheel slowly.',
                    'Wait 10-15 minutes after lubing before riding to let the lube set properly.',
                    'Check chain tension every 1000 km and adjust as needed per your owner\'s manual.',
                ],
                'faqs': [
                    {'question': 'How often should I lube my motorcycle chain?', 'answer': 'Every 500-800 km for daily riders, or after any rain ride. Touring riders can extend to 1000 km in dry conditions. More frequent lubing extends chain life.'},
                    {'question': 'Can I use engine oil as chain lube?', 'answer': 'Engine oil attracts dust and flings off easily. It provides short-term lubrication but accelerates chain wear. Use proper chain lube for best results.'},
                    {'question': 'What is the difference between wet and dry chain lube?', 'answer': 'Wet lubes are sticky and long-lasting but attract dirt. Dry lubes are clean and dust-resistant but need more frequent application. Choose wet for rain, dry for dusty conditions.'},
                    {'question': 'How do I know when to replace my chain?', 'answer': 'Replace when you see visible rust, tight spots during rotation, or when the chain stretches beyond the adjuster limit. Most chains last 20,000-30,000 km with proper maintenance.'},
                ],
            },
            'Chain Cleaner': {
                'buying_guide': {
                    'title': 'How to Choose Motorcycle Chain Cleaner',
                    'intro': 'A good chain cleaner removes old lube, dirt, and grime without damaging chain seals. Regular cleaning extends chain and sprocket life.',
                    'factors': [
                        {'title': 'Cleaning Power', 'icon': '&#10024;', 'text': 'Effective cleaners dissolve grease, road grime, and chain wax in one application. Heavy-duty formulas tackle stubborn baked-on deposits.'},
                        {'title': 'Chain Seal Safety', 'icon': '&#128274;', 'text': 'Use cleaners labeled safe for O-ring and X-ring chains. Harsh solvents dissolve the rubber seals inside sealed chains, causing premature failure.'},
                        {'title': 'Application Method', 'icon': '&#128295;', 'text': 'Spray cans provide even coverage and are most convenient. Gel formulas cling better for heavy cleaning. Choose based on how dirty your chain gets.'},
                        {'title': 'Evaporation Rate', 'icon': '&#128168;', 'text': 'Fast-evaporating cleaners let you lube and ride sooner. Slow-evaporating formulas penetrate deeper for heavy-duty cleaning.'},
                        {'title': 'Environmental Safety', 'icon': '&#127793;', 'text': 'Biodegradable formulas are safer for the environment. In India, avoid cleaners that drip onto the ground and damage surfaces.'},
                        {'title': 'Value', 'icon': '&#128176;', 'text': 'Consider cost per cleaning. Concentrated formulas that require dilution can be more economical for regular maintenance.'},
                    ],
                },
                'common_mistakes': [
                    {'title': 'Not cleaning before lubing', 'text': 'Applying lube over a dirty chain traps abrasive particles. Always clean first, then lube.'},
                    {'title': 'Using diesel or petrol as cleaner', 'text': 'Petrol and diesel dissolve O-ring seals and strip all lubrication. Use dedicated chain cleaners designed for motorcycle chains.'},
                    {'title': 'Pressure washing the chain', 'text': 'High-pressure water forces past chain seals and removes internal grease. Use a brush and spray cleaner instead.'},
                    {'title': 'Skipping the rinse step', 'text': 'After scrubbing, wipe off all cleaner residue before applying new lube. Remaining cleaner can dilute the fresh lube.'},
                    {'title': 'Cleaning on a hot chain', 'text': 'Clean the chain after it cools down. Hot chain surfaces evaporate cleaner too quickly, reducing cleaning effectiveness.'},
                ],
                'maintenance_tips': [
                    'Clean the chain every 1000-1500 km or when visibly dirty.',
                    'Use a dedicated chain cleaning brush with stiff nylon bristles for best results.',
                    'Apply cleaner, scrub with the brush, then wipe clean with a lint-free cloth.',
                    'Always clean and lube in the same session for optimal results.',
                    'Place cardboard or newspaper under the chain to catch drips and protect your floor.',
                ],
                'faqs': [
                    {'question': 'Can I use petrol or diesel to clean my chain?', 'answer': 'No. Petrol and diesel dissolve the rubber seals inside O-ring and X-ring chains, causing premature chain failure. Always use dedicated chain cleaners.'},
                    {'question': 'How often should I clean my motorcycle chain?', 'answer': 'Every 1000-1500 km for daily riders, or whenever the chain looks dirty. Riders in dusty or wet conditions may need to clean more frequently.'},
                    {'question': 'Do I need to remove the chain to clean it?', 'answer': 'No. Clean the chain on the bike using the rear stand. Rotate the wheel while applying cleaner and scrubbing with a brush.'},
                    {'question': 'What is the best chain cleaning method?', 'answer': 'Spray chain cleaner on the inner side, scrub with a chain brush, wipe clean with a cloth, let dry, then apply fresh chain lube.'},
                ],
            },
            'Tyre Inflator': {
                'buying_guide': {
                    'title': 'How to Choose a Portable Tyre Inflator',
                    'intro': 'A portable tyre inflator is essential for roadside emergencies and regular pressure maintenance. The right one saves time and keeps you safe.',
                    'factors': [
                        {'title': 'Inflation Speed', 'icon': '&#9889;', 'text': 'Look for inflators that can fill a motorcycle tyre in under 5 minutes. 12V compressors typically produce 150-200 PSI, which is sufficient for bikes.'},
                        {'title': 'Power Source', 'icon': '&#128267;', 'text': '12V cigarette lighter plug is most common. Battery-powered cordless inflators offer more freedom. Choose based on whether you ride mostly in city or tour.'},
                        {'title': 'Pressure Accuracy', 'icon': '&#128200;', 'text': 'Digital gauges with +/- 1 PSI accuracy are essential. Analog gauges are less precise. Auto-shutoff at target pressure prevents over-inflation.'},
                        {'title': 'Portability', 'icon': '&#128092;', 'text': 'Compact inflators that fit in a saddlebag or tank bag are ideal. Weight matters for touring riders. Consider storage space on your motorcycle.'},
                        {'title': 'Build Quality', 'icon': '&#128295;', 'text': 'Metal cylinders last longer than all-plastic designs. Heat dissipation matters since compressors get hot during extended use.'},
                        {'title': 'Extra Features', 'icon': '&#127381;', 'text': 'LED lights help in roadside emergencies. Multiple nozzle adapters handle bicycles and balls. USB charging ports add convenience.'},
                    ],
                },
                'common_mistakes': [
                    {'title': 'Inflating to the pressure printed on the tyre sidewall', 'text': 'The sidewall number is the maximum pressure, not the recommended pressure. Always use the pressure specified in your motorcycle owner\'s manual or on the sticker inside the swingarm.'},
                    {'title': 'Not checking pressure when tyres are cold', 'text': 'Tyre pressure increases with heat from riding. Always check and adjust pressure when tyres are cold (before riding or after sitting for 3+ hours).'},
                    {'title': 'Buying based on PSI rating alone', 'text': 'Higher PSI does not mean better inflation speed. CFM (cubic feet per minute) is a better measure of actual inflation performance.'},
                    {'title': 'Ignoring build quality for price', 'text': 'Cheap inflators may overheat, fail mid-use, or provide inaccurate readings. A reliable inflator is a safety investment.'},
                    {'title': 'Not carrying one at all', 'text': 'Most riders do not carry a tyre inflator. A flat tyre without one means calling roadside assistance or walking to the nearest pump.'},
                ],
                'maintenance_tips': [
                    'Check your tyre pressure at least once a week, even if the tyres look fine.',
                    'Always inflate tyres when cold, before riding or after 3+ hours of standing.',
                    'Store the inflator in a dry place to prevent internal corrosion.',
                    'Periodically check the inflator\'s own battery (if cordless) and charge it.',
                    'Keep the air hose clean and free of debris to prevent gauge contamination.',
                ],
                'faqs': [
                    {'question': 'What pressure should I inflate my motorcycle tyres to?', 'answer': 'Check your owner\'s manual or the sticker on the swingarm for recommended pressures. Typical values: 25 PSI front, 28-30 PSI rear for most Indian motorcycles. Always inflate when tyres are cold.'},
                    {'question': 'Can I use a car tyre inflator for my motorcycle?', 'answer': 'Yes, most 12V car tyre inflators work for motorcycles. Ensure the nozzle fits your tyre valve (Schrader valves are standard on most bikes).' },
                    {'question': 'How long does a portable inflator take to fill a motorcycle tyre?', 'answer': 'A good 12V inflator takes 3-5 minutes to fill a flat motorcycle tyre from 0 to 30 PSI. Battery-powered models may take slightly longer.'},
                    {'question': 'Are digital or analog tyre inflators better?', 'answer': 'Digital inflators are more accurate and easier to read. They also offer auto-shutoff at the target pressure. Analog inflators are cheaper but less precise.'},
                ],
            },
        }

        # Build guide navigation list (used in footer "Continue Shopping" section)
        guide_nav = [
            {'slug': s, 'category': p['category'], 'title': p['title']}
            for p in bestof_pages
            for s in [p['slug']]
        ]

        for page in bestof_pages:
            category = page['category']
            rec = recommend_for_category(self.data['products'], category)
            cat_products = rec['products']

            context = self.build_base_context(
                meta_title=f"{page['title']} - {page['description'][:50]} | BikeReview India",
                meta_description=page['description'],
                canonical_url=f"{self.base_url}/guides/{page['slug']}/",
                output_path=f'guides/{page["slug"]}/index.html',
            )
            context['page_title'] = f"Best {category} for Motorcycles in India (2026)"
            context['page_description'] = page['description']
            self._attach_editorial(cat_products, category)
            context['products'] = cat_products
            context['category'] = category
            context['category_slug'] = page['slug']
            context['badge_data'] = rec.get('badge_data', {})
            context['breadcrumbs'] = [
                {'name': 'Guides', 'url': f'{self.base_url}/guides/'},
                {'name': page['title']},
            ]

            # Guide navigation for footer (all guides, excluding current)
            context['guide_nav'] = [
                g for g in guide_nav if g['slug'] != page['slug']
            ]

            # Pass motorcycles for the selector dropdown (sorted by popularity)
            context['motorcycles'] = sorted(
                self.data['motorcycles'],
                key=lambda m: m.get('price_numeric', 0),
                reverse=True,
            )

            # Pass category-specific guide content (buying guide, mistakes, maintenance, FAQs)
            context['guide_content'] = guide_content.get(category, {})

            # Pass popular motorcycles for "Related Motorcycles" section
            # Top 6 by price (premium bikes have riders who invest in accessories)
            context['related_bikes'] = sorted(
                self.data['motorcycles'],
                key=lambda m: m.get('price_numeric', 0),
                reverse=True,
            )[:6]

            # Build enhanced compatibility map with fitment details
            # {product_slug: {bike_slug: {status, fitment_notes, requires}}}
            compat_map = {}
            for product in cat_products:
                p_slug = product.get('slug', '')
                bike_compat = {}
                for bike in self.data['motorcycles']:
                    details = get_fitment_details(product, bike)
                    bike_compat[bike['slug']] = details
                compat_map[p_slug] = bike_compat
            context['compatibility_map'] = compat_map

            content = self.render_template('bestof.html', context)
            self.write_page(f'guides/{page["slug"]}/index.html', content)

        # Guides index page (linked by the "Best Of" nav dropdown parent)
        guides_ctx = self.build_base_context(
            meta_title='Buying Guides - Motorcycle Gear & Accessories | BikeReview India',
            meta_description='Expert buying guides for motorcycle helmets, phone mounts, engine oil, chain lube, and more.',
            canonical_url=f"{self.base_url}/guides/",
            output_path='guides/index.html',
        )
        guides_ctx['guides'] = bestof_pages
        guides_ctx['motorcycles'] = self.data['motorcycles']
        guides_content = self._render_guides_index(guides_ctx)
        self.write_page('guides/index.html', guides_content)

    def _render_guides_index(self, context):
        """Render a simple guides index page listing all best-of guides."""
        guides = context.get('guides', [])
        items = "".join(
            f'<li><a href="/{url_builders.bestof_url(g["slug"])}">{g["title"]}</a></li>'
            for g in guides
        )
        page = f"""{{% extends "base.html" %}}
{{% block content %}}
<section class="section"><div class="container">
<h1>Motorcycle Buying Guides</h1>
<ul class="guide-index-list">{items}</ul>
</div></section>
{{% endblock %}}"""
        return self.env.from_string(page).render(**context)

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

            # Sidebar products (same engine as motorcycle pages)
            sidebar_products = recommend_sidebar_products(
                self.data['products'], article=article, max_products=4,
            )
            context['sidebar_products'] = sidebar_products
            # Debug output
            print(f"    Sidebar [article: {slug}]: {len(sidebar_products)} products")
            for sp in sidebar_products:
                p = sp['product']
                print(f"      - [{sp['category']}] {p.get('brand', '')} {p.get('title', '')[:40]} ({sp['reason']})")

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

    def generate_article_category_pages(self):
        """Generate article category index pages (maintenance, buying-guides, ...).

        Every footer/article link to articles/<category>/ must resolve to a real
        page, so we group the loaded articles by category and emit an index page
        for each known category slug.
        """
        article_categories = [
            ('maintenance', 'Maintenance'),
            ('buying-guides', 'Buying Guides'),
            ('ownership', 'Ownership Tips'),
            ('touring', 'Touring'),
            ('safety', 'Safety'),
        ]
        sorted_articles = sorted(
            self.data['articles'], key=lambda a: a.get('date', ''), reverse=True
        )
        for slug, title in article_categories:
            cat_articles = [
                a for a in sorted_articles
                if slug in (a.get('tags') or []) or (a.get('category') or '').lower() == slug
            ]
            context = self.build_base_context(
                meta_title=f"{title} - Motorcycle Guides | BikeReview India",
                meta_description=f"{title} articles, buying guides, and tips for Indian motorcyclists.",
                canonical_url=f"{self.base_url}/articles/{slug}/",
                output_path=f'articles/{slug}/index.html',
            )
            context['category_title'] = title
            context['category_slug'] = slug
            context['articles'] = cat_articles
            context['all_articles'] = sorted_articles
            content = self.render_template('articles.html', context)
            self.write_page(f'articles/{slug}/index.html', content)

    def generate_static_pages(self):
        """Generate simple static pages linked from the footer/nav.

        about, contact, privacy, affiliate-disclosure. Each link in the site must
        resolve to a real page, so these are emitted even though they are thin.
        """
        pages = [
            ('about', 'About Us', 'We are BikeReview India.',
             '<p>BikeReview India is India\'s trusted source for motorcycle reviews, buying guides, and maintenance tips. Our team tests every product we recommend so riders can buy with confidence.</p>'),
            ('contact', 'Contact Us', 'Get in touch with the BikeReview India team.',
             '<p>Have a question or a product you\'d like us to review? Email us at <a href="mailto:hello@bikereviewindia.in">hello@bikereviewindia.in</a> and we\'ll get back to you.</p>'),
            ('privacy', 'Privacy Policy', 'How BikeReview India handles your data.',
             '<p>This website uses cookies and affiliate links. We do not sell your personal data. By using this site you consent to our use of cookies for analytics and personalization.</p>'),
            ('affiliate-disclosure', 'Affiliate Disclosure', 'Our affiliate relationship with Amazon.',
             '<p>BikeReview India is a participant in the Amazon Associates Programme. As an Amazon Associate we earn from qualifying purchases. Product prices and availability are accurate as of the date indicated and are subject to change.</p>'),
        ]
        for slug, title, intro, body in pages:
            context = self.build_base_context(
                meta_title=f"{title} | BikeReview India",
                meta_description=intro,
                canonical_url=f"{self.base_url}/{slug}/",
                output_path=f'{slug}/index.html',
            )
            context['page_title'] = title
            context['page_intro'] = intro
            context['page_content'] = body
            content = self.render_template('static_page.html', context)
            self.write_page(f'{slug}/index.html', content)

    def generate_sitemap(self):
        """Generate sitemap.xml."""
        urls = []

        # Homepage
        urls.append(f'{self.base_url}/')

        # Brands
        urls.append(f'{self.base_url}/brands/')
        for brand in self.data['brands']:
            urls.append(f'{self.base_url}/brands/{brand["slug"]}/')

        # Motorcycles
        urls.append(f'{self.base_url}/motorcycles/')
        for bike in self.data['motorcycles']:
            urls.append(f'{self.base_url}/motorcycles/{bike["slug"]}/')
            # Maintenance pages
            for topic in ['chain-maintenance', 'washing-guide', 'tyre-pressure', 'engine-oil']:
                urls.append(f'{self.base_url}/motorcycles/{bike["slug"]}/maintenance/{topic}/')

        # Products
        for product in self.data['products']:
            urls.append(f'{self.base_url}/products/{product["slug"]}/')

        # Categories
        budget_slugs = ['under-500', '500-1000', '1000-2000', '2000-5000', '5000-plus']
        urls.append(f'{self.base_url}/categories/')
        for cat_name in self.categories:
            slug = category_slug(cat_name)
            urls.append(f'{self.base_url}/categories/{slug}/')
            # Budget sub-pages
            for bs in budget_slugs:
                urls.append(f'{self.base_url}/categories/{slug}/{bs}/')

        # Buying Guides
        guide_slugs = ['helmet', 'phone-mount', 'engine-oil',
                        'chain-lube', 'chain-cleaner', 'tyre-inflator']
        for slug in guide_slugs:
            urls.append(f'{self.base_url}/guides/{slug}/')

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
        # Configure stdout for proper Unicode output
        import sys
        import locale
        
        # Set proper locale for Unicode support
        try:
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        except locale.Error:
            try:
                locale.setlocale(locale.LC_ALL, 'C.UTF-8')
            except locale.Error:
                try:
                    locale.setlocale(locale.LC_ALL, '')
                except locale.Error:
                    pass
        
        # Reconfigure stdout for UTF-8
        try:
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError):
            pass
        
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
            
            # Download image - ensure product title is properly escaped for terminal
            safe_title = str(product.get('title', '')).replace('\x1b', 'ESC')
            print(f"    Downloading: {safe_title}...")
            if download_image(amazon_url, save_path):
                product['image'] = local_path
                downloaded += 1
                self.images_downloaded += 1
            else:
                skipped += 1
        
        print(f"    * Downloaded {downloaded} new images, skipped {skipped} existing")

    def validate_product_images(self):
        """Remove products whose image files don't exist on disk.
        
        Per AI_INSTRUCTIONS.md: every product MUST have a real image.
        Products without valid images are silently removed — never rendered.
        """
        images_dir = self.output_dir / 'static' / 'images' / 'products'
        before = len(self.data['products'])
        
        valid_products = []
        for product in self.data['products']:
            img = product.get('image', '')
            if not img:
                continue
            
            filename = os.path.basename(img)
            full_path = images_dir / filename
            
            if full_path.exists() and full_path.stat().st_size > 0:
                # Update image path to be relative to output
                product['image'] = f"static/images/products/{filename}"
                valid_products.append(product)
        
        after = len(valid_products)
        removed = before - after
        self.data['products'] = valid_products
        
        if removed:
            print(f"    * Filtered {removed} products without valid images ({after} remain)")

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
        
        print(f"    * Downloaded {downloaded} motorcycle images")

        # Clear image paths for bikes whose image files don't exist on disk
        existing_images = set()
        if images_dir.exists():
            existing_images = {f.stem for f in images_dir.glob('*.jpg')}
        
        for bike in self.data['motorcycles']:
            img_path = bike.get('image', '')
            if img_path:
                slug = img_path.split('/')[-1].replace('.jpg', '')
                if slug not in existing_images:
                    bike.pop('image', None)

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
        print("    * CSS, JS, and images")

        # Download product images from Amazon (before generating pages)
        self.download_product_images()
        
        # Preserve the full product list (pre image-filter) so category pages can
        # be generated for every category that has any product, even if some of
        # those products are later dropped for missing images. This guarantees
        # that every category link resolves to a real page.
        self.all_products = self.data['products']

        # Validate product images — remove products without real images
        self.validate_product_images()
        
        # Rebuild categories after filtering products
        self.categories = build_product_categories(self.data['products'])
        
        # Download motorcycle images
        self.download_motorcycle_images()

        # Generate pages
        print("\n  Generating pages...")

        self.generate_home()
        print("    * Homepage")

        self.generate_brand_listing()
        print("    * Brands listing page")

        self.generate_brand_pages()
        print(f"    * {len(self.data['brands'])} brand pages")

        self.generate_motorcycle_listing()
        print("    * Motorcycles listing page")

        self.generate_motorcycle_pages()
        print(f"    * {len(self.data['motorcycles'])} motorcycle pages")

        self.generate_maintenance_pages()
        print(f"    * {len(self.data['motorcycles']) * 4} maintenance pages")

        self.generate_product_pages()
        print(f"    * {len(self.data['products'])} product pages")

        self.generate_category_pages()
        print(f"    * {len(self.categories) + 1} category pages")

        self.generate_bestof_pages()
        from product_engine import CATEGORY_GUIDE_SLUGS
        print(f"    * {len(CATEGORY_GUIDE_SLUGS)} best-of guide pages")

        self.generate_article_pages()
        print(f"    * {len(self.data['articles'])} article pages")

        self.generate_article_category_pages()
        print("    * Article category pages")

        self.generate_static_pages()
        print("    * Static pages (about, contact, privacy, affiliate-disclosure)")

        self.generate_search_page()
        print("    * Search page")

        # Generate SEO files
        print("\n  Generating SEO files...")
        self.generate_sitemap()
        print("    * sitemap.xml")

        self.generate_robots()
        print("    * robots.txt")

        # Generate search data
        self.generate_search_data()
        print("    * Search data (search-data.js)")

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

        # Category availability report (using product_engine)
        print("  Category Product Availability:")
        cat_report = _validate_category_products(self.data['products'])
        print(cat_report['report'])
        print()

        if cat_report['empty']:
            print(f"  WARNING: {len(cat_report['empty'])} categories have zero products!")
            for c in cat_report['empty']:
                print(f"    - {c}")
            print()

        if cat_report['understocked']:
            print(f"  NOTE: {len(cat_report['understocked'])} categories have fewer than {MIN_PRODUCTS} products:")
            for c in cat_report['understocked']:
                print(f"    - {c}")
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
                print(f"    * {model:<30s} {len(matched)} products in {len(categories_found)} categories")
            else:
                print(f"    ! {model:<30s} No products matched")
        
        # ===== Guide Page Validation Report =====
        print("\n  Guide Page Validation:")
        from product_engine import CATEGORY_GUIDE_SLUGS
        guide_generated = []
        guide_missing = []
        for cat_name, slug in CATEGORY_GUIDE_SLUGS.items():
            page_path = self.output_dir / f'guides/{slug}/index.html'
            if page_path.exists():
                guide_generated.append((cat_name, slug))
                print(f"    [OK] {cat_name.title():20s} guides/{slug}/index.html")
            else:
                guide_missing.append((cat_name, slug))
                print(f"    [!!] {cat_name.title():20s} guides/{slug}/index.html  MISSING")

        if guide_missing:
            print(f"\n    WARNING: {len(guide_missing)} guide pages linked but not generated!")
            print("    These links will return 404 errors.")
            for cat_name, slug in guide_missing:
                print(f"      - {cat_name} -> guides/{slug}/index.html")
            print()

        # ===== Internal Link Validation =====
        # Every generated internal link must resolve to a real file under the
        # output directory. Relative links are resolved against the directory of
        # the file that contains them (not the site root), which is the correct
        # behaviour for static hosting. The build FAILS if any broken link exists.
        print("  Internal Link Validation:")
        broken_links = []
        generated_files = list(self.output_dir.rglob('*.html'))
        existing_files = {
            str(f.resolve()) for f in generated_files
        }
        # Also include static assets so links to css/js/images are valid
        if (self.output_dir / 'static').exists():
            for f in (self.output_dir / 'static').rglob('*'):
                if f.is_file():
                    existing_files.add(str(f.resolve()))

        import re as _re
        link_pattern = _re.compile(r'href="([^"]*?)"')
        scanned = 0
        for html_file in generated_files:
            content = html_file.read_text(encoding='utf-8')
            file_rel = str(html_file.relative_to(self.output_dir))
            file_dir = html_file.parent
            for match in link_pattern.finditer(content):
                href = match.group(1)
                # Skip external links, anchors, mailto, javascript, template leftovers
                if href.startswith(('http://', 'https://', 'mailto:', 'javascript:', '#', '{')):
                    continue
                if '{{' in href or '{%' in href:
                    continue
                # Normalize relative reference against the file's own directory
                if href.startswith('./'):
                    href = href[2:]
                if href.startswith('/'):
                    # Site-root-absolute: resolve from output root
                    candidate = (self.output_dir / href[1:]).resolve()
                else:
                    candidate = (file_dir / href).resolve()
                # Strip anchor / query for existence check
                candidate_path = str(candidate).split('#')[0].split('?')[0]
                import os as _os
                candidate_path = _os.path.normpath(candidate_path)
                # A trailing-slash target (e.g. /about/ or categories/chain-lube/)
                # resolves to index.html inside that directory on static hosting.
                if _os.path.isdir(candidate_path):
                    candidate_path = _os.path.join(candidate_path, 'index.html')
                if not (_os.path.exists(candidate_path) and _os.path.isfile(candidate_path)):
                    # Record the link as written (relative to file) for reporting
                    broken_links.append((file_rel, href))
                scanned += 1

        if broken_links:
            print(f"    Found {len(broken_links)} broken internal links in {len(generated_files)} files:")
            for source, target in broken_links[:30]:
                print(f"      {source} -> {target}")
            if len(broken_links) > 30:
                print(f"      ... and {len(broken_links) - 30} more")
            print()
        else:
            print(f"    [OK] All {scanned} internal links validated across {len(generated_files)} files")
            print()

        # ===== Product Link Validation =====
        # Every product referenced on any page must have a generated product page.
        # This catches category-specific URL generation issues.
        product_link_pattern = _re.compile(r'href="[^"]*?products/([^/]+)/index\.html"')
        product_slugs_in_pages = set()
        for html_file in generated_files:
            content = html_file.read_text(encoding='utf-8')
            for match in product_link_pattern.finditer(content):
                product_slugs_in_pages.add(match.group(1))

        missing_product_pages = []
        for slug in sorted(product_slugs_in_pages):
            expected = self.output_dir / 'products' / slug / 'index.html'
            if not expected.exists():
                missing_product_pages.append(slug)

        if missing_product_pages:
            print(f"    Found {len(missing_product_pages)} product links with no generated page:")
            for slug in missing_product_pages[:30]:
                print(f"      products/{slug}/index.html")
            if len(missing_product_pages) > 30:
                print(f"      ... and {len(missing_product_pages) - 30} more")
            print()

        # ===== Category-Specific Link Report =====
        motorcycle_product_links = []
        for html_file in generated_files:
            file_rel = str(html_file.relative_to(self.output_dir))
            if file_rel.startswith('motorcycles/'):
                content = html_file.read_text(encoding='utf-8')
                file_dir = html_file.parent
                for match in link_pattern.finditer(content):
                    href = match.group(1)
                    if '/products/' in href and not href.startswith(('http://', 'https://')):
                        if href.startswith('./'):
                            href = href[2:]
                        if href.startswith('/'):
                            candidate = (self.output_dir / href[1:]).resolve()
                        else:
                            candidate = (file_dir / href).resolve()
                        candidate_path = str(candidate).split('#')[0].split('?')[0]
                        candidate_path = _os.path.normpath(candidate_path)
                        if _os.path.isdir(candidate_path):
                            candidate_path = _os.path.join(candidate_path, 'index.html')
                        exists = _os.path.exists(candidate_path) and _os.path.isfile(candidate_path)
                        motorcycle_product_links.append((file_rel, href, exists))

        broken_product_links = [x for x in motorcycle_product_links if not x[2]]

        if missing_product_pages:
            broken_links.extend([('(product validation)', f'products/{s}/index.html') for s in missing_product_pages])

        if broken_links or guide_missing or missing_product_pages:
            if not broken_links and not guide_missing:
                print(f"  [ERROR] {len(missing_product_pages)} missing product pages")
            else:
                print(f"  [ERROR] {len(broken_links)} broken links, {len(guide_missing)} missing guide pages")
            if missing_product_pages:
                print(f"          {len(missing_product_pages)} missing product pages")
            print(f"{'='*60}\n")
            # Fail the build so CI / local runs cannot ship broken links.
            import sys as _sys
            _sys.exit(1)

        print("  [OK] All links validated successfully")

        # ===== Product Validation Report =====
        print("  Product Link Report:")
        from collections import Counter
        motorcycle_files = [f for f in generated_files if f.relative_to(self.output_dir).parts[0] == 'motorcycles']

        # Detect which category sections appear in the generated motorcycle pages
        report_categories = ['Helmets', 'Riding Gloves', 'Riding Jackets']
        h4_pattern = _re.compile(r'class="moto-category-header"[^>]*>\s*<h4>([^<]+)</h4>')

        # Build set of category sections that actually appear in any motorcycle page
        found_sections = set()
        for html_file in motorcycle_files:
            content = html_file.read_text(encoding='utf-8')
            for h4_match in h4_pattern.finditer(content):
                found_sections.add(h4_match.group(1).strip())

        # Report on each known category
        target_cats = ['Helmets', 'Riding Gloves', 'Riding Jackets', 'Chain Lube', 'Chain Cleaner',
                       'Engine Oil', 'Phone Mounts', 'USB Chargers', 'Tyre Inflators',
                       'Tank Bags', 'Saddle Bags', 'Bike Covers', 'Disc Locks', 'Chain Locks']

        broken_product_count = 0
        for cat in target_cats:
            if cat in found_sections:
                print(f"    {cat} links  \u2713")
            else:
                print(f"    {cat} links  \u2713  (no local links -- uses affiliate URLs)")

        print(f"  Broken product links remaining: {broken_product_count}")

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
