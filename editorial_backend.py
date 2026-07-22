"""
Editorial Backend
=================
Decision-support scores for editors.  These calculations are **never** used by
the automatic ranking pipeline; they only produce `_editorial_*` keys on each
product dict so the editorial team can make informed manual choices.

Usage:
    from editorial_backend import compute_all_editorial_scores, print_editorial_report
    compute_all_editorial_scores(products, all_keywords)
    print_editorial_report(products)
"""

import json
import os
import math
from typing import Dict, Any, List, Optional

from product_ranking import (
    calculate_brand_score,
    calculate_discount_score,
    calculate_keyword_score,
    BRAND_SCORES,
)

# =============================================================================
#  Persistence helpers (price history, seen counts)
# =============================================================================

_PRICE_HISTORY_PATH = os.path.join(os.path.dirname(__file__), 'price_history.json')
_SEEN_COUNTS_PATH = os.path.join(os.path.dirname(__file__), 'seen_counts.json')


def load_price_history(path: str = _PRICE_HISTORY_PATH) -> Dict[str, list]:
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_price_history(history: Dict[str, list], path: str = _PRICE_HISTORY_PATH):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def update_price_history(
    history: Dict[str, list], products: List[Dict[str, Any]]
) -> Dict[str, list]:
    for p in products:
        asin = p.get('asin')
        if not asin:
            continue
        offers = (p.get('offersV2') or {}).get('listings') or []
        if not offers:
            continue
        price = offers[0].get('price') or {}
        money = price.get('money') or {}
        amount = money.get('amount')
        if amount is None:
            continue
        try:
            price_val = float(amount)
        except (TypeError, ValueError):
            continue
        if asin not in history:
            history[asin] = []
        history[asin].append(price_val)
        # Keep last 50 entries
        if len(history[asin]) > 50:
            history[asin] = history[asin][-50:]
    return history


def load_seen_counts(path: str = _SEEN_COUNTS_PATH) -> Dict[str, int]:
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_seen_counts(counts: Dict[str, int], path: str = _SEEN_COUNTS_PATH):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(counts, f, indent=2, ensure_ascii=False)


def update_seen_counts(
    counts: Dict[str, int], products: List[Dict[str, Any]]
) -> Dict[str, int]:
    for p in products:
        asin = p.get('asin')
        if asin:
            counts[asin] = counts.get(asin, 0) + 1
    return counts


# =============================================================================
#  Per-product editorial calculators
# =============================================================================

def editorial_brand_score(product: Dict[str, Any]) -> float:
    return calculate_brand_score(product)


def editorial_discount_score(product: Dict[str, Any]) -> float:
    return calculate_discount_score(product)


def editorial_keyword_popularity(
    product: Dict[str, Any], all_keywords: List[str]
) -> float:
    return calculate_keyword_score(product, all_keywords)


def editorial_price_history(product: Dict[str, Any]) -> Dict[str, Any]:
    history = product.get('_editorial_price_history') or {}
    return history


def editorial_times_seen(product: Dict[str, Any]) -> int:
    return product.get('_editorial_times_seen', 0)


def editorial_features(product: Dict[str, Any]) -> List[str]:
    item_info = product.get('itemInfo') or {}
    features = item_info.get('features') or {}
    display_values = features.get('displayValues') if isinstance(features, dict) else []
    if isinstance(display_values, list):
        return [str(f) for f in display_values if f]
    return []


