"""
AmazonSearchService — keyword product discovery for the Control Center.

Searches Amazon by keyword (NOT by URL) through the CreatorsAPI SDK and
returns import-ready flat product dicts in the same format that
DatabaseWriter.save_product() consumes.

Usage:
    svc = AmazonSearchService()
    result = svc.search("motorcycle helmet", item_count=20)

Credentials resolve through amazon_credentials — the single source of truth
shared with bike.py: explicit args, standard env vars, or built-in defaults.
An injected `api` object may be supplied for tests.
"""

import math
import os
import re
from typing import Any, Dict, List, Optional

from amazon_credentials import get_credentials, get_partner_tag
from product_library import category_display, generate_slug, infer_category_from_title

from creatorsapi_python_sdk.api.default_api import DefaultApi
from creatorsapi_python_sdk.api_client import ApiClient
from creatorsapi_python_sdk.models import SearchItemsRequestContent, SearchItemsResource
from creatorsapi_python_sdk.models.search_items_response_content import (
    SearchItemsResponseContent,
)

MARKETPLACE = os.getenv("AMAZON_MARKETPLACE", "www.amazon.in")
SEARCH_INDEX = "Automotive"
DEFAULT_ITEM_COUNT = 20


class AmazonSearchError(Exception):
    """Raised when Amazon search cannot be performed (credentials, API, etc.)."""


_RESOURCES = [
    SearchItemsResource.ITEM_INFO_DOT_TITLE,
    SearchItemsResource.ITEM_INFO_DOT_BY_LINE_INFO,
    SearchItemsResource.IMAGES_DOT_PRIMARY_DOT_SMALL,
    SearchItemsResource.IMAGES_DOT_PRIMARY_DOT_MEDIUM,
    SearchItemsResource.IMAGES_DOT_PRIMARY_DOT_LARGE,
    SearchItemsResource.IMAGES_DOT_PRIMARY_DOT_HIGH_RES,
    SearchItemsResource.OFFERS_V2_DOT_LISTINGS_DOT_PRICE,
    SearchItemsResource.OFFERS_V2_DOT_LISTINGS_DOT_AVAILABILITY,
    SearchItemsResource.OFFERS_V2_DOT_LISTINGS_DOT_IS_BUY_BOX_WINNER,
    SearchItemsResource.OFFERS_V2_DOT_LISTINGS_DOT_DEAL_DETAILS,
    SearchItemsResource.CUSTOMER_REVIEWS_DOT_COUNT,
    SearchItemsResource.CUSTOMER_REVIEWS_DOT_STAR_RATING,
]

_IMAGE_SIZES = ("large", "medium", "small", "hiRes")

MIN_DISPLAY_COUNT = 10
RATING_FALLBACK_FLOOR = 3.8

# Tokens that do not help tell two similar products apart.
_DUP_STOPWORDS = {
    "the", "a", "an", "and", "with", "for", "of", "to", "in", "on", "motorcycle",
    "bike", "scooter", "moto", "universal", "compatible", "style", "india", "isi",
    "certified", "men", "women", "unisex", "kids", "adult", "black", "white",
    "red", "blue", "green", "grey", "gray", "silver", "gold",
}


def _quality_score(p: Dict[str, Any]) -> float:
    """Composite quality score for ranking Amazon search results.

    score = (rating * 60) + (log10(review_count) * 20)
          + (discount_percent * 0.2) + (is_buy_box_winner ? 10 : 0)
    """
    rating = float(p.get("rating") or 0)
    reviews = max(int(p.get("review_count") or 0), 1)
    discount = float(p.get("discount") or 0)
    bonus = 10 if p.get("is_buy_box_winner") else 0
    return round(rating * 60 + math.log10(reviews) * 20 + discount * 0.2 + bonus, 3)


