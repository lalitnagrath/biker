import json, os, re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

PROJECT_ROOT = Path(__file__).parent
IMAGES_DIR = PROJECT_ROOT / 'site' / 'static' / 'images' / 'motorcycles'
DATA_DIR = PROJECT_ROOT / 'data'
MIN_SIZE = 10000
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'

def clean_url(url):
    url = url.strip()
    return ''.join(c for c in url if ord(c) >= 32)

def download(url, save_path):
    url = clean_url(url)
    if not url or not url.startswith('http'):
        return False
    try:
        req = Request(url, headers={'User-Agent': UA})
        with urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < MIN_SIZE:
            return False
        with open(save_path, 'wb') as f:
            f.write(data)
        # Validate header
        with open(save_path, 'rb') as f:
            header = f.read(16)
        is_jpeg = header[:2] == b'\xff\xd8'
        is_png = header[:8] == b'\x89PNG\r\n\x1a\n'
        is_webp = header[8:12] == b'WEBP'
        if not (is_jpeg or is_png or is_webp):
            os.remove(save_path)
            return False
        return True
    except Exception:
        return False

def search_bing_images(query):
    """Search Bing images and return list of image URLs."""
    url = f'https://www.bing.com/images/search?q={query.replace(" ", "+")}&first=1&count=20&qft=+filterui:imagesize-large'
    try:
        req = Request(url, headers={'User-Agent': UA})
        with urlopen(req, timeout=20) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return []
    
    murls = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', html)
    results = []
    for u in murls:
        if any(c in u for c in [' ', '\n', '\r', '\t', '<', '>']):
            continue
        if any(ext in u.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            results.append(u)
    return results

# Missing motorcycles that need images
missing = [
    ('bajaj-dominar-250', 'Bajaj Dominar 250'),
    ('bajaj-pulsar-rs200', 'Bajaj Pulsar RS200'),
    ('harley-davidson-x440', 'Harley-Davidson X440'),
    ('hero-karizma-xmr', 'Hero Karizma XMR'),
    ('ktm-200-duke', 'KTM 200 Duke'),
    ('ktm-250-duke', 'KTM 250 Duke'),
    ('ktm-390-adventure', 'KTM 390 Adventure'),
    ('ktm-390-duke', 'KTM 390 Duke'),
    ('ktm-rc-200', 'KTM RC 200'),
    ('royal-enfield-interceptor-650', 'Royal Enfield Interceptor 650'),
    ('suzuki-gixxer-250', 'Suzuki Gixxer 250'),
    ('yamaha-fz-s-fi', 'Yamaha FZ-S Fi'),
]

downloaded = 0
still_missing = []

for slug, name in missing:
    save_path = IMAGES_DIR / f'{slug}.jpg'
    if save_path.exists():
        print(f'  Already exists: {slug}')
        continue
    
    print(f'  Searching: {name}...')
    urls = search_bing_images(f'{name} motorcycle official press photo')
    
    found = False
    for img_url in urls[:10]:
        if download(img_url, save_path):
            size = save_path.stat().st_size
            print(f'    -> Downloaded: {size} bytes from {img_url[:60]}')
            downloaded += 1
            found = True
            break
    
    if not found:
        # Try alternate query
        urls = search_bing_images(f'{name} bike image hd')
        for img_url in urls[:10]:
            if download(img_url, save_path):
                size = save_path.stat().st_size
                print(f'    -> Downloaded: {size} bytes from {img_url[:60]}')
                downloaded += 1
                found = True
                break
    
    if not found:
        print(f'    -> STILL MISSING')
        still_missing.append({'slug': slug, 'name': name})

print(f'\nDownloaded: {downloaded}')
print(f'Still missing: {len(still_missing)}')
for m in still_missing:
    print(f'  {m["slug"]}: {m["name"]}')