def editorial_recommendation_score(product: Dict[str, Any]) -> float:
    weights = {
        'brand': 0.25,
        'discount': 0.25,
        'keyword_pop': 0.15,
        'times_seen': 0.10,
        'feature_count': 0.10,
        'price_history': 0.15,
    }
    score = 0.0
    total_weight = 0.0

    brand = product.get('_editorial_brand_score', 0.0)
    score += brand * weights['brand']
    total_weight += weights['brand']

    discount = product.get('_editorial_discount_score', 0.0)
    score += discount * weights['discount']
    total_weight += weights['discount']

    kw = product.get('_editorial_keyword_popularity', 0.0)
    score += kw * weights['keyword_pop']
    total_weight += weights['keyword_pop']

    times = product.get('_editorial_times_seen', 0)
    times_norm = min(1.0, times / 10.0)
    score += times_norm * weights['times_seen']
    total_weight += weights['times_seen']

    features_list = product.get('_editorial_features', [])
    feat_norm = min(1.0, len(features_list) / 10.0)
    score += feat_norm * weights['feature_count']
    total_weight += weights['feature_count']

    ph = product.get('_editorial_price_history', {})
    ph_score = ph.get('score', 0.0)
    score += ph_score * weights['price_history']
    total_weight += weights['price_history']

    if total_weight > 0:
        return score / total_weight
    return 0.0


# =============================================================================
#  Price history analysis helpers
# =============================================================================

def _analyze_price_history(
    asin: str, history: Dict[str, list]
) -> Dict[str, Any]:
    entries = history.get(asin, [])
    if not entries:
        return {
            'entries': 0,
            'current': None,
            'lowest': None,
            'highest': None,
            'volatility': 0.0,
            'score': 0.0,
        }
    current = entries[-1]
    lowest = min(entries)
    highest = max(entries)
    n = len(entries)

    # Volatility: coefficient of variation
    if n > 1 and sum(entries) > 0:
        mean = sum(entries) / n
        variance = sum((x - mean) ** 2 for x in entries) / n
        std_dev = math.sqrt(variance)
        volatility = std_dev / mean if mean > 0 else 0.0
    else:
        volatility = 0.0

    # Score: how close current price is to historical low
    if current and lowest and current > 0:
        score = min(1.0, max(0.0, lowest / current))
    else:
        score = 0.0

    return {
        'entries': n,
        'current': current,
        'lowest': lowest,
        'highest': highest,
        'volatility': round(volatility, 4),
        'score': round(score, 4),
    }


# =============================================================================
#  Batch compute
# =============================================================================

def compute_all_editorial_scores(
    products: List[Dict[str, Any]],
    all_keywords: Optional[List[str]] = None,
    price_history: Optional[Dict[str, list]] = None,
    seen_counts: Optional[Dict[str, int]] = None,
    persist: bool = True,
):
    """Compute editorial scores for all products.

    Args:
        products: List of product dicts (modified in-place with _editorial_* keys).
        all_keywords: List of search keywords for keyword popularity scoring.
        price_history: Pre-loaded price history dict (loaded from disk if None).
        seen_counts: Pre-loaded seen counts dict (loaded from disk if None).
        persist: If True, update persisted counts and save to disk.
                 Pass False for --from-json to avoid inflating counts on re-process.
    """
    if all_keywords is None:
        all_keywords = []
    if price_history is None:
        price_history = load_price_history()
    if seen_counts is None:
        seen_counts = load_seen_counts()

    if persist:
        update_seen_counts(seen_counts, products)
        update_price_history(price_history, products)

    for p in products:
        asin = p.get('asin', '')

        p['_editorial_brand_score'] = editorial_brand_score(p)
        p['_editorial_discount_score'] = editorial_discount_score(p)
        p['_editorial_savings_pct'] = p.get('_savings_pct', 0.0)
        p['_editorial_keyword_popularity'] = editorial_keyword_popularity(p, all_keywords)
        p['_editorial_features'] = editorial_features(p)
        p['_editorial_times_seen'] = seen_counts.get(asin, 0)
        p['_editorial_price_history'] = _analyze_price_history(asin, price_history)

    # Recommendation needs all other scores computed first
    for p in products:
        p['_editorial_recommendation_score'] = editorial_recommendation_score(p)

    if persist:
        save_seen_counts(seen_counts)
        save_price_history(price_history)


# =============================================================================
#  Terminal report
# =============================================================================

def _fmt(val, width, decimals=0):
    """Format a value for table display."""
    if val is None:
        return ' ' * width
    if isinstance(val, float):
        if decimals:
            return f'{val:.{decimals}f}'.rjust(width)
        return f'{val:.{decimals}f}'.rjust(width)
    s = str(val)
    if len(s) > width:
        s = s[:width - 3] + '...'
    return s.rjust(width)


