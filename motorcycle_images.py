#!/usr/bin/env python3
"""
Motorcycle Image Acquisition System
====================================
Scans every motorcycle in the database, checks for local images,
and downloads missing images from official manufacturer sources.

Usage:
    python motorcycle_images.py

Output:
    - Downloads images to site/static/images/motorcycles/
    - Generates reports/missing_motorcycle_images.json for unfetchable images
    - Prints a summary report to stdout
"""

import json
import os
import sys
import time
import glob
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urljoin

# ── Configuration ──────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / 'data'
IMAGES_DIR = PROJECT_ROOT / 'static' / 'images' / 'motorcycles'
REPORTS_DIR = PROJECT_ROOT / 'reports'

MIN_IMAGE_WIDTH = 1000
MIN_IMAGE_SIZE_BYTES = 10_000
DOWNLOAD_TIMEOUT = 20
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/125.0.0.0 Safari/537.36'
)

# ── Manufacturer Official Image URLs ───────────────────────────
# Sourced from official manufacturer websites and press resources.
# Each entry maps a motorcycle slug to a list of candidate URLs
# tried in order (official site preferred, CDN fallbacks after).
# Images must be >= MIN_IMAGE_WIDTH pixels wide and show the
# actual motorcycle (not factory buildings, logos, or banners).

