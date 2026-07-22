"""
Shared helper for the ASIN refresh workflow.

Instead of skipping seen ASINs, each module now fetches pricing data for every
product and uses `refresh_product_pricing()` to update only dynamic fields on
existing records — preserving static fields (title, images, brand, etc.).
"""

from typing import Dict, Any

PRICING_FIELDS = {
    'offersV2',
    '_savings_pct',
    '_savings_amount',
    '_search_keyword',
    '_found_in_category',
}

STATIC_FIELDS = {
    'images',
    'itemInfo',
    'customerReviews',
    'browseNodeInfo',
}


def refresh_product_pricing(existing: Dict[str, Any],
                            fresh: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge a fresh API response into an existing product record.

    * Dynamic (pricing/offer) fields are always taken from *fresh*.
    * Static fields (title, images, brand, specs, reviews …) are preserved
      from *existing* unless they are missing/empty in *existing*.
    """
    result = dict(existing)

    # Always overwrite dynamic fields with latest API data
    for key in PRICING_FIELDS:
        if key in fresh:
            result[key] = fresh[key]

    # Fill in missing static fields from fresh data
    for key in STATIC_FIELDS:
        if key not in result or not result.get(key):
            if key in fresh:
                result[key] = fresh[key]

    # Ensure ASIN is never lost
    if 'asin' not in result or not result.get('asin'):
        if 'asin' in fresh:
            result['asin'] = fresh['asin']

    return result