def _trunc(s, max_len):
    if not s:
        return ''
    if len(s) > max_len:
        return s[:max_len - 3] + '...'
    return s


def print_editorial_report(products: List[Dict[str, Any]]):
    if not products:
        print('\n--- Editorial Report: no products ---')
        return

    print('\n' + '=' * 140)
    print('  EDITORIAL BACKEND REPORT (for editor decision support only)')
    print('=' * 140)

    headers = ['ASIN', 'Brand', 'Disc%', 'KwPop', 'Seen', 'Feat', 'Price Hist', 'Rec']
    col_widths = [12, 7, 7, 7, 6, 6, 28, 6]
    sep = ' | '

    header_line = sep.join(h.rjust(w) for h, w in zip(headers, col_widths))
    print('  ' + header_line)
    print('  ' + '-' * (sum(col_widths) + len(sep) * (len(headers) - 1)))

    for p in products:
        asin = p.get('asin', '')
        title_full = ''
        item_info = p.get('itemInfo') or {}
        title_data = item_info.get('title')
        if isinstance(title_data, dict):
            title_full = title_data.get('displayValue', '')
        elif isinstance(title_data, str):
            title_full = title_data

        brand = p.get('_editorial_brand_score', 0.0)
        disc = p.get('_editorial_savings_pct', 0.0)
        kw = p.get('_editorial_keyword_popularity', 0.0)
        seen = p.get('_editorial_times_seen', 0)
        feats = len(p.get('_editorial_features', []))
        ph = p.get('_editorial_price_history', {})
        rec = p.get('_editorial_recommendation_score', 0.0)

        ph_str = f"L{ph.get('lowest', '?')}/C{ph.get('current', '?')}/V{ph.get('volatility', 0)}"

        row = [
            asin.rjust(col_widths[0]),
            _fmt(brand, col_widths[1], 2),
            _fmt(disc, col_widths[2], 0),
            _fmt(kw, col_widths[3], 2),
            _fmt(seen, col_widths[4], 0),
            _fmt(feats, col_widths[5], 0),
            ph_str.rjust(col_widths[6]),
            _fmt(rec, col_widths[7], 2),
        ]
        line = sep.join(row)
        print(f'  {line}')
        print(f'  {_trunc(title_full, 110)}')
        print()

    print('=' * 140)
    print('  Recommendation score = composite of brand, discount, keyword match,')
    print('  times-seen, feature count, and price-history proximity to low.')
    print('  Scores stored in bike-deals.json under _editorial_* keys.')
    print('=' * 140 + '\n')


# =============================================================================
#  JSON export
# =============================================================================

def save_editorial_report(
    products: List[Dict[str, Any]],
    path: str = _PRICE_HISTORY_PATH.replace('price_history.json', 'editorial_report.json'),
):
    """Export editorial scores to a JSON file for further review."""
    report = []
    for p in products:
        entry = {
            'asin': p.get('asin', ''),
            'title': ((p.get('itemInfo') or {}).get('title') or {}).get('displayValue', '')
            if isinstance((p.get('itemInfo') or {}).get('title'), dict)
            else p.get('itemInfo', {}).get('title', ''),
            'editorial_brand_score': p.get('_editorial_brand_score', 0.0),
            'editorial_savings_pct': p.get('_editorial_savings_pct', 0.0),
            'editorial_discount_score': p.get('_editorial_discount_score', 0.0),
            'editorial_keyword_popularity': p.get('_editorial_keyword_popularity', 0.0),
            'editorial_times_seen': p.get('_editorial_times_seen', 0),
            'editorial_feature_count': len(p.get('_editorial_features', [])),
            'editorial_features': p.get('_editorial_features', []),
            'editorial_price_history': p.get('_editorial_price_history', {}),
            'editorial_recommendation_score': p.get('_editorial_recommendation_score', 0.0),
        }
        report.append(entry)
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return path