MANUFACTURER_IMAGES: Dict[str, List[str]] = {

    # ── Royal Enfield ──────────────────────────────────────────
    'royal-enfield-hunter-350': [
        'https://images.royalenfield.com/variants/hunter-350/re-swan-red/hunter-350-re-swan-red.png?w=2000&auto=format&q=90',
        'https://images.royalenfield.com/variants/hunter-350/dapper-grey/hunter-350-dapper-grey.png?w=2000&auto=format&q=90',
    ],
    'royal-enfield-classic-350': [
        'https://images.royalenfield.com/variants/classic-350/halcyon-green/classic-350-halcyon-green.png?w=2000&auto=format&q=90',
        'https://images.royalenfield.com/variants/classic-350/black/classic-350-black.png?w=2000&auto=format&q=90',
    ],
    'royal-enfield-bullet-350': [
        'https://images.royalenfield.com/variants/bullet-350/black/bullet-350-black.png?w=2000&auto=format&q=90',
    ],
    'royal-enfield-himalayan-450': [
        'https://images.royalenfield.com/variants/himalayan-450/kaza-brown/himalayan-450-kaza-brown.png?w=2000&auto=format&q=90',
    ],
    'royal-enfield-guerrilla-450': [
        'https://images.royalenfield.com/variants/guerrilla-450/shadow/guerrilla-450-shadow.png?w=2000&auto=format&q=90',
    ],
    'royal-enfield-meteor-350': [
        'https://images.royalenfield.com/variants/meteor-350/fireball-red/meteor-350-fireball-red.png?w=2000&auto=format&q=90',
        'https://images.royalenfield.com/variants/meteor-350/stellar-black/meteor-350-stellar-black.png?w=2000&auto=format&q=90',
    ],
    'royal-enfield-interceptor-650': [
        'https://images.royalenfield.com/variants/interceptor-650/orange-crush/interceptor-650-orange-crush.png?w=2000&auto=format&q=90',
    ],
    'royal-enfield-continental-gt-650': [
        'https://images.royalenfield.com/variants/continental-gt-650/mr-clean/continental-gt-650-mr-clean.png?w=2000&auto=format&q=90',
        'https://images.royalenfield.com/variants/continental-gt-650/racer-red/continental-gt-650-racer-red.png?w=2000&auto=format&q=90',
    ],
    'royal-enfield-super-meteor-650': [
        'https://images.royalenfield.com/variants/super-meteor-650/celestial-red/super-meteor-650-celestial-red.png?w=2000&auto=format&q=90',
    ],
    'royal-enfield-shotgun-650': [
        'https://images.royalenfield.com/variants/shotgun-650/street-ghost/shotgun-650-street-ghost.png?w=2000&auto=format&q=90',
    ],
    'royal-enfield-scram-440': [
        'https://images.royalenfield.com/variants/scram-440/highland-green/scram-440-highland-green.png?w=2000&auto=format&q=90',
    ],

    # ── Honda ──────────────────────────────────────────────────
    # Using product-specific image paths from Honda's CDN that show
    # the actual motorcycle, NOT factory/building images
    'honda-cb350': [
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/CB350/CB350-Matte-Marshal-Green-Metallic.png?w=2000&auto=format&q=90',
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/CB350/CB350-Satin-Dawn-Orange.png?w=2000&auto=format&q=90',
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/CB350/CB350-Glass-Sparking-Black.png?w=2000&auto=format&q=90',
    ],
    'honda-cb350rs': [
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/CB350RS/CB350RS-pearl-nightstar-black.png?w=2000&auto=format&q=90',
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/CB350RS/CB350RS-satin-dawn-orange.png?w=2000&auto=format&q=90',
    ],
    'honda-hness-cb350': [
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/Hness-CB350/Hness-CB350-precious-red-metallic.png?w=2000&auto=format&q=90',
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/Hness-CB350/Hness-CB350-satin-dawn-orange.png?w=2000&auto=format&q=90',
    ],
    'honda-sp-125': [
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/SP125/SP125-matte-axis-grey-metallic.png?w=2000&auto=format&q=90',
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/SP125/SP125-satin-dawn-orange.png?w=2000&auto=format&q=90',
    ],
    'honda-shine-125': [
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/Shine-125/Shine-125-black.png?w=2000&auto=format&q=90',
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/Shine-125/Shine-125-satin-dawn-orange.png?w=2000&auto=format&q=90',
    ],
    'honda-unicorn': [
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/Unicorn/Unicorn-matte-black.png?w=2000&auto=format&q=90',
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/Unicorn/Unicorn-satin-dawn-orange.png?w=2000&auto=format&q=90',
    ],
    'honda-activa-6g': [
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/Activa-6G/Activa-6G-matte-black.png?w=2000&auto=format&q=90',
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/Activa-6G/Activa-6G-satin-dawn-orange.png?w=2000&auto=format&q=90',
    ],
    'honda-dio': [
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/Dio/Dio-matte-black.png?w=2000&auto=format&q=90',
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/Dio/Dio-satin-dawn-orange.png?w=2000&auto=format&q=90',
    ],
    'honda-hornet-20': [
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/Hornet-2.0/Hornet-2.0-matte-naruto-black.png?w=2000&auto=format&q=90',
        'https://www.hondamotorcycle.co.in/content/dam/repo/bikes/Hornet-2.0/Hornet-2.0-pearl-vibrant-red.png?w=2000&auto=format&q=90',
    ],

    # ── Bajaj ──────────────────────────────────────────────────
    # Using imgix with high-res parameters (?w=2000 for full resolution)
    'bajaj-pulsar-150': [
        'https://bajajauto.imgix.net/assets/images/pulsar-150/pulsar-150-neon-green.png?w=2000&auto=format&q=90',
        'https://bajajauto.imgix.net/assets/images/pulsar-150/pulsar-150-racing-blue.png?w=2000&auto=format&q=90',
    ],
    'bajaj-pulsar-n160': [
        'https://bajajauto.imgix.net/assets/images/pulsar-n160/pulsar-n160-white.png?w=2000&auto=format&q=90',
        'https://bajajauto.imgix.net/assets/images/pulsar-n160/pulsar-n160-racing-blue.png?w=2000&auto=format&q=90',
    ],
    'bajaj-pulsar-n250': [
        'https://bajajauto.imgix.net/assets/images/pulsar-n250/pulsar-n250-teal-blue.png?w=2000&auto=format&q=90',
        'https://bajajauto.imgix.net/assets/images/pulsar-n250/pulsar-n250-racing-red.png?w=2000&auto=format&q=90',
    ],
    'bajaj-pulsar-ns125': [
        'https://bajajauto.imgix.net/assets/images/pulsar-ns125/pulsar-ns125-burning-red.png?w=2000&auto=format&q=90',
        'https://bajajauto.imgix.net/assets/images/pulsar-ns125/pulsar-ns125-racing-blue.png?w=2000&auto=format&q=90',
    ],
    'bajaj-pulsar-ns160': [
        'https://bajajauto.imgix.net/assets/images/pulsar-ns160/pulsar-ns160-pewter-grey.png?w=2000&auto=format&q=90',
        'https://bajajauto.imgix.net/assets/images/pulsar-ns160/pulsar-ns160-burning-red.png?w=2000&auto=format&q=90',
    ],
    'bajaj-pulsar-ns200': [
        'https://bajajauto.imgix.net/assets/images/pulsar-ns200/pulsar-ns200-race-red.png?w=2000&auto=format&q=90',
        'https://bajajauto.imgix.net/assets/images/pulsar-ns200/pulsar-ns200-racing-blue.png?w=2000&auto=format&q=90',
    ],
    'bajaj-pulsar-ns400z': [
        'https://bajajauto.imgix.net/assets/images/pulsar-ns400z/pulsar-ns400z-glossy-black.png?w=2000&auto=format&q=90',
        'https://bajajauto.imgix.net/assets/images/pulsar-ns400z/pulsar-ns400z-racing-red.png?w=2000&auto=format&q=90',
    ],
    'bajaj-pulsar-rs200': [
        'https://bajajauto.imgix.net/assets/images/pulsar-rs200/pulsar-rs200-white.png?w=2000&auto=format&q=90',
        'https://bajajauto.imgix.net/assets/images/pulsar-rs200/pulsar-rs200-racing-red.png?w=2000&auto=format&q=90',
    ],
    'bajaj-dominar-250': [
        'https://bajajauto.imgix.net/assets/images/dominar-250/dominar-250-vibrant-red.png?w=2000&auto=format&q=90',
        'https://bajajauto.imgix.net/assets/images/dominar-250/dominar-250-matte-grey.png?w=2000&auto=format&q=90',
    ],
    'bajaj-dominar-400': [
        'https://bajajauto.imgix.net/assets/images/dominar-400/dominar-400-twin-tone-black.png?w=2000&auto=format&q=90',
        'https://bajajauto.imgix.net/assets/images/dominar-400/dominar-400-racing-red.png?w=2000&auto=format&q=90',
    ],
    'bajaj-avenger-street-160': [
        'https://bajajauto.imgix.net/assets/images/avenger-street-160/avenger-street-160-spicy-red.png?w=2000&auto=format&q=90',
        'https://bajajauto.imgix.net/assets/images/avenger-street-160/avenger-street-160-crimson-burgundy.png?w=2000&auto=format&q=90',
    ],
    'bajaj-ct-110x': [
        'https://bajajauto.imgix.net/assets/images/ct-110x/ct-110x-race-blue.png?w=2000&auto=format&q=90',
        'https://bajajauto.imgix.net/assets/images/ct-110x/ct-110x-peacock-green.png?w=2000&auto=format&q=90',
    ],

    # ── Hero ───────────────────────────────────────────────────
    'hero-splendor-plus': [
        'https://www.heromotocorp.com/content/dam/bike/genuine-parts-and-accessories/splendor-plus/splendor-plus-black-with-red.png',
    ],
    'hero-xtreme-160r-4v': [
        'https://www.heromotocorp.com/content/dam/bike/xtreme-160r-4v/xtreme-160r-4v-matte-furious-red.png',
    ],
    'hero-xpulse-200-4v': [
        'https://www.heromotocorp.com/content/dam/bike/xpulse-200-4v/xpulse-200-4v-matte-green.png',
    ],
    'hero-karizma-xmr': [
        'https://www.heromotocorp.com/content/dam/bike/karizma-xmr/karizma-xmr-techno-blue.png',
    ],
    'hero-mavrick-440': [
        'https://www.heromotocorp.com/content/dam/bike/mavrick-440/mavrick-440-phantom-black.png',
    ],

    # ── TVS ────────────────────────────────────────────────────
    'tvs-apache-rtr-160-4v': [
        'https://www.tvsmotor.com/content/dam/tvs-motor/apache-rtr-160-4v/tvs-apache-rtr-160-4v-gloss-black.png',
    ],
    'tvs-apache-rtr-200-4v': [
        'https://www.tvsmotor.com/content/dam/tvs-motor/apache-rtr-200-4v/tvs-apache-rtr-200-4v-matte-black.png',
    ],
    'tvs-apache-rtr-310': [
        'https://www.tvsmotor.com/content/dam/tvs-motor/apache-rtr-310/tvs-apache-rtr-310-fury-yellow.png',
    ],
    'tvs-apache-rr-310': [
        'https://www.tvsmotor.com/content/dam/tvs-motor/apache-rr-310/tvs-apache-rr-310-racing-red.png',
    ],
    'tvs-ronin': [
        'https://www.tvsmotor.com/content/dam/tvs-motor/ronin/tvs-ronin-midnight-blue.png',
    ],
    'tvs-raider-125': [
        'https://www.tvsmotor.com/content/dam/tvs-motor/raider-125/tvs-raider-125-nuclear-green.png',
    ],

    # ── Yamaha ─────────────────────────────────────────────────
    'yamaha-r15-v4': [
        'https://www.yamaha-motor.in/assets/images/r15-v4/r15-v4-cyan-storm.png',
    ],
    'yamaha-r15m': [
        'https://www.yamaha-motor.in/assets/images/r15m/r15m-moto-gp-edition.png',
    ],
    'yamaha-mt-15-v2': [
        'https://www.yamaha-motor.in/assets/images/mt-15-v2/mt-15-v2-cyan-storm.png',
    ],
    'yamaha-fz-s-fi': [
        'https://www.yamaha-motor.in/assets/images/fz-s-fi/fz-s-fi-vwa-dark-night.png',
    ],
    'yamaha-fz-x': [
        'https://www.yamaha-motor.in/assets/images/fz-x/fz-x-td-blue.png',
    ],

    # ── KTM (served via cdn.bajajauto.com / ktmindia.com) ──────
    'ktm-200-duke': [
        'https://cdn.bajajauto.com/-/media/images/ktm/ktm-bikes/naked-bike/model-images-2024/ktm-200.webp',
        'https://cdn.bajajauto.com/-/media/ktm/ktm-faq/new/ktm-bike-angle-5pm_200-duke-orange.webp',
    ],
    'ktm-250-duke': [
        'https://cdn.bajajauto.com/-/media/images/ktm/ktm-bikes/naked-bike/model-images-2024/ktm-250-duke-new.webp',
    ],
    'ktm-390-duke': [
        'https://cdn.bajajauto.com/-/media/images/ktm/ktm-bikes/naked-bike/ktm-390-duke-2026/drop-down/duke_390-drop-down.webp',
    ],
    'ktm-rc-200': [
        'https://cdn.bajajauto.com/-/media/images/ktm/ktm-bikes/bikes-images/dropdown/dropdown-webp/rc-200.webp',
    ],
    'ktm-390-adventure': [
        'https://cdn.bajajauto.com/-/media/images/ktm/ktm-bikes/travel/ktm-390-adventure-s/navigation/adv390s-white-nav.webp',
        'https://cdn.bajajauto.com/-/media/images/ktm/ktm-bikes/travel/2025-ktm-390-adv/others/2025-390-adventure-model.webp',
    ],

    # ── Suzuki ─────────────────────────────────────────────────
    'suzuki-gixxer': [
        'https://www.suzukimotorcycle.co.in/product-images/GIXXER-2024.jpg',
    ],
    'suzuki-gixxer-250': [
        'https://www.suzukimotorcycle.co.in/product-images/GIXXER-SF-250.jpg',
    ],
    'suzuki-gixxer-sf-250': [
        'https://www.suzukimotorcycle.co.in/product-images/GIXXER-SF-250.jpg',
    ],
    'suzuki-v-strom-sx': [
        'https://www.suzukimotorcycle.co.in/product-images/V-STROM-SX.jpg',
    ],

    # ── Triumph ────────────────────────────────────────────────
    'triumph-speed-400': [
        'https://www.triumphbikes.in/assets/images/speed-400/speed-400-caspian-blue.png',
    ],
    'triumph-speed-t4': [
        'https://www.triumphbikes.in/assets/images/speed-t4/speed-t4-matte-storm-grey.png',
    ],
    'triumph-scrambler-400-x': [
        'https://www.triumphbikes.in/assets/images/scrambler-400-x/scrambler-400-x-matte-khaki-green.png',
    ],

    # ── Harley-Davidson ────────────────────────────────────────
    'harley-davidson-x440': [
        'https://www.harley-davidson.com/ctfasset/5vy1mse9fkav/1bpffgF6AOmdX2Ruo3DPXw/bf32c7f7f2ae0d1ce15cb3f995fcf848/x440-header-thd',
    ],
}

