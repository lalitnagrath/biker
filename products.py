#!/usr/bin/env python3
"""
Product Library Management CLI
==============================
Management utilities for the curated product library.

Usage:
    python products.py import            Import from bike-deals.json into Product Library
    python products.py validate          Validate entire product library
    python products.py sync              Run daily Amazon sync
    python products.py stats             Print library statistics
    python products.py export            Export library to JSON
    python products.py find_duplicates   Find duplicate ASINs/titles
    python products.py list              List all products
    python products.py list --status approved   Filter by status
    python products.py list --category Helmet   Filter by category
    python products.py status <slug> [new_status]  Show/change product status
"""

import sys
import json
from pathlib import Path
from datetime import datetime

from product_library import (
    load_products,
    approved_products,
    active_products,
    validate_products,
    find_duplicates,
    generate_stats,
    import_legacy_products,
    export_products,
    find_product_by_slug,
    unflatten_product,
    count_by_status,
    count_by_category,
    VALID_STATUSES,
)
from sync_engine import sync_products, dry_run_sync, get_sync_status


# ===== Configuration =====

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
PRODUCTS_DIR = DATA_DIR / 'products'
DEFAULT_FEED_PATH = BASE_DIR / 'bike-deals.json'


# ===== Commands =====

def cmd_validate():
    """Validate the entire product library."""
    print("=" * 60)
    print("PRODUCT LIBRARY VALIDATION")
    print("=" * 60)

    products = load_products(PRODUCTS_DIR)
    if not products:
        print("  No products found in", PRODUCTS_DIR)
        return False

    result = validate_products(products)

    # Print stats
    stats = result['stats']
    print(f"\n  Total products: {stats['total']}")
    print(f"  By status:")
    for status, count in sorted(stats['by_status'].items()):
        print(f"    {status}: {count}")
    print(f"  By category:")
    for category, count in sorted(stats['by_category'].items()):
        print(f"    {category}: {count}")

    # Print errors
    if result['errors']:
        print(f"\n  ERRORS ({len(result['errors'])}):")
        for error in result['errors']:
            print(f"    [ERROR] {error}")
    else:
        print("\n  No errors found.")

    # Print warnings
    if result['warnings']:
        print(f"\n  WARNINGS ({len(result['warnings'])}):")
        for warning in result['warnings']:
            print(f"    [WARN] {warning}")
    else:
        print("  No warnings found.")

    print()
    if result['valid']:
        print("  PASS: Product library is valid.")
    else:
        print("  FAIL: Product library has errors that must be fixed.")
    print("=" * 60)

    return result['valid']


def cmd_sync(dry_run=False):
    """Run the daily Amazon sync."""
    print("=" * 60)
    print("AMAZON SYNC" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 60)

    feed_path = DEFAULT_FEED_PATH
    if not feed_path.exists():
        print(f"\n  Feed file not found: {feed_path}")
        print("  Run bike.py first to generate Amazon deal data.")
        return False

    print(f"\n  Feed: {feed_path}")
    print(f"  Products: {PRODUCTS_DIR}")
    print()

    if dry_run:
        result = dry_run_sync(PRODUCTS_DIR, feed_path)
    else:
        result = sync_products(PRODUCTS_DIR, feed_path)

    print(result.summary())
    print()

    if result.synced > 0:
        print(f"  {result.synced} products updated with Amazon data.")
    elif result.matched > 0:
        print("  All products already up to date.")
    else:
        print("  No products matched the Amazon feed.")

    print("=" * 60)
    return True


