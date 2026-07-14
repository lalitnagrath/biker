# coding: utf-8
"""
Fetch top deals using the CreatorsAPI SDK, download images and emit an HTML file.

Usage:
  Set environment variables `AMAZON_CREATOR_CREDENTIAL_ID` and `AMAZON_CREATOR_CREDENTIAL_SECRET`.
  Then run: python examples/fetch_deals.py

The script will write `examples/deals.html` and an `examples/images/` folder with images.
"""

import os
import sys
import time
import math
import json
import argparse
from typing import List, Dict, Any

import requests

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from creatorsapi_python_sdk.api_client import ApiClient
from creatorsapi_python_sdk.api.default_api import DefaultApi
from creatorsapi_python_sdk.models.search_items_request_content import SearchItemsRequestContent
from creatorsapi_python_sdk.exceptions import ApiException

# Optional credentials can be added here directly.
# If you prefer this method, replace None with your own values.
DEFAULT_CREDENTIAL_ID = "amzn1.application-oa2-client.b9b4e4acd8b145de93d67e30964552f6"
DEFAULT_CREDENTIAL_SECRET = "amzn1.oa2-cs.v1.c54ce65e63d4bc8d44bf9ec5dbb7a368aa943b0cc84bb89a32eb77afbb0ca028"
DEFAULT_PARTNER_TAG = "helpfulsurfer-21"
SEARCH_KEYWORDS = [
    'motorcycle helmet',
    'riding jacket',
    'riding gloves',
    'ear plugs',
    'bike phone mount',
    'bike cover',
    'chain lube',
    'chain cleaner',
    'bike disc lock',
    'gps tracker for bike',
    'motorcycle saddle bag',
    'tyre inflator',
]
SEARCH_INDICES = ['All']

IMAGES_DIR = os.path.join(os.path.dirname(__file__), 'bike-images')
OUTPUT_HTML = os.path.join(os.path.dirname(__file__), 'bike.html')
OUTPUT_JSON = os.path.join(os.path.dirname(__file__), 'bike-deals.json')
#OUTPUT_TOP10_HTML = os.path.join(os.path.dirname(__file__), 'top10.html')
SEEN_ASINS_FILE = os.path.join(os.path.dirname(__file__), 'bike-seen_asins1.txt')
OUTPUT_REDDIT_JSON = os.path.join(os.path.dirname(__file__), 'reddit-poster', 'bike-deals.json')



def get_credentials(credential_id: str | None = None, credential_secret: str | None = None):
    cid = credential_id or DEFAULT_CREDENTIAL_ID or os.environ.get('AMAZON_CREATOR_CREDENTIAL_ID')
    csecret = credential_secret or DEFAULT_CREDENTIAL_SECRET or os.environ.get('AMAZON_CREATOR_CREDENTIAL_SECRET')
    if not cid or not csecret:
        raise RuntimeError(
            'Please set AMAZON_CREATOR_CREDENTIAL_ID and AMAZON_CREATOR_CREDENTIAL_SECRET environment variables, '
            'or provide --credential-id and --credential-secret, or assign DEFAULT_CREDENTIAL_ID / DEFAULT_CREDENTIAL_SECRET in the script.'
        )
    return cid, csecret

def get_partner_tag(partner_tag: str | None = None) -> str:
    tag = partner_tag or DEFAULT_PARTNER_TAG or os.environ.get('helpfulsurfer-21')
    if not tag or not tag.strip():
        raise RuntimeError(
            'Please set AMAZON_PARTNER_TAG environment variable, provide --partner-tag, '
            'or assign DEFAULT_PARTNER_TAG in the script.'
        )
    return tag.strip()










def ensure_dirs():
    os.makedirs(IMAGES_DIR, exist_ok=True)


def load_seen_asins() -> set[str]:
    if not os.path.exists(SEEN_ASINS_FILE):
        return set()
    with open(SEEN_ASINS_FILE, 'r', encoding='utf-8') as f:
        return {line.strip() for line in f if line.strip()}


def save_seen_asins(asins: set[str]):
    with open(SEEN_ASINS_FILE, 'w', encoding='utf-8') as f:
        for asin in sorted(asins):
            f.write(f'{asin}\n')