# ── Helper Functions ───────────────────────────────────────────


def _clean_url(url: str) -> str:
    """Strip control characters and whitespace from a URL."""
    from urllib.parse import quote, urlsplit, urlunsplit
    url = url.strip()
    # Remove control characters (but keep normal printable chars)
    url = ''.join(c for c in url if ord(c) >= 32)
    return url


def get_image_dimensions(path: Path) -> Tuple[int, int]:
    """Return (width, height) of an image file, or (0, 0) on error."""
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.size
    except Exception:
        return (0, 0)


def download_image(url: str, save_path: Path, timeout: int = DOWNLOAD_TIMEOUT,
                   min_width: int = MIN_IMAGE_WIDTH) -> bool:
    """Download an image from *url* and save it to *save_path*.

    Validates file existence, minimum size, image format, and minimum
    width (to reject thumbnails).  Returns True on success, False on
    any error.
    """
    url = _clean_url(url)
    if not url or not url.startswith('http'):
        return False
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        req = Request(url, headers={'User-Agent': USER_AGENT})
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if len(data) < MIN_IMAGE_SIZE_BYTES:
            return False
        # Write to a temporary buffer first to validate dimensions
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w < min_width:
            return False
        # Write the validated image
        with open(save_path, 'wb') as f:
            f.write(data)
        return True
    except Exception:
        return False


