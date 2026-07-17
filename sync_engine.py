"""
Daily Amazon Sync Engine
========================
Synchronizes Amazon data into the product library without modifying editorial data.

This module is the ONLY place that should update Amazon-specific fields
(price, rating, reviews, availability, image, affiliate URL). It uses the
deterministic product_matcher for matching and product_library for loading/saving.

Sync Flow:
    1. Load product library (nested JSON)
    2. Load Amazon feed data (PA-API output or cached deals)
    3. For each approved product:
       a. Match product to Amazon record (using product_matcher)
       b. Update ONLY amazon.* fields
       c. NEVER touch editorial.* fields, status, compatibility, or identity
    4. Save updated product library
    5. Generate sync report

What Gets Updated:
    - price, mrp, discount
    - rating, review_count
    - availability
    - image (if changed)
    - affiliate_url (if updated)
    - last_updated = timestamp

What NEVER Gets Updated:
    - editorial.score, pros, cons, features, fitment_notes, notes
    - status
    - compatible_bikes
    - category, brand, type
    - slug, title, asin
    - best_for, verdict
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from product_library import (
    load_products,
    unflatten_product,
    approved_products,
    find_product_by_asin,
    RECOMMENDABLE_STATUSES,
)


# ===== Amazon Feed Loading =====

def load_amazon_feed(feed_path: Path) -> List[dict]:
    """Load Amazon feed data from a JSON file.

    Supports two formats:
    1. Array of deal objects (bike-deals.json format)
    2. Dict keyed by ASIN

    Returns a list of deal records.
    """
    if not feed_path.exists():
        return []

    with open(feed_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    if isinstance(raw, list):
        return raw
    elif isinstance(raw, dict):
        return list(raw.values())
    return []


def load_amazon_feed_by_asin(feed_path: Path) -> Dict[str, dict]:
    """Load Amazon feed data indexed by ASIN for fast lookup.

    Returns dict keyed by uppercase ASIN.
    """
    deals = load_amazon_feed(feed_path)
    by_asin = {}
    for deal in deals:
        asin = (deal.get('asin') or '').strip().upper()
        if asin:
            by_asin[asin] = deal
    return by_asin


# ===== Feed Record Extraction =====

def extract_feed_price(deal: dict) -> Optional[int]:
    """Extract price from an Amazon deal record."""
    # Try offersV2 first (PA-API v3 format)
    offers = deal.get('offersV2', {})
    listings = offers.get('listings', [])
    for listing in listings:
        if listing.get('isBuyBoxWinner'):
            price_money = listing.get('price', {}).get('money', {})
            amount = price_money.get('amount')
            if amount:
                return int(float(amount))

    # Try direct price field
    price = deal.get('price')
    if price:
        return int(float(price))

    return None


def extract_feed_mrp(deal: dict) -> Optional[int]:
    """Extract MRP from an Amazon deal record."""
    offers = deal.get('offersV2', {})
    listings = offers.get('listings', [])
    for listing in listings:
        if listing.get('isBuyBoxWinner'):
            saving = listing.get('savingBasis', {})
            if saving:
                amount = saving.get('money', {}).get('amount')
                if amount:
                    return int(float(amount))
    return None


def extract_feed_discount(deal: dict, price: int, mrp: int) -> Optional[int]:
    """Calculate discount percentage from price and MRP."""
    if mrp and price and mrp > price:
        return round(((mrp - price) / mrp) * 100)
    return None


def extract_feed_rating(deal: dict) -> Optional[float]:
    """Extract rating from an Amazon deal record."""
    rating = deal.get('rating')
    if rating:
        try:
            return float(rating)
        except (TypeError, ValueError):
            pass
    return None


def extract_feed_review_count(deal: dict) -> Optional[int]:
    """Extract review count from an Amazon deal record."""
    reviews = deal.get('reviews') or deal.get('review_count')
    if reviews:
        try:
            return int(reviews)
        except (TypeError, ValueError):
            pass
    return None


def extract_feed_image(deal: dict) -> Optional[str]:
    """Extract large image URL from an Amazon deal record."""
    images = deal.get('images', {})
    primary = images.get('primary', {})
    large = primary.get('large', {})
    url = large.get('url', '')
    if url:
        return url
    return None


def extract_feed_availability(deal: dict) -> Optional[str]:
    """Extract availability from an Amazon deal record."""
    availability = deal.get('availability')
    if availability:
        return availability
    offers = deal.get('offersV2', {})
    listings = offers.get('listings', [])
    for listing in listings:
        avail = listing.get('availability', {})
        message = avail.get('message', '')
        if message:
            return message
    return None


def extract_feed_affiliate_url(deal: dict) -> Optional[str]:
    """Extract affiliate URL from an Amazon deal record."""
    url = deal.get('detailPageURL') or deal.get('url') or ''
    if url:
        return url
    return None


# ===== Sync Core =====

# Fields that may ONLY be updated by the sync engine.
SYNCABLE_FIELDS = {
    'price', 'mrp', 'discount', 'rating', 'review_count',
    'availability', 'image', 'affiliate_url', 'last_updated',
}

# Fields that must NEVER be modified during sync.
IMMUTABLE_FIELDS = {
    'editorial', 'status', 'compatible_bikes', 'category', 'brand',
    'type', 'slug', 'title', 'asin', 'best_for', 'verdict',
    'pros', 'cons', 'features', 'fitment_notes', 'recommended_for',
    'editorial_notes', 'editor_rating',
}


class SyncResult:
    """Result of a sync operation."""

    def __init__(self):
        self.total_products = 0
        self.approved_products = 0
        self.synced = 0
        self.matched = 0
        self.unmatched = 0
        self.fields_updated = 0
        self.errors = []
        self.warnings = []
        self.changes = []  # {slug, field, old, new}
        self.unmatched_asins = []
        self.start_time = None
        self.end_time = None

    def summary(self) -> str:
        """Return a human-readable sync summary."""
        duration = ''
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            duration = f" in {delta.total_seconds():.1f}s"

        lines = [
            f"Sync completed{duration}",
            f"  Total products: {self.total_products}",
            f"  Approved: {self.approved_products}",
            f"  Matched to Amazon feed: {self.matched}",
            f"  Unmatched (no feed data): {self.unmatched}",
            f"  Products updated: {self.synced}",
            f"  Fields updated: {self.fields_updated}",
        ]
        if self.errors:
            lines.append(f"  Errors: {len(self.errors)}")
            for e in self.errors[:5]:
                lines.append(f"    - {e}")
        if self.warnings:
            lines.append(f"  Warnings: {len(self.warnings)}")
            for w in self.warnings[:5]:
                lines.append(f"    - {w}")
        return '\n'.join(lines)


def _validate_sync_safety(product: dict, updates: dict) -> dict:
    """Verify that sync updates do not touch immutable fields.

    Returns {safe: bool, violations: [...], safe_updates: dict}.
    """
    violations = []
    safe_updates = {}

    for field, value in updates.items():
        if field in IMMUTABLE_FIELDS:
            violations.append(
                f"Sync attempted to modify immutable field '{field}' on "
                f"product '{product.get('slug', 'unknown')}'"
            )
        elif field in SYNCABLE_FIELDS:
            safe_updates[field] = value
        else:
            # Unknown field - skip with warning
            pass

    return {
        'safe': len(violations) == 0,
        'violations': violations,
        'safe_updates': safe_updates,
    }


def sync_product(
    product: dict,
    deal: dict,
    match_type: str,
    sync_time: str,
) -> Tuple[dict, list, list]:
    """Sync Amazon data into a single product.

    Updates ONLY amazon data fields. Never touches editorial data.

    Returns: (updated_product, changes_list, errors_list)
    """
    changes = []
    errors = []
    slug = product.get('slug', 'unknown')

    # --- Extract new Amazon data from the feed ---
    new_price = extract_feed_price(deal)
    new_mrp = extract_feed_mrp(deal)
    new_discount = extract_feed_discount(deal, new_price or 0, new_mrp or 0) if new_price and new_mrp else None
    new_rating = extract_feed_rating(deal)
    new_review_count = extract_feed_review_count(deal)
    new_image = extract_feed_image(deal)
    new_availability = extract_feed_availability(deal)
    new_affiliate_url = extract_feed_affiliate_url(deal)

    # --- Build update dict ---
    updates = {}
    if new_price is not None:
        updates['price'] = new_price
    if new_mrp is not None:
        updates['mrp'] = new_mrp
    if new_discount is not None:
        updates['discount'] = new_discount
    if new_rating is not None:
        updates['rating'] = new_rating
    if new_review_count is not None:
        updates['review_count'] = new_review_count
        updates['reviews'] = new_review_count  # legacy alias
    if new_image:
        updates['image'] = new_image
        updates['amazon_image_url'] = new_image
    if new_availability:
        updates['availability'] = new_availability
    if new_affiliate_url and match_type in ('asin', 'url_asin'):
        updates['affiliate_url'] = new_affiliate_url
    updates['last_updated'] = sync_time

    # --- Validate safety ---
    validation = _validate_sync_safety(product, updates)
    if not validation['safe']:
        errors.extend(validation['violations'])
        return product, changes, errors

    # --- Apply safe updates ---
    safe_updates = validation['safe_updates']
    for field, new_value in safe_updates.items():
        old_value = product.get(field)
        if old_value != new_value:
            product[field] = new_value
            changes.append({
                'slug': slug,
                'field': field,
                'old': old_value,
                'new': new_value,
            })

    return product, changes, errors


# ===== Main Sync Function =====

def sync_products(
    products_dir: Path,
    feed_path: Path,
    mode: str = 'full',
    dry_run: bool = False,
) -> SyncResult:
    """Sync Amazon data into the product library.

    Modes:
        'full': Process all approved products
        'selective': Only products where last_updated is older than 1 day
        'asins': Only specific ASINs (requires additional asins parameter)

    The feed_path should point to a JSON file containing Amazon deal data
    (e.g., bike-deals.json from bike.py output).

    Returns a SyncResult with detailed information about what was updated.
    """
    result = SyncResult()
    result.start_time = datetime.now()
    sync_time = result.start_time.isoformat()

    # --- Load product library ---
    products = load_products(products_dir)
    result.total_products = len(products)

    # Filter to approved products only
    syncable = [p for p in products if p.get('status') in RECOMMENDABLE_STATUSES]
    result.approved_products = len(syncable)

    # --- Load Amazon feed ---
    feed_by_asin = load_amazon_feed_by_asin(feed_path)
    if not feed_by_asin:
        result.warnings.append(f"No Amazon feed data found at {feed_path}")
        result.end_time = datetime.now()
        return result

    # --- Build product index by ASIN ---
    products_by_asin = {}
    for p in syncable:
        asin = (p.get('asin') or '').strip().upper()
        if asin:
            products_by_asin[asin] = p

    # --- Sync loop ---
    all_changes = []
    all_errors = []

    for product in syncable:
        asin = (product.get('asin') or '').strip().upper()
        slug = product.get('slug', 'unknown')

        # Find matching deal
        deal = None
        match_type = None

        if asin and asin in feed_by_asin:
            deal = feed_by_asin[asin]
            match_type = 'asin'
        else:
            # Try URL-based matching
            for url_field in ('affiliate_url',):
                url = product.get(url_field, '')
                if url:
                    # Extract ASIN from URL
                    import re
                    asin_match = re.search(r'(?:/dp/|/gp/product/|asin=)([A-Z0-9]{10})', url, re.IGNORECASE)
                    if asin_match:
                        url_asin = asin_match.group(1).upper()
                        if url_asin in feed_by_asin:
                            deal = feed_by_asin[url_asin]
                            match_type = 'url_asin'
                            break

        if not deal:
            result.unmatched += 1
            if asin:
                result.unmatched_asins.append(asin)
            continue

        result.matched += 1

        # Apply selective mode filter
        if mode == 'selective':
            last_updated = product.get('last_updated')
            if last_updated:
                try:
                    last_dt = datetime.fromisoformat(last_updated)
                    if (result.start_time - last_dt).days < 1:
                        continue  # Skip recently synced products
                except (ValueError, TypeError):
                    pass

        # Sync the product
        updated_product, changes, errors = sync_product(
            product, deal, match_type, sync_time
        )

        if changes:
            result.synced += 1
            result.fields_updated += len(changes)
            all_changes.extend(changes)

        if errors:
            all_errors.extend(errors)

    # --- Save updated products ---
    if not dry_run and result.synced > 0:
        _save_products(products_dir, products)

    # --- Record sync log ---
    if not dry_run:
        _save_sync_log(products_dir, result, all_changes)

    result.changes = all_changes
    result.errors = all_errors
    result.end_time = datetime.now()

    return result


def _save_products(products_dir: Path, products: list) -> None:
    """Save products back to their source JSON files.

    Groups products by their _source_file, converts to nested format,
    and writes each group back. Creates .bak backups before writing.
    """
    from collections import defaultdict

    groups = defaultdict(list)
    for p in products:
        source = p.get('_source_file', 'unknown.json')
        groups[source].append(p)

    for filename, group in groups.items():
        filepath = products_dir / filename
        if not filepath.exists():
            continue

        # Create backup
        backup_path = filepath.with_suffix('.json.bak')
        if not backup_path.exists():
            shutil.copy2(filepath, backup_path)

        # Convert to nested format
        nested = [unflatten_product(p) for p in group]

        # Write
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(nested, f, indent=2, ensure_ascii=False)


def _save_sync_log(products_dir: Path, result: SyncResult, changes: list) -> None:
    """Save sync log for audit trail."""
    log_path = products_dir / 'sync_log.json'

    # Load existing log
    existing = []
    if log_path.exists():
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except (json.JSONDecodeError, IOError):
            existing = []

    # Add new entry
    entry = {
        'timestamp': result.start_time.isoformat() if result.start_time else '',
        'total_products': result.total_products,
        'approved_products': result.approved_products,
        'matched': result.matched,
        'unmatched': result.unmatched,
        'synced': result.synced,
        'fields_updated': result.fields_updated,
        'errors': result.errors,
        'warnings': result.warnings,
        'changes': changes[:100],  # Cap at 100 changes per log entry
    }
    existing.append(entry)

    # Keep only last 30 days of logs
    if len(existing) > 30:
        existing = existing[-30:]

    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


# ===== Dry Run =====

def dry_run_sync(
    products_dir: Path,
    feed_path: Path,
    mode: str = 'full',
) -> SyncResult:
    """Run sync in dry-run mode (no files modified).

    Reports what WOULD be changed without actually changing anything.
    """
    return sync_products(products_dir, feed_path, mode=mode, dry_run=True)


# ===== Utility =====

def get_sync_status(products_dir: Path) -> dict:
    """Get the current sync status of the product library.

    Returns information about when products were last synced.
    """
    products = load_products(products_dir)
    approved = [p for p in products if p.get('status') == 'approved']

    synced = 0
    unsynced = 0
    oldest_sync = None
    newest_sync = None

    for p in approved:
        last_updated = p.get('last_updated')
        if last_updated:
            synced += 1
            try:
                dt = datetime.fromisoformat(last_updated)
                if oldest_sync is None or dt < oldest_sync:
                    oldest_sync = dt
                if newest_sync is None or dt > newest_sync:
                    newest_sync = dt
            except (ValueError, TypeError):
                pass
        else:
            unsynced += 1

    return {
        'total_products': len(products),
        'approved_products': len(approved),
        'synced_products': synced,
        'unsynced_products': unsynced,
        'oldest_sync': oldest_sync.isoformat() if oldest_sync else None,
        'newest_sync': newest_sync.isoformat() if newest_sync else None,
    }