def pick_image_url(item_dict: Dict[str, Any]) -> str:
    imgs = item_dict.get('images') or {}
    primary = imgs.get('primary') or {}
    # prefer large, then medium, then small
    for size in ('large', 'medium', 'small', 'hiRes'):
        s = primary.get(size)
        if isinstance(s, dict):
            url = s.get('url')
            if url:
                return url
    return ''


def truncate_title(title: str, max_words: int = 60) -> str:
    if not isinstance(title, str):
        return ''
    words = title.split()
    if len(words) <= max_words:
        return title
    return ' '.join(words[:max_words]) + '...'


def title_contains_filter(item_dict: Dict[str, Any], filter_text: str) -> bool:
    title = (item_dict.get('itemInfo') or {}).get('title')
    title_text = title.get('displayValue') if isinstance(title, dict) else title or ''
    return filter_text.lower() in title_text.lower()


def is_on_sale(item_dict: Dict[str, Any]) -> bool:
    offers = (item_dict.get('offersV2') or {}).get('listings') or []
    for listing in offers:
        if listing.get('dealDetails'):
            return True
        price = listing.get('price') or {}
        savings = price.get('savings') or {}
        pct = savings.get('percentage')
        amount = savings.get('amount')
        try:
            if pct is not None and float(pct) > 0:
                return True
        except Exception:
            pass
        try:
            if amount is not None and float(amount) > 0:
                return True
        except Exception:
            pass
    return False


def extract_savings_pct(item_dict: Dict[str, Any]) -> float:
    offers = (item_dict.get('offersV2') or {}).get('listings') or []
    best = 0.0
    for listing in offers:
        # check dealDetails presence
        if listing.get('dealDetails'):
            best = max(best, 0.0)
        price = listing.get('price') or {}
        savings = price.get('savings') or {}
        pct = savings.get('percentage')
        if pct is not None:
            try:
                best = max(best, float(pct))
            except Exception:
                pass
    return best


def extract_savings_amount(item_dict: Dict[str, Any]) -> float:
    offers = (item_dict.get('offersV2') or {}).get('listings') or []
    best_amount = 0.0
    for listing in offers:
        price = listing.get('price') or {}
        savings = price.get('savings') or {}
        amount = savings.get('amount')
        if amount is not None:
            try:
                best_amount = max(best_amount, float(amount))
            except Exception:
                pass
    return best_amount


def fetch_candidates(api: DefaultApi, marketplace: str, categories: List[str], partner_tag: str, seen_asins: set[str], search_keywords: List[str], per_cat: int = 50) -> List[Dict[str, Any]]:
    resources = [
        'images.primary.large',
        'images.primary.medium',
        'itemInfo.title',
        'offersV2.listings.dealDetails',
        'offersV2.listings.price',
        'offersV2.listings.loyaltyPoints',
        'offersV2.listings.merchantInfo',
        'offersV2.listings.type'
    ]

    seen = {}
    for keyword in search_keywords:
        for cat in categories:
            req = SearchItemsRequestContent(
                partner_tag=partner_tag,
                keywords=keyword,
                search_index=cat,
                item_count=per_cat,
                resources=resources
            )
            try:
                resp = api.search_items(x_marketplace=marketplace, search_items_request_content=req)
                rd = resp.to_dict() if hasattr(resp, 'to_dict') else {}
                items = (rd.get('searchResult') or {}).get('items') or []
                for it in items:
                    asin = it.get('asin')
                    if not asin:
                        continue
                    if asin in seen or asin in seen_asins:
                        continue
                    if keyword and not title_contains_filter(it, keyword):
                        continue
                    it['_search_keyword'] = keyword
                    it['_found_in_category'] = cat
                    seen[asin] = it
            except ApiException as e:
                print('API error for category', cat, 'keyword', keyword, e)
            except Exception as e:
                print('Unexpected error for category', cat, 'keyword', keyword, e)
            time.sleep(0.8)

    return list(seen.values())