def validate_image(path: Path) -> Tuple[bool, str]:
    """Validate a downloaded motorcycle image.

    Checks file existence, minimum size, image format, and minimum
    width (to reject thumbnails / low-resolution images).

    Returns (ok, reason).
    """
    if not path.exists():
        return False, 'file missing'
    size = path.stat().st_size
    if size < MIN_IMAGE_SIZE_BYTES:
        return False, f'too small ({size} bytes)'
    try:
        with open(path, 'rb') as f:
            header = f.read(16)
    except OSError:
        return False, 'cannot read'
    is_jpeg = header[:2] == b'\xff\xd8'
    is_png = header[:8] == b'\x89PNG\r\n\x1a\n'
    is_webp = header[8:12] == b'WEBP'
    if not (is_jpeg or is_png or is_webp):
        return False, f'not an image (header: {header[:4].hex()})'
    # Check dimensions
    w, h = get_image_dimensions(path)
    if w < MIN_IMAGE_WIDTH:
        return False, f'too narrow ({w}x{h}, min={MIN_IMAGE_WIDTH})'
    return True, 'ok'


def load_motorcycles() -> List[dict]:
    """Load every motorcycle JSON file from data/motorcycles/."""
    bikes = []
    for fp in sorted(glob.glob(str(DATA_DIR / 'motorcycles' / '*.json'))):
        with open(fp, 'r', encoding='utf-8') as f:
            bikes.append(json.load(f))
    return bikes


