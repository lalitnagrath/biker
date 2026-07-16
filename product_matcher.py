"""
Deterministic Product Matcher
=============================
The ONLY place in the project that decides whether two product records refer
to the SAME physical product.

Hard rules (never violated):

    * No fuzzy title matching.
    * No similarity scores.
    * No partial word overlap.
    * No RapidFuzz. No Levenshtein.
    * Products are NEVER merged because titles "look similar".

Matching is attempted strictly in priority order:

    Priority 1  Same ASIN
    Priority 2  ASIN extracted from an Amazon URL matches
    Priority 3  Exact normalized title match
    Priority 4  Same brand AND same parsed model

If none match: DO NOT MERGE. It is better to have missing pricing than wrong
product data.

The matcher is source agnostic. It matches a master catalog product against a
commerce feed record from Amazon, Flipkart, Myntra, Ajio, Reliance Digital or
any future source, as long as that record exposes asin / url / title / brand.
"""

import re
from typing import Dict, List, Optional, Tuple

# ASIN embedded in an Amazon style URL, e.g. /dp/B0XXXXXXXX or ?asin=...
_ASIN_IN_URL = re.compile(r"(?:/dp/|/gp/product/|[?&]asin=)([A-Z0-9]{10})", re.IGNORECASE)
# A bare 10 char ASIN token as a last resort within a URL path.
_ASIN_BARE = re.compile(r"\b([A-Z0-9]{10})\b")
# A valid standalone ASIN value (already extracted, not a URL).
_ASIN_VALUE = re.compile(r"^[A-Z0-9]{10}$", re.IGNORECASE)

# Generic tokens stripped before exact title comparison. These are noise that
# legitimately varies between the catalog and a commerce listing for the SAME
# product (certifications, marketing copy, generic category words). Removing
# them makes the *exact* comparison robust WITHOUT resorting to fuzziness.
_TITLE_NOISE = (
    "isi certified", "isi", "dot certified", "dot", "ece", "bis", "certified",
    "with", "for", "and", "the", "premium", "original", "genuine",
    "full face", "open face", "flip up", "modular", "half face",
    "motorcycle", "motorbike", "helmet", "bike", "scooter",
)


def extract_asin(value: Optional[str]) -> str:
    """Extract a 10 character Amazon ASIN from a raw ASIN or an Amazon URL.

    Returns an uppercase ASIN, or '' if none can be found. Never guesses.
    """
    if not value:
        return ""
    value = value.strip()
    if _ASIN_VALUE.match(value):
        return value.upper()
    m = _ASIN_IN_URL.search(value)
    if m:
        return m.group(1).upper()
    m = _ASIN_BARE.search(value)
    if m:
        return m.group(1).upper()
    return ""


def normalized_title(title: Optional[str]) -> str:
    """Return a title normalized for EXACT comparison only.

    Lowercases, removes generic noise tokens, keeps alphanumerics + spaces,
    collapses whitespace. This is deterministic normalization, NOT similarity.
    Two products match on title only if their normalized forms are identical.
    """
    if not title:
        return ""
    t = title.lower()
    for token in _TITLE_NOISE:
        t = re.sub(rf"\b{re.escape(token)}\b", " ", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def parse_model(title: Optional[str], brand: Optional[str] = None) -> str:
    """Extract a product model token used for brand+model matching.

    Removes the brand name (if given) from the normalized title so the
    remaining tokens represent the distinctive model. Deterministic only.
    """
    t = normalized_title(title)
    if brand:
        b = brand.strip().lower()
        if b:
            t = re.sub(rf"\b{re.escape(b)}\b", " ", t)
            t = re.sub(r"\s+", " ", t).strip()
    return t


# ----- Feed record adapters -----
# Commerce feeds have wildly different shapes. Adapters normalize a raw feed
# record into a flat dict with the keys the matcher understands:
#   asin, url, title, brand

def adapt_amazon_deal(deal: dict) -> dict:
    """Normalize an Amazon PA-API style deal record for matching + enrichment."""
    item_info = deal.get("itemInfo", {}) or {}
    title = (item_info.get("title", {}) or {}).get("displayValue", "") or deal.get("title", "")
    return {
        "asin": (deal.get("asin") or "").strip(),
        "url": deal.get("detailPageURL") or deal.get("url") or "",
        "title": title,
        "brand": (deal.get("brand") or "").strip(),
        "_raw": deal,
    }


class ProductMatcher:
    """Indexes commerce feed records and matches catalog products against them.

    Build once per feed, then call match() for each catalog product. All four
    lookup indexes are exact-match hash lookups (O(1)); the matcher scales to
    tens of thousands of products without degradation.
    """

    def __init__(self, feed_records: List[dict]):
        self._by_asin: Dict[str, dict] = {}
        self._by_title: Dict[str, dict] = {}
        self._by_brand_model: Dict[Tuple[str, str], dict] = {}

        for record in feed_records:
            asin = extract_asin(record.get("asin")) or extract_asin(record.get("url"))
            if asin:
                self._by_asin.setdefault(asin, record)

            ntitle = normalized_title(record.get("title"))
            if ntitle:
                self._by_title.setdefault(ntitle, record)

            brand = (record.get("brand") or "").strip().lower()
            model = parse_model(record.get("title"), record.get("brand"))
            if brand and model:
                self._by_brand_model.setdefault((brand, model), record)

    def match(self, product: dict) -> Tuple[Optional[dict], Optional[str]]:
        """Return (feed_record, match_type) or (None, None).

        match_type is one of: 'asin', 'url_asin', 'title', 'brand_model'.
        Only 'asin' / 'url_asin' are strong enough to update price; the caller
        decides what each match strength is allowed to enrich.
        """
        # Priority 1: same ASIN (from the product's own asin field)
        asin = extract_asin(product.get("asin"))
        if asin and asin in self._by_asin:
            return self._by_asin[asin], "asin"

        # Priority 2: ASIN extracted from an existing Amazon URL
        for field in ("affiliate_url", "amazon_url", "url"):
            url_asin = extract_asin(product.get(field))
            if url_asin and url_asin in self._by_asin:
                return self._by_asin[url_asin], "url_asin"

        # Priority 3: exact normalized title
        ntitle = normalized_title(product.get("title"))
        if ntitle and ntitle in self._by_title:
            return self._by_title[ntitle], "title"

        # Priority 4: same brand AND same parsed model
        brand = (product.get("brand") or "").strip().lower()
        model = parse_model(product.get("title"), product.get("brand"))
        if brand and model and (brand, model) in self._by_brand_model:
            return self._by_brand_model[(brand, model)], "brand_model"

        # No confident match. DO NOT MERGE.
        return None, None