def _title_fingerprint(title: str) -> str:
    """Normalise a title into a stable 'model' fingerprint for deduping.

    Strips parenthetical variants (colour / size / qty), punctuation and
    stopwords, keeping the first few significant tokens.
    """
    t = (title or "").lower()
    t = re.sub(r"\(.*?\)", " ", t)          # (Black, Size:M), pack contents, etc.
    t = re.sub(r"\b\d+\s*(ml|l|cc|pcs|pack|pk)\b", " ", t)  # 150ml / 2 pack
    t = re.sub(r"[^a-z0-9]+", " ", t)
    tokens = [w for w in t.split() if w not in _DUP_STOPWORDS and not w.isdigit()]
    return " ".join(tokens[:6])


def _image_key(url: str) -> str:
    """Stable key for an image URL (last path segment, minus extension)."""
    if not url:
        return ""
    seg = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"\.[a-z]+$", "", seg.lower())


def _dedupe(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop near-duplicate products, keeping the highest-scoring version.

    Duplicate signals: same brand + normalised title fingerprint, or the same
    Amazon image key for the same brand.
    """
    ordered = sorted(products, key=lambda p: p.get("score") or 0, reverse=True)
    kept = []
    seen_fp = set()
    seen_img = set()
    for p in ordered:
        brand = (p.get("brand") or "").lower()
        fp = (brand, _title_fingerprint(p.get("title") or ""))
        if fp in seen_fp:
            continue
        imgk = (brand, _image_key(p.get("image") or "")) if p.get("image") else None
        if imgk and imgk in seen_img:
            continue
        seen_fp.add(fp)
        if imgk:
            seen_img.add(imgk)
        kept.append(p)
    return kept


def _compute_badges(products: List[Dict[str, Any]]) -> None:
    """Attach quality badges to each product in-place (based on the curated set)."""
    if not products:
        return
    rated = [p for p in products if (p.get("rating") or 0) > 0]
    if rated:
        best_rating = max(p["rating"] for p in rated)
        top_rated = max(
            (p for p in rated if p["rating"] == best_rating),
            key=lambda p: p.get("review_count") or 0,
        )
    else:
        top_rated = None
    top_popular = max(products, key=lambda p: p.get("review_count") or 0)
    prices = sorted(p.get("price") for p in products if p.get("price"))
    median_price = prices[len(prices) // 2] if prices else None
    review_counts = sorted(p.get("review_count") or 0 for p in products)
    median_reviews = review_counts[len(review_counts) // 2] if review_counts else 0

    for p in products:
        badges = []
        rating = p.get("rating") or 0
        reviews = p.get("review_count") or 0
        if top_popular and p is top_popular and reviews >= 50:
            badges.append({"emoji": "🔥", "label": "Popular", "cls": "pop"})
        if top_rated and p is top_rated and rating >= 4.0:
            badges.append({"emoji": "🏆", "label": "Best Rated", "cls": "best"})
        if p.get("is_buy_box_winner") and rating >= 4.0 and reviews >= 30:
            badges.append({"emoji": "⭐", "label": "Amazon Choice", "cls": "choice"})
        if rating >= 4.0 and reviews >= 200:
            badges.append({"emoji": "🚀", "label": "Trending", "cls": "trend"})
        if rating >= 4.0 and median_price and p.get("price") and p["price"] >= median_price:
            badges.append({"emoji": "💎", "label": "Premium Choice", "cls": "premium"})
        p["badges"] = badges


def _sort_key(product: Dict[str, Any], sort: str):
    if sort == "price_asc":
        price = product.get("price")
        return (0, price) if price is not None else (1, 0)
    if sort == "price_desc":
        price = product.get("price")
        return -(price if price is not None else 0)
    if sort == "reviews":
        return -(product.get("review_count") or 0)
    return -(product.get("score") or 0)


def _extract_title(raw: Dict[str, Any]) -> str:
    title = (raw.get("itemInfo") or {}).get("title") or {}
    if isinstance(title, dict):
        return title.get("displayValue") or ""
    return title or ""


def _extract_brand(raw: Dict[str, Any]) -> str:
    by_line = (raw.get("itemInfo") or {}).get("byLineInfo") or {}
    brand = by_line.get("brand") or {}
    if isinstance(brand, dict):
        return brand.get("displayValue") or ""
    return brand or ""


def _extract_listing(raw: Dict[str, Any]) -> Optional[dict]:
    listings = (raw.get("offersV2") or {}).get("listings") or []
    return listings[0] if listings else None


def _extract_price(raw: Dict[str, Any]) -> Optional[dict]:
    listing = _extract_listing(raw)
    if not listing:
        return None
    return listing.get("price") or None


def _amount(money: Any) -> Optional[float]:
    if isinstance(money, dict):
        return money.get("amount")
    return money


def _extract_image_url(raw: Dict[str, Any]) -> str:
    primary = (raw.get("images") or {}).get("primary") or {}
    for size in _IMAGE_SIZES:
        size_dict = primary.get(size)
        if isinstance(size_dict, dict):
            url = size_dict.get("url")
            if url:
                return url
    return ""


def _extract_rating(raw: Dict[str, Any]) -> Optional[float]:
    reviews = raw.get("customerReviews") or {}
    rating = reviews.get("starRating")
    if rating is None:
        return None
    try:
        return float(rating)
    except (TypeError, ValueError):
        return None


def _extract_review_count(raw: Dict[str, Any]) -> Optional[int]:
    reviews = raw.get("customerReviews") or {}
    count = reviews.get("count")
    if count is None:
        return None
    try:
        return int(count)
    except (TypeError, ValueError):
        return None


def _extract_availability(raw: Dict[str, Any]) -> str:
    listing = _extract_listing(raw)
    if not listing:
        return ""
    availability = listing.get("availability") or {}
    if isinstance(availability, dict):
        return availability.get("type") or availability.get("message") or ""
    return availability or ""


class AmazonSearchService:
    """Search Amazon by keyword and return import-ready flat product dicts.

    The `api` argument allows injecting a fake DefaultApi for tests.
    """

    def __init__(
        self,
        marketplace: str = MARKETPLACE,
        partner_tag: Optional[str] = None,
        credential_id: Optional[str] = None,
        credential_secret: Optional[str] = None,
        api: Any = None,
        item_count: int = DEFAULT_ITEM_COUNT,
    ):
        self.marketplace = marketplace
        self.partner_tag = get_partner_tag(partner_tag)
        self.credential_id = credential_id
        self.credential_secret = credential_secret
        self._api = api
        self.item_count = item_count

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        keyword: str,
        item_count: Optional[int] = None,
        page: int = 1,
        known_asins: Optional[set] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        min_rating: float = 0.0,
        min_reviews: int = 0,
        min_discount: int = 0,
        sort: str = "quality",
        dedupe: bool = True,
    ) -> Dict[str, Any]:
        """Search Amazon by keyword with optional quality filters.

        Quality filtering, ranking and de-duplication happen server-side so the
        Control Center receives a curated, import-ready list rather than raw
        Amazon ordering.

        Filters are parameterised (``min_rating`` / ``min_reviews`` /
        ``min_discount`` / ``sort``) so the frontend can add more later without
        backend changes.  ``sort`` supports: ``quality`` (default), ``reviews``,
        ``price_asc``, ``price_desc``.

        Smart fallback: when fewer than ``MIN_DISPLAY_COUNT`` products satisfy a
        rating filter, the rating threshold is relaxed 0.1 at a time down to
        ``RATING_FALLBACK_FLOOR`` (3.8) so the grid never looks empty.  The
        floor is never crossed unless the user explicitly asked for a lower one.

        Returns:
            {
                "keyword": str,
                "page": int,
                "count": int,
                "total": int,           # Amazon totalResultCount (may be None)
                "categories": [...],
                "brands": [...],
                "filters": {...},       # filters actually applied
                "fallback": bool,       # True when rating was auto-relaxed
                "results": [flat product dicts, each with score + badges],
            }
        """
        if not keyword or not keyword.strip():
            raise AmazonSearchError("Search keyword is required")

        api = self.get_api()
        req = SearchItemsRequestContent(
            partner_tag=self.partner_tag,
            keywords=keyword.strip(),
            search_index=SEARCH_INDEX,
            item_count=item_count or self.item_count,
            resources=_RESOURCES,
            item_page=page,
        )

        try:
            resp = api.search_items(
                x_marketplace=self.marketplace,
                search_items_request_content=req,
            )
        except AmazonSearchError:
            raise
        except Exception as exc:  # SDK ApiException or network errors
            raise AmazonSearchError(f"Amazon search failed: {exc}") from exc

        raw = self._to_dict(resp)
        search_result = raw.get("searchResult") or {}
        total = search_result.get("totalResultCount")
        items = search_result.get("items") or []
        flat_items = [
            self._raw_to_flat(item)
            for item in items
            if item.get("asin")
        ]

        # Best-effort enrichment: the CreatorsAPI search endpoint often omits
        # review data, so batch-fetch it via get_items when the API supports it.
        reviews = self._enrich_reviews([p["asin"] for p in flat_items])
        if reviews:
            for p in flat_items:
                info = reviews.get(p["asin"])
                if not info:
                    continue
                if info.get("rating") is not None:
                    p["rating"] = info["rating"]
                if info.get("review_count") is not None:
                    p["review_count"] = info["review_count"]
                    p["reviews"] = info["review_count"]

        categories = sorted({p.get("category") for p in flat_items if p.get("category")})
        brands = sorted({p.get("brand") for p in flat_items if p.get("brand")})

        # Pool filtered by category/brand only (facets stay independent).
        pool = [
            p for p in flat_items
            if self._matches_filters(p, category=category, brand=brand)
        ]

        min_rating = float(min_rating or 0)
        min_reviews = int(min_reviews or 0)
        min_discount = int(min_discount or 0)
        sort = sort or "quality"

        def select(rating_threshold: float) -> List[Dict[str, Any]]:
            selected = [
                p for p in pool
                if self._matches_quality(p, rating_threshold, min_reviews, min_discount)
            ]
            for p in selected:
                p["score"] = _quality_score(p)
            if dedupe and len(selected) > 1:
                selected = _dedupe(selected)
            selected.sort(key=lambda p: _sort_key(p, sort))
            return selected

        # If the source returned no rating/review data at all, the rating and
        # review thresholds cannot be satisfied.  Fall back to a curated list
        # ranked by the available signals (discount, buy-box) instead of an
        # empty grid, and flag it so the UI can explain.
        pool_has_ratings = any((p.get("rating") or 0) > 0 for p in pool)
        no_rating_data = False
        fallback = False
        used_rating = min_rating

        if (min_rating > 0 or min_reviews > 0) and not pool_has_ratings:
            no_rating_data = True
            used_rating = 0.0
            results = [
                p for p in pool
                if not min_discount or (p.get("discount") or 0) >= min_discount
            ]
            for p in results:
                p["score"] = _quality_score(p)
            if dedupe and len(results) > 1:
                results = _dedupe(results)
            results.sort(key=lambda p: _sort_key(p, sort))
        else:
            results = select(min_rating)
            if min_rating > RATING_FALLBACK_FLOOR and len(results) < MIN_DISPLAY_COUNT:
                rating = min_rating
                while rating > RATING_FALLBACK_FLOOR and len(results) < MIN_DISPLAY_COUNT:
                    rating = round(max(RATING_FALLBACK_FLOOR, rating - 0.1), 1)
                    results = select(rating)
                    fallback = True
                used_rating = rating

        _compute_badges(results)

        if known_asins:
            for result in results:
                result["in_library"] = result["asin"] in known_asins

        return {
            "keyword": keyword.strip(),
            "page": page,
            "count": len(results),
            "total": total if total is not None else len(results),
            "categories": categories,
            "brands": brands,
            "filters": {
                "rating": used_rating,
                "reviews": min_reviews,
                "discount": min_discount,
                "sort": sort,
            },
            "fallback": fallback,
            "no_rating_data": no_rating_data,
            "results": results,
        }

    def _enrich_reviews(self, asins: List[str]) -> Dict[str, Any]:
        """Batch-fetch review data for ASINs via the get_items endpoint.

        Best-effort: returns {} on any error or when the provider does not
        expose review data.  Only the first batch is checked — if it yields no
        review data the remaining batches are skipped to save API calls.
        """
        if not asins or not hasattr(self.get_api(), "get_items"):
            return {}
        try:
            from creatorsapi_python_sdk.models import (
                GetItemsRequestContent,
                GetItemsResource,
            )
        except Exception:
            return {}

        api = self.get_api()
        resources = [
            GetItemsResource.CUSTOMER_REVIEWS_DOT_COUNT,
            GetItemsResource.CUSTOMER_REVIEWS_DOT_STAR_RATING,
        ]

        def fetch(batch: List[str]) -> List[Dict[str, Any]]:
            req = GetItemsRequestContent(
                partner_tag=self.partner_tag,
                item_ids=batch,
                resources=resources,
            )
            resp = api.get_items(
                x_marketplace=self.marketplace,
                get_items_request_content=req,
            )
            data = self._to_dict(resp)
            return (data.get("itemsResult") or {}).get("items") or []

        def parse(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            reviews_raw = item.get("customerReviews") or {}
            rating = reviews_raw.get("starRating") if isinstance(reviews_raw, dict) else None
            count = reviews_raw.get("count") if isinstance(reviews_raw, dict) else None
            try:
                rating = float(rating) if rating is not None else None
            except (TypeError, ValueError):
                rating = None
            try:
                count = int(count) if count is not None else None
            except (TypeError, ValueError):
                count = None
            if rating is None and count is None:
                return None
            return {"asin": item.get("asin"), "rating": rating, "review_count": count}

        enriched: Dict[str, Any] = {}
        try:
            first = fetch(asins[:10])
        except Exception:
            return {}
        found = 0
        for item in first:
            parsed = parse(item)
            if parsed and parsed.get("asin"):
                enriched[parsed["asin"]] = parsed
                found += 1
        if not found:
            return enriched
        for start in range(10, len(asins), 10):
            try:
                for item in fetch(asins[start:start + 10]):
                    parsed = parse(item)
                    if parsed and parsed.get("asin"):
                        enriched[parsed["asin"]] = parsed
            except Exception:
                break
        return enriched

    def get_api(self) -> Any:
        """Return the CreatorsAPI DefaultApi (builds it lazily if needed)."""
        if self._api is not None:
            return self._api
        try:
            cid, csecret = get_credentials(self.credential_id, self.credential_secret)
        except RuntimeError as exc:
            raise AmazonSearchError(str(exc)) from exc
        client = ApiClient(
            credential_id=cid,
            credential_secret=csecret,
            version="3.2",
        )
        self._api = DefaultApi(client)
        return self._api

    # ------------------------------------------------------------------
    # Flat conversion
    # ------------------------------------------------------------------

    def _raw_to_flat(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a CreatorsAPI raw item dict to an import-ready flat dict."""
        asin = (raw.get("asin") or "").strip().upper()
        title = _extract_title(raw)
        brand = _extract_brand(raw)
        price = _extract_price(raw)

        money = price.get("money") if price else None
        current = _amount(money)
        savings = price.get("savings") or {} if price else {}
        mrp = None
        discount = None
        if price:
            saving_basis = price.get("savingBasis") or {}
            mrp = _amount(saving_basis.get("money"))
            pct = savings.get("percentage")
            if pct is not None:
                try:
                    discount = int(round(float(pct)))
                except (TypeError, ValueError):
                    discount = None
            if current is not None:
                current = _maybe_int(current)
            if mrp is not None:
                mrp = _maybe_int(mrp)

        rating = _extract_rating(raw)
        review_count = _extract_review_count(raw)

        image_url = _extract_image_url(raw)
        affiliate_url = raw.get("detailPageURL") or self._build_affiliate_url(asin)

        listing = _extract_listing(raw)
        is_buy_box_winner = bool((listing or {}).get("isBuyBoxWinner"))
        deal_badge = ""
        if listing:
            deal = listing.get("dealDetails") or {}
            deal_badge = (deal.get("badge") or "") if isinstance(deal, dict) else ""

        canonical_category = infer_category_from_title(title)
        slug = generate_slug(title) or f"product-{asin.lower()}"

        return {
            "asin": asin,
            "slug": slug,
            "title": title,
            "brand": brand,
            "category": category_display(canonical_category) if canonical_category else "",
            "type": "",
            "status": "draft",
            "price": current,
            "mrp": mrp,
            "discount": discount,
            "rating": rating or 0,
            "review_count": review_count or 0,
            "reviews": review_count or 0,
            "availability": _extract_availability(raw),
            "affiliate_url": affiliate_url,
            "image": image_url,
            "amazon_image_url": image_url,
            "is_buy_box_winner": is_buy_box_winner,
            "deal_badge": deal_badge,
            "score": 0.0,
            "badges": [],
            "last_updated": None,
            "editor_rating": 0,
            "editorial_verdict": "",
            "pros": [],
            "cons": [],
            "features": [],
            "fitment_notes": "",
            "recommended_for": [],
            "editorial_notes": "",
            "editors_choice": False,
            "override_rank": 0,
            "best_for": "",
            "verdict": "",
            "compatible_bikes": ["*"],
        }

    def _build_affiliate_url(self, asin: str) -> str:
        if not asin:
            return ""
        domain = self.marketplace
        if domain.startswith("http://") or domain.startswith("https://"):
            domain = domain.split("//", 1)[-1]
        domain = domain.split("/")[0]
        return f"https://{domain}/dp/{asin}/?tag={self.partner_tag}"

    def _matches_quality(self, flat: Dict[str, Any],
                         min_rating: float,
                         min_reviews: int,
                         min_discount: int) -> bool:
        """Apply rating / review-count / discount thresholds to a product."""
        if min_rating and (flat.get("rating") or 0) < min_rating:
            return False
        if min_reviews and (flat.get("review_count") or 0) < min_reviews:
            return False
        if min_discount and (flat.get("discount") or 0) < min_discount:
            return False
        return True

    def _matches_filters(self, flat: Dict[str, Any],
                         category: Optional[str] = None,
                         brand: Optional[str] = None) -> bool:
        """Apply optional category/brand filters to a flat product dict.

        Category matches the display name or the inferred canonical category.
        Brand matches the exact (case-insensitive) brand name.
        """
        if category:
            wanted = category.strip().lower().replace("-", "_")
            display = (flat.get("category") or "").lower()
            canonical = infer_category_from_title(flat.get("title") or "").lower()
            if display != wanted and canonical != wanted:
                return False
        if brand:
            wanted = brand.strip().lower()
            if (flat.get("brand") or "").lower() != wanted:
                return False
        return True

    @staticmethod
    def _to_dict(resp: Any) -> Dict[str, Any]:
        if isinstance(resp, SearchItemsResponseContent):
            return resp.to_dict()
        if hasattr(resp, "to_dict"):
            return resp.to_dict()
        return resp or {}


def _maybe_int(value: float) -> Any:
    """Convert whole floats to int (matches flat-product JSON behavior)."""
    if isinstance(value, float) and value == int(value):
        return int(value)
    return value