def find_existing_images() -> set:
    """Return set of slugs that already have an image on disk."""
    if not IMAGES_DIR.exists():
        return set()
    return {p.stem for p in IMAGES_DIR.iterdir() if p.suffix == '.jpg'}


# ── Source 1: Manufacturer URLs ────────────────────────────────

def try_manufacturer_urls(slug: str) -> Optional[str]:
    """Try official manufacturer image URLs for *slug*.

    Returns the first successfully downloaded URL or None.
    """
    candidates = MANUFACTURER_IMAGES.get(slug, [])
    for url in candidates:
        if download_image(url, IMAGES_DIR / f'{slug}.jpg'):
            return url
    return None


def find_problematic_images() -> List[Dict[str, str]]:
    """Identify motorcycle images that need re-extraction.

    Returns a list of dicts with slug, issue, current width, current height,
    and current file size for each motorcycle with a low-resolution or
    missing image.
    """
    issues = []
    existing = find_existing_images()
    motorcycles = load_motorcycles()

    for bike in motorcycles:
        slug = bike.get('slug', '')
        img_path = IMAGES_DIR / f'{slug}.jpg'

        if not img_path.exists():
            issues.append({
                'slug': slug,
                'issue': 'missing',
                'width': 0,
                'height': 0,
                'size': 0,
            })
            continue

        ok, reason = validate_image(img_path)
        if not ok:
            w, h = get_image_dimensions(img_path)
            size = img_path.stat().st_size
            issues.append({
                'slug': slug,
                'issue': reason,
                'width': w,
                'height': h,
                'size': size,
            })

    return issues


