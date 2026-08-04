#!/usr/bin/env python3
"""
Motorcycle Image Fix Report Generator
======================================
Identifies motorcycle images that are:
  1. Too low resolution (< 1000px width)
  2. Likely showing factory/building/banner images
  3. Missing entirely

Reports old image details and generates new URLs from the updated
MANUFACTURER_IMAGES dict.
"""

import json
import os
from pathlib import Path
from PIL import Image

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / 'data'
IMAGES_DIR = PROJECT_ROOT / 'static' / 'images' / 'motorcycles'
REPORTS_DIR = PROJECT_ROOT / 'reports'

MIN_WIDTH = 1000

# Known problematic images based on file size clustering
# (multiple Honda bikes all 113KB suggests same factory image)
HONDA_FACTORY_SIZE = 113  # KB - all Honda bikes with this size are factory images

# Bajaj Pulsar images that are 600x300 (thumbnails)
LOW_RES_BAJAJ = [
    'bajaj-pulsar-n160', 'bajaj-pulsar-n250', 'bajaj-pulsar-ns125',
    'bajaj-pulsar-ns160', 'bajaj-pulsar-ns200', 'bajaj-pulsar-ns400z',
    'bajaj-pulsar-rs200',
]

# Royal Enfield images below 1000px
LOW_RES_RE = ['royal-enfield-meteor-350', 'royal-enfield-continental-gt-650']


def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Import from motorcycle_images.py
    from motorcycle_images import (
        MANUFACTURER_IMAGES,
        download_image,
        validate_image,
        get_image_dimensions,
        find_existing_images,
        find_problematic_images,
        try_manufacturer_urls,
        try_amazon_deals,
        try_web_search,
        IMAGES_DIR as MI_IMAGES_DIR,
        load_motorcycles,
        USER_AGENT,
    )

    # Load motorcycles
    motorcycles = load_motorcycles()
    existing = find_existing_images()

    # Find problematic images
    problems = []
    for bike in motorcycles:
        slug = bike.get('slug', '')
        brand = bike.get('brand', '')
        model = bike.get('model', '')
        img_path = IMAGES_DIR / f'{slug}.jpg'

        if not img_path.exists():
            problems.append({
                'slug': slug,
                'brand': brand,
                'model': model,
                'issue': 'missing',
                'old_width': 0,
                'old_height': 0,
                'old_size': 0,
                'old_url': None,
            })
            continue

        ok, reason = validate_image(img_path)
        if not ok:
            w, h = get_image_dimensions(img_path)
            size = img_path.stat().st_size
            old_url = bike.get('image_url', '')  # might be stored somewhere
            problems.append({
                'slug': slug,
                'brand': brand,
                'model': model,
                'issue': reason,
                'old_width': w,
                'old_height': h,
                'old_size': size,
                'old_url': old_url or 'local file',
            })

        # Also check for Honda factory image (113KB, same image for all)
        if brand.lower() == 'honda':
            if size == HONDA_FACTORY_SIZE * 1024 or (w == h == 0 and size < 200000):
                # Check if already in problems
                already = any(p['slug'] == slug for p in problems)
                if not already:
                    problems.append({
                        'slug': slug,
                        'brand': brand,
                        'model': model,
                        'issue': 'factory/building image (likely)',
                        'old_width': w,
                        'old_height': h,
                        'old_size': size,
                        'old_url': old_url or 'local file',
                    })

    # Now find new URLs for each problematic motorcycle
    print(f'{'='*60}')
    print(f'  Motorcycle Image Fix Report')
    print(f'{'='*60}\n')
    print(f'Total motorcycles: {len(motorcycles)}')
    print(f'Problematic images: {len(problems)}')
    print()

    changed = []
    for p in problems:
        slug = p['slug']
        new_urls = MANUFACTURER_IMAGES.get(slug, [])
        
        print(f'Motorcycle: {p["brand"]} {p["model"]} ({slug})')
        print(f'  Issue: {p["issue"]}')
        print(f'  Old: {p["old_width"]}x{p["old_height"]}, {p["old_size"]//1024}KB')
        
        if new_urls:
            print(f'  New URL candidates:')
            for url in new_urls:
                print(f'    -> {url}')
            changed.append({
                'slug': slug,
                'brand': p['brand'],
                'model': p['model'],
                'issue': p['issue'],
                'old_width': p['old_width'],
                'old_height': p['old_height'],
                'old_size': p['old_size'],
                'old_url': p['old_url'],
                'new_url': new_urls[0],
                'new_url_candidates': new_urls,
            })
        else:
            print(f'  No updated URL available - will use web search fallback')
            changed.append({
                'slug': slug,
                'brand': p['brand'],
                'model': p['model'],
                'issue': p['issue'],
                'old_width': p['old_width'],
                'old_height': p['old_height'],
                'old_size': p['old_size'],
                'old_url': p['old_url'],
                'new_url': 'web search (to be determined)',
                'new_url_candidates': [],
            })
        print()

    # Write report
    report_path = REPORTS_DIR / 'motorcycle_image_fix_report.json'
    report = {
        'total_motorcycles': len(motorcycles),
        'problematic_count': len(problems),
        'changed_count': len(changed),
        'changed': changed,
    }
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f'Report saved: {report_path}')

    # Also write a summary text report
    txt_path = REPORTS_DIR / 'motorcycle_image_fix_report.txt'
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('Motorcycle Image Fix Report\n')
        f.write('=' * 60 + '\n\n')
        f.write(f'Total motorcycles: {len(motorcycles)}\n')
        f.write(f'Problematic images: {len(problems)}\n')
        f.write(f'Motorcycles with new URLs: {len(changed)}\n\n')
        f.write('--- Changed Motorcycles ---\n\n')
        for c in changed:
            f.write(f'Motorcycle: {c["brand"]} {c["model"]} ({c["slug"]})\n')
            f.write(f'  Issue: {c["issue"]}\n')
            f.write(f'  Old: {c["old_width"]}x{c["old_height"]}, {c["old_size"]//1024}KB\n')
            f.write(f'  Old URL: {c["old_url"]}\n')
            f.write(f'  New URL: {c["new_url"]}\n')
            f.write('\n')
    print(f'Text report saved: {txt_path}')

    return report


if __name__ == '__main__':
    main()
