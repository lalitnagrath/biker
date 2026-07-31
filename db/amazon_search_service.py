"""
AmazonSearchService — keyword product discovery for the Control Center.

Searches Amazon by keyword (NOT by URL) through the CreatorsAPI SDK and
returns import-ready flat product dicts in the same format that
DatabaseWriter.save_product() consumes.

Usage:
    svc = AmazonSearchService()
    result = svc.search("motorcycle helmet", item_count=20)

Credentials come from AMAZON_CREATOR_CREDENTIAL_ID /
AMAZON_CREATOR_CREDENTIAL_SECRET env vars, or may be passed explicitly.
An injected `api` object may be supplied for tests.
"""

import os
from typing import Any, Dict, List, Optional

from product_library import category_display, generate_slug, infer_category_from_title

from creatorsapi_python_sdk.api.default_api import DefaultApi
from creatorsapi_python_sdk.api_client import ApiClient
from creatorsapi_python_sdk.models import SearchItemsRequestContent, SearchItemsResource
from creatorsapi_python_sdk.models.search_items_response_content import (
    SearchItemsResponseContent,
)

MARKETPLACE = os.getenv("AMAZON_MARKETPLACE", "www.amazon.in")
PARTNER_TAG = os.getenv("AMAZON_PARTNER_TAG", "helpfulsurfer-21")
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
    SearchItemsResource.CUSTOMER_REVIEWS_DOT_COUNT,
    SearchItemsResource.CUSTOMER_REVIEWS_DOT_STAR_RATING,
]

_IMAGE_SIZES = ("large", "medium", "small", "hiRes")


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
        partner_tag: str = PARTNER_TAG,
        credential_id: Optional[str] = None,
        credential_secret: Optional[str] = None,
        api: Any = None,
        item_count: int = DEFAULT_ITEM_COUNT,
    ):
        self.marketplace = marketplace
        self.partner_tag = partner_tag
        self.credential_id = credential_id or os.getenv("AMAZON_CREATOR_CREDENTIAL_ID")
        self.credential_secret = credential_secret or os.getenv(
            "AMAZON_CREATOR_CREDENTIAL_SECRET"
        )
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
    ) -> Dict[str, Any]:
        """Search Amazon by keyword.

        Returns:
            {
                "keyword": str,
                "page": int,
                "count": int,
                "results": [flat product dicts],
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
            page=page,
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
        items = ((raw.get("searchResult") or {}).get("items")) or []
        results = [
            self._raw_to_flat(item)
            for item in items
            if item.get("asin")
        ]

        if known_asins:
            for result in results:
                result["in_library"] = result["asin"] in known_asins

        return {
            "keyword": keyword.strip(),
            "page": page,
            "count": len(results),
            "results": results,
        }

    def get_api(self) -> Any:
        """Return the CreatorsAPI DefaultApi (builds it lazily if needed)."""
        if self._api is not None:
            return self._api
        if not self.credential_id or not self.credential_secret:
            raise AmazonSearchError(
                "Amazon credentials not configured. Set "
                "AMAZON_CREATOR_CREDENTIAL_ID and "
                "AMAZON_CREATOR_CREDENTIAL_SECRET."
            )
        client = ApiClient(
            credential_id=self.credential_id,
            credential_secret=self.credential_secret,
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