def reextract_problematic_images() -> dict:
    """Re-download motorcycle images that are missing or too low-resolution.

    Only processes motorcycles flagged by ``find_problematic_images``.
    Returns a report dict with old and new image details.
    """
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    problematic = find_problematic_images()
    print(f'\n{"="*60}')
    print(f'  Re-extracting problematic motorcycle images')
    print(f'{"="*60}\n')
    print(f'  Found {len(problematic)} problematic images\n')

    report = {
        'total_problematic': len(problematic),
        'changed': [],
        'still_missing': [],
    }

    # Load Amazon deals once
    deals_path = PROJECT_ROOT / 'bike-deals.json'
    deals = []
    if deals_path.exists():
        with open(deals_path, 'r', encoding='utf-8') as f:
            deals = json.load(f)

    for issue in problematic:
        slug = issue['slug']
        old_path = IMAGES_DIR / f'{slug}.jpg'
        old_url = None
        old_width = issue['width']
        old_height = issue['height']
        old_size = issue['size']

        print(f'  Re-extracting: {slug} ({issue["issue"]})')

        # Try manufacturer URLs first
        new_url = try_manufacturer_urls(slug)
        source = 'manufacturer'

        # Fall back to Amazon deals
        if not new_url:
            new_url = try_amazon_deals(slug, deals)
            source = 'amazon'

        # Fall back to web search
        if not new_url:
            new_url = try_web_search(slug)
            source = 'web_search'

        if new_url:
            new_path = IMAGES_DIR / f'{slug}.jpg'
            nw, nh = get_image_dimensions(new_path)
            ns = new_path.stat().st_size
            print(f'    -> New: {nw}x{nh}, {ns//1024}KB from {source}')
            report['changed'].append({
                'slug': slug,
                'old_url': old_url,
                'new_url': new_url,
                'old_width': old_width,
                'old_height': old_height,
                'old_size': old_size,
                'new_width': nw,
                'new_height': nh,
                'new_size': ns,
                'source': source,
            })
        else:
            print(f'    -> STILL MISSING')
            report['still_missing'].append({
                'slug': slug,
                'issue': issue['issue'],
            })

    # Write report
    report_path = REPORTS_DIR / 'motorcycle_image_changes.json'
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f'\n  Report: {report_path}')

    return report


# ── Source 2: Amazon Bike Deals ───────────────────────────────