def cmd_stats():
    """Print library statistics."""
    print("=" * 60)
    print("PRODUCT LIBRARY STATISTICS")
    print("=" * 60)

    products = load_products(PRODUCTS_DIR)
    if not products:
        print("  No products found.")
        return

    stats = generate_stats(products)

    print(f"\n  Total Products: {stats['total_products']}")
    print()

    # By status
    print("  By Status:")
    for status, count in sorted(stats['by_status'].items()):
        print(f"    {status:20s} {count}")
    print()

    # By category
    print("  By Category:")
    for category, count in sorted(stats['by_category'].items()):
        print(f"    {category:20s} {count}")
    print()

    # By brand
    print("  By Brand:")
    for brand, count in sorted(stats['by_brand'].items(), key=lambda x: -x[1]):
        print(f"    {brand:20s} {count}")
    print()

    # Quality metrics
    print("  Quality Metrics:")
    print(f"    Average Rating:        {stats['average_rating']}")
    print(f"    Average Editor Rating: {stats['average_editor_rating']}")
    print(f"    Average Price:         Rs.{stats['average_price']:.0f}")
    print(f"    Average Discount:      {stats['average_discount']}%")
    print()

    # Issues
    issues = []
    if stats['missing_editorial']:
        issues.append(f"    Missing Editorial:     {len(stats['missing_editorial'])} products")
    if stats['missing_images']:
        issues.append(f"    Missing Images:        {len(stats['missing_images'])} products")
    if stats['missing_affiliate']:
        issues.append(f"    Missing Affiliate URL: {len(stats['missing_affiliate'])} products")
    if stats['duplicate_asins']:
        issues.append(f"    Duplicate ASINs:       {len(stats['duplicate_asins'])} groups")

    if issues:
        print("  Issues:")
        for issue in issues:
            print(issue)
    else:
        print("  No issues found.")

    print()

    # Sync status
    sync_status = get_sync_status(PRODUCTS_DIR)
    print("  Sync Status:")
    print(f"    Approved Products: {sync_status['approved_products']}")
    print(f"    Synced:            {sync_status['synced_products']}")
    print(f"    Unsynced:          {sync_status['unsynced_products']}")
    if sync_status['newest_sync']:
        print(f"    Last Sync:         {sync_status['newest_sync']}")
    else:
        print(f"    Last Sync:         Never")

    print("=" * 60)


def cmd_import():
    """Import products from bike-deals.json into the Product Library."""
    print("=" * 60)
    print("IMPORT FROM BIKE-DEALS.JSON")
    print("=" * 60)

    from product_importer import import_from_deals

    feed_path = DEFAULT_FEED_PATH
    if not feed_path.exists():
        print(f"\n  Feed file not found: {feed_path}")
        print("  Run bike.py first to generate Amazon deal data.")
        return False

    print(f"\n  Feed: {feed_path}")
    print(f"  Products: {PRODUCTS_DIR}")

    result = import_from_deals(feed_path, PRODUCTS_DIR, dry_run=False, verbose=False)

    # Print verification summary
    print(f"\n  Products found:      {result['found']}")
    print(f"  Products imported:   {result['imported']}  (new, status: draft)")
    print(f"  Products updated:    {result['updated']}  (existing, Amazon fields)")
    print(f"  Products skipped:    {result['skipped']}  (no category mapping)")
    print(f"  Duplicate ASINs:     {result['duplicate_asins']}")

    if result['errors']:
        print(f"\n  Errors:")
        for e in result['errors']:
            print(f"    - {e}")

    print(f"\n  Products by category:")
    for cat, count in sorted(result['by_category'].items(), key=lambda x: -x[1]):
        print(f"    {cat:25s} {count}")

    # Show what categories now exist in the library
    products = load_products(PRODUCTS_DIR)
    cats = {}
    for p in products:
        c = p.get('category', 'Unknown')
        cats[c] = cats.get(c, 0) + 1
    print(f"\n  Categories in library ({len(cats)}):")
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"    {cat:25s} {count}")

    print("\n" + "=" * 60)
    return True


def cmd_export():
    """Export library to JSON."""
    print("=" * 60)
    print("EXPORT PRODUCT LIBRARY")
    print("=" * 60)

    products = load_products(PRODUCTS_DIR)
    if not products:
        print("  No products to export.")
        return

    output_path = DATA_DIR / 'products_export.json'
    export_products(products, output_path)

    print(f"\n  Exported {len(products)} products to:")
    print(f"    {output_path}")
    print("=" * 60)


def cmd_find_duplicates():
    """Find duplicate ASINs/titles."""
    print("=" * 60)
    print("DUPLICATE DETECTION")
    print("=" * 60)

    products = load_products(PRODUCTS_DIR)
    result = find_duplicates(products)

    # ASIN duplicates
    if result['asin_duplicates']:
        print(f"\n  Duplicate ASINs ({len(result['asin_duplicates'])} groups):")
        for dup in result['asin_duplicates']:
            print(f"    ASIN {dup['asin']}: {', '.join(dup['products'])}")
    else:
        print("\n  No duplicate ASINs found.")

    # Slug duplicates
    if result['slug_duplicates']:
        print(f"\n  Duplicate Slugs ({len(result['slug_duplicates'])} groups):")
        for dup in result['slug_duplicates']:
            print(f"    Slug '{dup['slug']}': {', '.join(dup['sources'])}")
    else:
        print("  No duplicate slugs found.")

    # Title duplicates
    if result['title_duplicates']:
        print(f"\n  Duplicate Titles ({len(result['title_duplicates'])} groups):")
        for dup in result['title_duplicates']:
            print(f"    Title '{dup['title'][:50]}...': {', '.join(dup['products'])}")
    else:
        print("  No duplicate titles found.")

    total = (len(result['asin_duplicates']) + len(result['slug_duplicates']) +
             len(result['title_duplicates']))
    print()
    if total == 0:
        print("  PASS: No duplicates found.")
    else:
        print(f"  WARN: Found {total} duplicate groups.")

    print("=" * 60)