def filter_and_sort(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deals = []
    for it in items:
        pct = extract_savings_pct(it)
        savings_amount = extract_savings_amount(it)
        it['_savings_pct'] = pct
        it['_savings_amount'] = savings_amount
        deals.append(it)

    deals.sort(key=lambda x: (x.get('_savings_pct', 0.0), x.get('_savings_amount', 0.0)), reverse=True)
    return deals


def download_image(url: str, dest: str):
    if not url:
        return False
    try:
        r = requests.get(url, timeout=10, stream=True)
        if r.status_code == 200:
            with open(dest, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return True
    except Exception:
        return False
    return False


def get_affiliate_url(item: Dict[str, Any], marketplace: str, partner_tag: str) -> str:
    detail_url = item.get('detailPageURL') or item.get('detail_page_url')
    if detail_url and isinstance(detail_url, str) and detail_url.strip():
        return detail_url

    asin = item.get('asin')
    if not asin:
        return '#'

    domain = marketplace if marketplace.startswith('www.') else marketplace
    domain = domain.replace('https://', '').replace('http://', '')
    if '/' in domain:
        domain = domain.split('/')[0]
    return f'https://{domain}/dp/{asin}/?tag={partner_tag}'


def save_deals_json(items: List[Dict[str, Any]], output_path: str):
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    print('Saved deal data to', output_path)


def load_deals_json(input_path: str) -> List[Dict[str, Any]]:
    with open(input_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_html(items: List[Dict[str, Any]], output_path: str, marketplace: str, partner_tag: str):
    def safe_anchor(value: str) -> str:
        return ''.join(ch if ch.isalnum() else '-' for ch in value.lower()).strip('-')

    def fmt_amount(value) -> str:
        try:
            v = float(value)
        except Exception:
            return str(value)
        # Format with comma separators and drop .00 when not needed
        s = f"{v:,.2f}"
        if s.endswith('.00'):
            s = s[:-3]
        return s
    html_parts = [
        '<!doctype html>',
        '<html><head><meta charset="utf-8"><title>DealsRadar-style Deals</title>',
        '<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">',
        '<style>',
        'html { scroll-behavior: smooth; }',
        'body { background: linear-gradient(180deg, #f7f8fc 0%, #eef1f9 100%); color: #111827; }',
        '.hero { padding: 3rem 0 2rem; }',
        '.hero h1 { font-size: clamp(2.5rem, 4vw, 4rem); line-height: 1.02; font-weight: 800; letter-spacing: -0.04em; margin-bottom: 1rem; }',
        '.hero p { font-size: 1rem; color: #4b5563; max-width: 720px; margin: 0 auto; }',
        '.category-pill { display: inline-flex; align-items: center; border-radius: 999px; border: 1px solid rgba(15,23,42,0.08); background: #fff; color: #111827; padding: 0.55rem 1rem; margin: 0.25rem 0.25rem 0 0; font-size: 0.95rem; text-decoration: none; transition: transform .2s ease, box-shadow .2s ease; }',
        '.category-pill:hover { transform: translateY(-1px); box-shadow: 0 16px 30px rgba(15,23,42,0.08); }',
        '.category-pill:nth-of-type(odd) { background: #fff7ed; color: #c2410c; border-color: rgba(249,115,22,0.2); }',
        '.deals-count { color: #6b7280; margin-top: 1rem; }',
        '.deals-grid { margin-top: 2rem; }',
        '.deal-card { overflow: hidden; border-radius: 24px; border: 1px solid rgba(15,23,42,0.08); background: #ffffff; box-shadow: 0 18px 40px rgba(15,23,42,0.06); transition: transform .2s ease, box-shadow .2s ease; }',
        '.deal-card:hover { transform: translateY(-2px); box-shadow: 0 24px 50px rgba(15,23,42,0.12), 0 0 20px rgba(249,115,22,0.25); }',
        '.deal-image { position: relative; overflow: visible; background: #f8fafc; display: flex; flex-direction: column; }',
        '.deal-image img.amazon-logo { width: 100%; height: 36px; object-fit: contain; display: block; flex-shrink: 0; padding-top: 10px; }',
        '.deal-image img.product-img { width: 100%; height: 110px; object-fit: cover; display: block; flex-shrink: 0; }',
        '.discount-badge { position: absolute; top: 16px; left: 16px; background: linear-gradient(135deg, #ff6b6b 0%, #fb7185 100%); color: #fff; font-weight: 700; padding: 0.4rem 0.85rem; border-radius: 999px; font-size: 0.9rem; box-shadow: 0 16px 32px rgba(251,113,133,0.18); }',
        '.deal-meta { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin-bottom: 0.5rem; }',
        '.deal-meta span.badge { font-size: 0.8rem !important; background: #fff7ed !important; color: #c2410c !important; padding: 0.35rem 0.65rem !important; border-radius: 999px !important; }',
        '.deal-card .card-body { display: flex; flex-direction: column; gap: 0.6rem; padding: 1.4rem; }',
        '.deal-card h6 { font-size: 1rem; line-height: 1.4; font-weight: 700; margin-bottom: 0.4rem; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis; min-height: 4.2rem; }',
        '.deal-price { display: flex; align-items: baseline; gap: 0.75rem; flex-wrap: wrap; }',
        '.deal-price .price-value { font-size: 1.2rem; font-weight: 700; color: #16a34a; }',
        '.deal-price .price-old { text-decoration: line-through; color: #6b7280; }',
        '.deal-price .price-savings { color: #dc2626; font-weight: 700; }',
        '.view-btn { width: 100%; background: linear-gradient(135deg, #f97316 0%, #ef4444 100%); color: #fff; border: none; border-radius: 999px; padding: 0.76rem 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; transition: transform .2s ease, box-shadow .2s ease; }',
        '.view-btn:hover { transform: translateY(-1px); box-shadow: 0 18px 32px rgba(239,68,68,0.22); }',
        '.section-heading { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }',
        '.section-heading h2 { margin: 0; font-size: 1.45rem; font-weight: 800; }',
        '.section-heading p { margin: 0; color: #6b7280; }',
        '.page-footer { padding: 2rem 0; text-align: center; color: #6b7280; }',
        '.page-footer a { color: #2563eb; text-decoration: none; }',
        '.page-footer a:hover { text-decoration: underline; }',
        '#backToTop { position: fixed; bottom: 24px; right: 24px; width: 48px; height: 48px; border-radius: 50%; background: linear-gradient(135deg, #f97316 0%, #ef4444 100%); color: #fff; border: none; font-size: 1.4rem; cursor: pointer; box-shadow: 0 8px 20px rgba(239,68,68,0.35); display: none; align-items: center; justify-content: center; z-index: 999; }',
        '#backToTop.show { display: flex; }',
        '</style>',
        '</head><body>',
        '<div class="container">',
        '<section id="top" class="hero text-center">',
        '<p class="text-uppercase fw-semibold mb-2" style="color:#f97316; letter-spacing:0.24em; font-size:0.85rem;">Daily Deals</p>',
        '<h1>Riding Gear deals</h1>',
        '<p>Find the best Amazon deals in one place. Every deal is selected for value, discount, and everyday usefulness.</p>',
        '</section>',
    ]

    cat_map = {}
    SECTION_ALIASES = {
        'motorcycle helmet': {'motorcycle', 'motorcycle helmet', 'riding helmet', 'bike helmet', 'helmet discount'},
        'riding jacket': {'riding jacket', 'motorcycle jacket', 'riding jacket sale'},
        'riding gloves': {'riding gloves', 'motorcycle gloves', 'bike gloves'},
        'ear plug': {'ear plug', 'ear plugs', 'riding ear plug'},
        'bike mobile holder': {'bike mobile holder', 'mobile holder', 'bike phone mount'},
        'bike cover': {'bike cover', 'motorcycle cover', 'bike body cover'},
        'chain lube': {'chain lube', 'bike chain lube', 'motorcycle chain lube'},
        'chain cleaner': {'chain cleaner', 'bike chain cleaner', 'motorcycle chain cleaner'},
        'disc lock for bike': {'disc lock for bike', 'bike disc lock', 'motorcycle disc lock'},
        'gps tracker for bike': {'gps tracker for bike', 'bike gps tracker', 'motorcycle gps tracker'},
        'saddle bag motorcycle': {'saddle bag motorcycle', 'motorcycle saddle bag', 'bike saddle bag'},
        'air compressor tyre inflator': {'air compressor tyre inflator', 'tyre inflator', 'bike air compressor'},
        'motorcycle toolkit': {'motorcycle toolkit', 'bike toolkit', 'motorcycle tool kit'},
    }
    def resolve_section(keyword: str) -> str:
        kw = keyword.lower().strip()
        for canonical, aliases in SECTION_ALIASES.items():
            if kw in aliases:
                return canonical
        return keyword
    for it in items:
        raw_keyword = it.get('_search_keyword') or (it.get('browseNodeInfo') or {}).get('displayName') or it.get('_found_in_category', 'General')
        block = resolve_section(raw_keyword)
        cat_map.setdefault(block, []).append(it)

    html_parts.append('<section class="mb-5">')
    html_parts.append('<div class="d-flex flex-wrap align-items-center gap-2 mb-3">')
    html_parts.append('<strong>Popular deal keywords:</strong>')
    for block in cat_map.keys():
        anchor = safe_anchor(block)
        html_parts.append(f'<a class="category-pill" href="#{anchor}">{block}</a>')
    html_parts.append('</div>')
    html_parts.append(f'<div class="deals-count">Showing {len(items)} handpicked deals across {len(cat_map)} keyword blocks.</div>')
    html_parts.append('</section>')

    html_parts.append('<section class="deals-grid">')
    for category, category_items in sorted(cat_map.items(), key=lambda x: (-len(x[1]), x[0])):
        anchor = safe_anchor(category)
        html_parts.append(f'<section id="{anchor}" class="mb-5">')
        html_parts.append('<div class="section-heading">')
        html_parts.append(f'<div><h2>{category}</h2><p>{len(category_items)} featured deals</p></div>')
        html_parts.append('</div>')
        html_parts.append('<div class="row row-cols-1 row-cols-sm-2 row-cols-md-3 row-cols-lg-4 row-cols-xl-5 g-4">')
        for it in category_items:
            title = (it.get('itemInfo') or {}).get('title')
            title_text = title.get('displayValue') if isinstance(title, dict) else title or 'No title available'
            title_text = truncate_title(title_text, max_words=60)
            asin = it.get('asin') or 'unknown'
            img_file = f'images/{asin}.jpg'
            price = ''
            original_price = ''
            savings = it.get('_savings_pct', 0.0)
            offers = (it.get('offersV2') or {}).get('listings') or []
            if offers:
                p = offers[0].get('price') or {}
                money = p.get('money') or {}
                amount = money.get('amount')
                # Always show Indian Rupee symbol as requested
                try:
                    if amount is not None:
                        price = f"₹{fmt_amount(amount)}"
                except Exception:
                    price = f"₹{amount}"
                if p.get('savings'):
                    savings_amount = p.get('savings', {}).get('amount')
                    try:
                        if amount is not None and savings_amount is not None:
                            original_price = f"₹{fmt_amount(float(amount) + float(savings_amount))}"
                    except Exception:
                         original_price = ''
            purchase_url = get_affiliate_url(it, marketplace, partner_tag)
            discount_badge = ''
            if savings and savings > 0:
                discount_badge = f'<span class="discount-badge">-{int(round(savings))}%</span>'

            html_parts.append('<div class="col">')
            html_parts.append('<div class="deal-card h-100">')
            html_parts.append('<div class="deal-image">')
            html_parts.append(f'<img src="" alt="{title_text}" style="display:none;">')
            if discount_badge:
                html_parts.append(discount_badge)
            html_parts.append('<img class="amazon-logo" src="amazon.png" alt="Amazon">')
            html_parts.append('</div>')
            html_parts.append('<div class="card-body d-flex flex-column">')
            html_parts.append(f'<span class="badge">{category}</span>')
            html_parts.append(f'<h6>{title_text}</h6>')
            html_parts.append('<div class="deal-price">')
            if price:
                html_parts.append(f'<span class="price-value">{price}</span>')
            if original_price:
                html_parts.append(f'<span class="price-old">{original_price}</span>')
            if savings and savings > 0:
                html_parts.append(f'<span class="price-savings">Save {int(round(savings))}%</span>')
            html_parts.append('</div>')
            html_parts.append(f'<button type="button" class="view-btn mt-auto" data-href="{purchase_url}">Buy on Amazon</button>')
            html_parts.append('</div>')
            html_parts.append('</div>')
            html_parts.append('</div>')
        html_parts.append('</div>')
        html_parts.append('</section>')
    html_parts.append('</section>')

    html_parts.append('</div>')
    html_parts.append('<footer class="page-footer">')
    html_parts.append('<p>Affiliate links may earn a small commission at no extra cost to you. Prices and availability can change.</p>')
    html_parts.append('</footer>')
    html_parts.append('<button id="backToTop" title="Back to top">&#8593;</button>')
    html_parts.append('<script>document.querySelectorAll("[data-href]").forEach(function(button){button.addEventListener("click", function(){window.open(button.dataset.href, "_blank", "noopener,noreferrer")});});</script>')
    html_parts.append('<script>const btn = document.getElementById("backToTop"); window.addEventListener("scroll", function() { btn.classList.toggle("show", window.scrollY > 400); }); btn.addEventListener("click", function() { window.scrollTo({ top: 0, behavior: "smooth" }); });</script>')
    html_parts.append('</body></html>')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html_parts))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--marketplace', default=os.environ.get('AMAZON_MARKETPLACE', 'www.amazon.in'))
    parser.add_argument('--per-cat', type=int, default=50)
    parser.add_argument('--top', type=int, default=100)
    parser.add_argument('--min-pct', type=float, default=1.0,
                        help='Minimum savings percentage to include a deal')
    parser.add_argument('--credential-id', default=None)
    parser.add_argument('--credential-secret', default=None)
    parser.add_argument('--partner-tag', default=None)
    parser.add_argument('--clear-cache', action='store_true', help='Clear saved ASIN cache before fetching new deals')
    parser.add_argument('--from-json', action='store_true', help='Generate HTML from existing JSON instead of fetching from API')
    args = parser.parse_args()

    if args.from_json:
        if not os.path.exists(OUTPUT_JSON):
            print('JSON file not found:', OUTPUT_JSON)
            return
        items = load_deals_json(OUTPUT_JSON)
        print('Loaded', len(items), 'deals from JSON')
        ensure_dirs()
        write_html(items, OUTPUT_HTML, args.marketplace, args.partner_tag or DEFAULT_PARTNER_TAG)
        print('Wrote HTML to', OUTPUT_HTML)
        return

    if args.clear_cache and os.path.exists(SEEN_ASINS_FILE):
        os.remove(SEEN_ASINS_FILE)

    cid, csecret = get_credentials(
        credential_id=args.credential_id,
        credential_secret=args.credential_secret,
    )
    partner_tag = get_partner_tag(args.partner_tag)
    ensure_dirs()

    api_client = ApiClient(
        credential_id=cid,
        credential_secret=csecret,
        version="3.2"
    )
    api = DefaultApi(api_client)

    categories = SEARCH_INDICES

    seen_asins = load_seen_asins()
    print('Skipping', len(seen_asins), 'previously seen products')
    print('Fetching candidates from categories:', categories)
    print('Using search keywords:', SEARCH_KEYWORDS)
    candidates = fetch_candidates(api, args.marketplace, categories, partner_tag, seen_asins, SEARCH_KEYWORDS, per_cat=args.per_cat)
    print('Fetched', len(candidates), 'new unique sale items for selected keywords')

    deals = filter_and_sort(candidates)
    print('Found', len(deals), 'deals after filtering')

    existing_items = load_deals_json(OUTPUT_JSON) if os.path.exists(OUTPUT_JSON) else []
    existing_by_asin = {it.get('asin'): it for it in existing_items if it.get('asin')}
    for it in deals:
        asin = it.get('asin')
        if asin:
            existing_by_asin[asin] = it
    merged = list(existing_by_asin.values())
    merged.sort(key=lambda x: (x.get('_savings_pct', 0.0), x.get('_savings_amount', 0.0)), reverse=True)
    top = merged[:args.top]
    print(f'Merged deals: {len(merged)} total ({len(top)} shown in HTML)')
    if not top:
        print('No deals found; skipping HTML generation.')
        new_asins = {it.get('asin') for it in candidates if it.get('asin')}
        save_seen_asins(seen_asins | new_asins)
        return

    new_asins = {it.get('asin') for it in candidates if it.get('asin')}
    save_seen_asins(seen_asins | new_asins)
    save_deals_json(merged, OUTPUT_JSON)
    

if __name__ == '__main__':
    main()