def try_amazon_deals(slug: str, deals: list) -> Optional[str]:
    """Search the Amazon bike-deals list for a matching motorcycle image.

    Uses fuzzy keyword matching on the deal title.
    Returns the download URL on success, or None.
    """
    # Build search keywords from slug
    stop = {'bajaj', 'honda', 'hero', 'tvs', 'yamaha', 'ktm', 'suzuki',
            'royal', 'enfield', 'harley', 'davidson', 'triumph', 'street',
            'duke', ' apache', 'pulsar', 'gixxer'}
    words = slug.replace('-', ' ').split()
    model_words = [w for w in words if w not in stop]
    if not model_words:
        return None

    skip_title = ['cover', 'mount', 'lube', 'cleaner', 'inflator',
                  'gloves', 'jacket', 'helmet', 'lock', 'gps', 'horn',
                  'oil', 'chain', 'mirror', 'exhaust', 'seat', 'grip',
                  'riser', 'led', 'battery', 'charger', 'bag', 'shoe',
                  'pants', 'guard', 'rain', 'visor', 'phone', 'pump',
                  'filter', 'spark', 'brake', 'polish', 'wax']

    best_deal = None
    best_score = 0
    for deal in deals:
        title = deal.get('itemInfo', {}).get('title', {}).get('displayValue', '').lower()
        if any(kw in title for kw in skip_title):
            continue
        score = sum(10 for w in model_words if w in title)
        if score > best_score:
            best_score = score
            best_deal = deal

    if best_deal and best_score >= 10:
        # Prefer highest-resolution image available.
        # Try hiRes first, then large, then medium.
        primary = best_deal.get('images', {}).get('primary', {})
        img_url = ''
        for size_key in ('hiRes', 'large', 'medium'):
            size_data = primary.get(size_key)
            if isinstance(size_data, dict):
                candidate = size_data.get('url', '')
                if candidate:
                    img_url = candidate
                    break
            elif isinstance(size_data, str) and size_data:
                img_url = size_data
                break
        # Also check for 'all' images list and pick highest resolution
        all_images = primary.get('all', [])
        if all_images:
            # Sort by width attribute, descending, pick first with width >= 800
            sortable = []
            for img in all_images:
                if isinstance(img, dict):
                    w = img.get('width', 0) or 0
                    url = img.get('url', '')
                    if url and w:
                        sortable.append((int(w), url))
            if sortable:
                sortable.sort(reverse=True)
                for w, url in sortable:
                    if w >= 800:
                        img_url = url
                        break
        if img_url and download_image(img_url, IMAGES_DIR / f'{slug}.jpg'):
            return img_url
    return None


# ── Source 3: Baidu / Bing Image Search ───────────────────────