def cmd_list(status_filter=None, category_filter=None):
    """List all products."""
    products = load_products(PRODUCTS_DIR)

    # Apply filters
    if status_filter:
        products = [p for p in products if p.get('status') == status_filter]
    if category_filter:
        products = [p for p in products if category_filter.lower() in p.get('category', '').lower()]

    if not products:
        print("No products found matching criteria.")
        return

    print(f"{'Slug':<30} {'Status':<15} {'Category':<15} {'Brand':<12} {'Price':>8} {'Rating':>6}")
    print("-" * 90)

    for p in products:
        slug = p.get('slug', '')[:29]
        status = p.get('status', '')
        category = p.get('category', '')[:14]
        brand = p.get('brand', '')[:11]
        price = p.get('price', 0)
        rating = p.get('rating', 0)
        print(f"{slug:<30} {status:<15} {category:<15} {brand:<12} Rs.{price:>5} {rating:>5.1f}")

    print(f"\nTotal: {len(products)} products")


def cmd_status(slug, new_status=None):
    """Show or change a product's status."""
    products = load_products(PRODUCTS_DIR)
    product = find_product_by_slug(products, slug)

    if not product:
        print(f"Product not found: {slug}")
        return False

    if new_status is None:
        # Show current status
        print(f"  Product: {product.get('title', '')}")
        print(f"  Slug:    {product.get('slug', '')}")
        print(f"  ASIN:    {product.get('asin', '')}")
        print(f"  Status:  {product.get('status', 'unknown')}")
        print(f"  Category: {product.get('category', '')}")
        print(f"  Brand:   {product.get('brand', '')}")
    else:
        # Change status
        if new_status not in VALID_STATUSES:
            print(f"Invalid status: {new_status}")
            print(f"Valid statuses: {', '.join(sorted(VALID_STATUSES))}")
            return False

        old_status = product.get('status', 'unknown')
        product['status'] = new_status

        # Save back to file
        source_file = product.get('_source_file', '')
        if source_file:
            filepath = PRODUCTS_DIR / source_file
            if filepath.exists():
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Find and update the product
                for i, item in enumerate(data):
                    if item.get('slug') == slug:
                        item['status'] = new_status
                        break

                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                print(f"  Updated '{slug}' status: {old_status} -> {new_status}")
                return True

    return True


# ===== Main =====

def print_usage():
    """Print usage information."""
    print("""
Product Library Management CLI

Commands:
    import                        Import from bike-deals.json into Product Library
    validate                      Validate entire product library
    sync [--dry-run]              Run daily Amazon sync
    stats                         Print library statistics
    export                        Export library to JSON
    find_duplicates               Find duplicate ASINs/titles
    list [--status S] [--category C]  List products
    status <slug> [new_status]    Show/change product status

Examples:
    python products.py import
    python products.py validate
    python products.py sync --dry-run
    python products.py stats
    python products.py list --status approved
    python products.py list --category Helmet
    python products.py status bobo-bm4-pro-plus hidden
""")


def main():
    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1].lower()

    if command == 'validate':
        cmd_validate()
    elif command == 'sync':
        dry_run = '--dry-run' in sys.argv
        cmd_sync(dry_run=dry_run)
    elif command == 'stats':
        cmd_stats()
    elif command == 'import':
        cmd_import()
    elif command == 'export':
        cmd_export()
    elif command == 'find_duplicates':
        cmd_find_duplicates()
    elif command == 'list':
        status_filter = None
        category_filter = None
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] == '--status' and i + 1 < len(args):
                status_filter = args[i + 1]
                i += 2
            elif args[i] == '--category' and i + 1 < len(args):
                category_filter = args[i + 1]
                i += 2
            else:
                i += 1
        cmd_list(status_filter=status_filter, category_filter=category_filter)
    elif command == 'status':
        if len(sys.argv) < 3:
            print("Usage: python products.py status <slug> [new_status]")
            return
        slug = sys.argv[2]
        new_status = sys.argv[3] if len(sys.argv) > 3 else None
        cmd_status(slug, new_status)
    elif command in ('--help', '-h', 'help'):
        print_usage()
    else:
        print(f"Unknown command: {command}")
        print_usage()


if __name__ == '__main__':
    main()