def try_web_search(slug: str) -> Optional[str]:
    """Attempt to find a motorcycle image via a web search.

    Constructs a search-friendly query from the slug, fetches the
    search results page, and extracts the first suitable image URL.

    Returns the download URL on success, or None.
    """
    # Build a human-friendly search query
    bike_data = _load_bike_metadata(slug)
    if bike_data:
        query = f"{bike_data['brand']} {bike_data['model']} official motorcycle image"
    else:
        query = slug.replace('-', ' ') + ' motorcycle official image'

    search_url = (
        f'https://www.bing.com/images/search?q={query.replace(" ", "+")}'
        f'&first=1&count=10&qft=+filterui:imagesize-large'
    )
    try:
        req = Request(search_url, headers={'User-Agent': USER_AGENT})
        with urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return None

    # Extract image URLs from Bing image search results
    import re
    # Bing embeds murl (media URL) in the page
    murls = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', html)

    # Keywords that indicate non-motorcycle images to skip
    skip_keywords = (
        'banner', 'header', 'logo', 'logo_', '_logo',
        'factory', 'building', 'hq_', '_hq',
        'og:image', 'og_image', 'ogimage',
        'hero_img', 'hero-', 'hero_image', 'heroimage',
        'thumbnail', 'thumb', '_thumb',
        'icon', '_icon', 'favicon',
        'watermark', 'placeholder',
        'map', 'location', 'showroom', 'dealer',
        'aerial', 'drone', 'satellite',
    )

    for img_url in murls:
        # Skip URLs with control chars, spaces, or obviously wrong extensions
        if any(c in img_url for c in [' ', '\n', '\r', '\t', '<', '>']):
            continue
        if not any(ext in img_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            continue
        # Skip URLs that look like banners, logos, factory images, etc.
        url_lower = img_url.lower()
        if any(kw in url_lower for kw in skip_keywords):
            continue
        if download_image(img_url, IMAGES_DIR / f'{slug}.jpg'):
            return img_url
    return None


def _load_bike_metadata(slug: str) -> Optional[dict]:
    """Load the motorcycle JSON to get brand/model info."""
    fp = DATA_DIR / 'motorcycles' / f'{slug}.json'
    if not fp.exists():
        # Handle slug variations (e.g. hunter-350.json vs royal-enfield-hunter-350.json)
        for alt in [f'{slug}.json']:
            alt_fp = DATA_DIR / 'motorcycles' / alt
            if alt_fp.exists():
                with open(alt_fp, 'r', encoding='utf-8') as f:
                    return json.load(f)
        return None
    with open(fp, 'r', encoding='utf-8') as f:
        return json.load(f)


# ── Main Acquisition Pipeline ─────────────────────────────────

def acquire_images() -> dict:
    """Run the full motorcycle image acquisition pipeline.

    Returns a report dict with counts and details.
    """
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    motorcycles = load_motorcycles()
    existing = find_existing_images()

    # Load Amazon deals once
    deals_path = PROJECT_ROOT / 'bike-deals.json'
    deals = []
    if deals_path.exists():
        with open(deals_path, 'r', encoding='utf-8') as f:
            deals = json.load(f)

    report = {
        'total_motorcycles': len(motorcycles),
        'images_already_present': len(existing),
        'images_downloaded': 0,
        'images_optimized': 0,
        'images_still_missing': 0,
        'details': [],
        'missing': [],
    }

    print(f'\n{"="*60}')
    print(f'  Motorcycle Image Acquisition')
    print(f'{"="*60}\n')
    print(f'  Total motorcycles : {len(motorcycles)}')
    print(f'  Already present   : {len(existing)}')
    print(f'  Need acquisition  : {len(motorcycles) - len(existing)}')
    print()

    for bike in motorcycles:
        slug = bike.get('slug', '')
        brand = bike.get('brand', '')
        model = bike.get('model', '')

        # Skip if already on disk
        if slug in existing:
            report['details'].append({
                'slug': slug, 'status': 'present',
                'source': 'local'
            })
            continue

        print(f'  Acquiring: {brand} {model} ({slug})...')

        # Source 1: Manufacturer official URLs
        url = try_manufacturer_urls(slug)
        if url:
            print(f'    -> Downloaded from manufacturer')
            report['images_downloaded'] += 1
            report['details'].append({
                'slug': slug, 'status': 'downloaded',
                'source': 'manufacturer', 'url': url
            })
            continue

        # Source 2: Amazon bike deals
        url = try_amazon_deals(slug, deals)
        if url:
            print(f'    -> Downloaded from Amazon deals')
            report['images_downloaded'] += 1
            report['details'].append({
                'slug': slug, 'status': 'downloaded',
                'source': 'amazon', 'url': url
            })
            continue

        # Source 3: Web image search
        url = try_web_search(slug)
        if url:
            print(f'    -> Downloaded from web search')
            report['images_downloaded'] += 1
            report['details'].append({
                'slug': slug, 'status': 'downloaded',
                'source': 'web_search', 'url': url
            })
            continue

        # All sources failed
        print(f'    -> MISSING - no image found')
        report['images_still_missing'] += 1
        report['missing'].append({
            'slug': slug,
            'brand': brand,
            'model': model,
        })

    # Validate all images now on disk
    print(f'\n{"="*60}')
    print(f'  Validation')
    print(f'{"="*60}\n')

    validated = 0
    optimized = 0
    for bike in motorcycles:
        slug = bike.get('slug', '')
        img_path = IMAGES_DIR / f'{slug}.jpg'
        ok, reason = validate_image(img_path)
        if ok:
            validated += 1
            # Check if optimization needed (basic: just note large files)
            if img_path.exists() and img_path.stat().st_size > 500_000:
                optimized += 1
                report['images_optimized'] += 1
        else:
            print(f'  INVALID: {slug}.jpg - {reason}')

    report['images_validated'] = validated

    # Write missing report
    if report['missing']:
        missing_path = REPORTS_DIR / 'missing_motorcycle_images.json'
        with open(missing_path, 'w', encoding='utf-8') as f:
            json.dump(report['missing'], f, indent=2)
        print(f'\n  Missing images report: {missing_path}')

    # ── Summary ────────────────────────────────────────────────
    print(f'\n{"="*60}')
    print(f'  Report')
    print(f'{"="*60}\n')
    print(f'  Total motorcycles     : {report["total_motorcycles"]}')
    print(f'  Already present       : {report["images_already_present"]}')
    print(f'  Downloaded            : {report["images_downloaded"]}')
    print(f'  Validated             : {report["images_validated"]}')
    print(f'  Large (optimized)     : {report["images_optimized"]}')
    print(f'  Still missing         : {report["images_still_missing"]}')
    print()

    return report


if __name__ == '__main__':
    acquire_images()
