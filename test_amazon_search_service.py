"""
Tests for AmazonSearchService (Phase 8.1 - Amazon keyword discovery).

The CreatorsAPI SDK is stubbed out so tests are hermetic; the service is
exercised with an injected fake `api` object that returns canned responses.
"""

import os
import sys
import types
from unittest.mock import MagicMock

import amazon_credentials

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Stub the CreatorsAPI SDK before importing the service
_sdk_pkg = types.ModuleType("creatorsapi_python_sdk")
_api_pkg = types.ModuleType("creatorsapi_python_sdk.api")
_default_api = types.ModuleType("creatorsapi_python_sdk.api.default_api")
_api_client = types.ModuleType("creatorsapi_python_sdk.api_client")
_models_pkg = types.ModuleType("creatorsapi_python_sdk.models")
_resp_mod = types.ModuleType(
    "creatorsapi_python_sdk.models.search_items_response_content"
)

_default_api.DefaultApi = MagicMock
_api_client.ApiClient = MagicMock
_models_pkg.SearchItemsRequestContent = MagicMock
_models_pkg.SearchItemsResource = MagicMock()
_enum_names = [
    "ITEM_INFO_DOT_TITLE",
    "ITEM_INFO_DOT_BY_LINE_INFO",
    "IMAGES_DOT_PRIMARY_DOT_SMALL",
    "IMAGES_DOT_PRIMARY_DOT_MEDIUM",
    "IMAGES_DOT_PRIMARY_DOT_LARGE",
    "IMAGES_DOT_PRIMARY_DOT_HIGH_RES",
    "OFFERS_V2_DOT_LISTINGS_DOT_PRICE",
    "OFFERS_V2_DOT_LISTINGS_DOT_AVAILABILITY",
    "CUSTOMER_REVIEWS_DOT_COUNT",
    "CUSTOMER_REVIEWS_DOT_STAR_RATING",
]
for _name in _enum_names:
    setattr(_models_pkg.SearchItemsResource, _name, "Resource." + _name)
_resp_mod.SearchItemsResponseContent = MagicMock

_api_pkg.default_api = _default_api
_models_pkg.search_items_response_content = _resp_mod
sys.modules["creatorsapi_python_sdk"] = _sdk_pkg
sys.modules["creatorsapi_python_sdk.api"] = _api_pkg
sys.modules["creatorsapi_python_sdk.api.default_api"] = _default_api
sys.modules["creatorsapi_python_sdk.api_client"] = _api_client
sys.modules["creatorsapi_python_sdk.models"] = _models_pkg
sys.modules["creatorsapi_python_sdk.models.search_items_response_content"] = _resp_mod

from db.amazon_search_service import (
    AmazonSearchError,
    AmazonSearchService,
)


def _raw_item(asin="B0RAW01", title="Steelbird Helmet",
              brand="Steelbird", price=1488.0, mrp=1740.0,
              discount_pct=14, rating=4.3, review_count=120,
              image_url="https://m.media-amazon.com/images/I/71abc.jpg",
              has_detail_url=True):
    item = {
        "asin": asin,
        "detailPageURL": f"https://www.amazon.in/dp/{asin}?th=1" if has_detail_url else None,
        "images": {"primary": {"large": {"url": image_url}}},
        "itemInfo": {
            "title": {"displayValue": title},
            "byLineInfo": {"brand": {"displayValue": brand}},
        },
        "offersV2": {"listings": [{
            "price": {
                "money": {"amount": price},
                "savingBasis": {"money": {"amount": mrp}},
                "savings": {"percentage": discount_pct},
            },
            "availability": {"type": "Now", "message": "In Stock"},
        }]},
        "customerReviews": {"starRating": rating, "count": review_count},
    }
    return item


class FakeApi:
    """Canned CreatorsAPI stub."""

    def __init__(self, items, error=None, total=None):
        self.items = items
        self.error = error
        self.total = total
        self.calls = []

    def search_items(self, x_marketplace, search_items_request_content):
        self.calls.append({"marketplace": x_marketplace,
                           "request": search_items_request_content})
        if self.error:
            raise self.error
        result = {"items": self.items}
        if self.total is not None:
            result["totalResultCount"] = self.total
        return {"searchResult": result}


def _make_service(items, error=None, **kwargs):
    return AmazonSearchService(
        api=FakeApi(items, error=error),
        credential_id="cid",
        credential_secret="csec",
        **kwargs,
    )


# ------------------------------------------------------------------
# search()
# ------------------------------------------------------------------

def test_search_returns_flat_results():
    svc = _make_service([_raw_item()])
    result = svc.search("helmet")
    assert result["keyword"] == "helmet"
    assert result["page"] == 1
    assert result["count"] == 1
    item = result["results"][0]
    assert item["asin"] == "B0RAW01"
    assert item["status"] == "draft"
    assert item["price"] == 1488
    assert item["mrp"] == 1740
    assert item["discount"] == 14
    assert item["rating"] == 4.3
    assert item["review_count"] == 120
    assert item["availability"] == "Now"
    assert item["image"].endswith("71abc.jpg")
    assert item["compatible_bikes"] == ["*"]
    assert item["category"]
    print("OK test_search_returns_flat_results")


def test_search_flags_in_library():
    svc = _make_service([_raw_item("B0RAW01"), _raw_item("B0RAW02")])
    result = svc.search("helmet", known_asins={"B0RAW02"})
    flags = {p["asin"]: p["in_library"] for p in result["results"]}
    assert flags == {"B0RAW01": False, "B0RAW02": True}
    print("OK test_search_flags_in_library")


def test_search_missing_keyword_raises():
    svc = _make_service([])
    try:
        svc.search("   ")
        assert False, "expected AmazonSearchError"
    except AmazonSearchError:
        pass
    print("OK test_search_missing_keyword_raises")


def test_search_empty_results():
    svc = _make_service([])
    result = svc.search("nothing")
    assert result["count"] == 0
    assert result["results"] == []
    print("OK test_search_empty_results")


def test_search_api_error_wrapped():
    svc = _make_service([], error=RuntimeError("boom"))
    try:
        svc.search("helmet")
        assert False, "expected AmazonSearchError"
    except AmazonSearchError:
        pass
    print("OK test_search_api_error_wrapped")


def test_search_passes_request_args():
    fake = FakeApi([])
    svc = AmazonSearchService(api=fake, credential_id="cid",
                              credential_secret="csec", item_count=30)
    svc.search("riding jacket", page=2)
    call = fake.calls[0]
    assert call["marketplace"].startswith("www.amazon")
    assert call["request"].keywords == "riding jacket"
    assert call["request"].item_count == 30
    assert call["request"].item_page == 2
    print("OK test_search_passes_request_args")


# ------------------------------------------------------------------
# category / brand filters (Phase 8.2)
# ------------------------------------------------------------------

def test_search_category_filter():
    svc = _make_service([
        _raw_item("B0RAW01", title="Steelbird Helmet"),
        _raw_item("B0RAW02", title="Vega Gloves"),
        _raw_item("B0RAW03", title="Motul Chain Lube"),
    ])
    result = svc.search("gear", category="Helmet")
    assert [p["asin"] for p in result["results"]] == ["B0RAW01"]
    assert result["count"] == 1
    print("OK test_search_category_filter")


def test_search_category_filter_accepts_canonical():
    svc = _make_service([_raw_item("B0RAW01", title="Steelbird Helmet")])
    result = svc.search("gear", category="helmet")
    assert [p["asin"] for p in result["results"]] == ["B0RAW01"]
    print("OK test_search_category_filter_accepts_canonical")


def test_search_brand_filter():
    svc = _make_service([
        _raw_item("B0RAW01", title="Steelbird Helmet", brand="Steelbird"),
        _raw_item("B0RAW02", title="Vega Gloves", brand="Vega"),
    ])
    result = svc.search("gear", brand="vega")
    assert [p["asin"] for p in result["results"]] == ["B0RAW02"]
    print("OK test_search_brand_filter")


def test_search_filters_combine():
    svc = _make_service([
        _raw_item("B0RAW01", title="Steelbird Helmet", brand="Steelbird"),
        _raw_item("B0RAW02", title="Vega Helmet", brand="Vega"),
    ])
    result = svc.search("helmet", category="Helmet", brand="Vega")
    assert [p["asin"] for p in result["results"]] == ["B0RAW02"]
    print("OK test_search_filters_combine")


def test_search_filter_no_matches_keeps_facets():
    svc = _make_service([
        _raw_item("B0RAW01", title="Steelbird Helmet", brand="Steelbird"),
        _raw_item("B0RAW02", title="Vega Gloves", brand="Vega"),
    ])
    result = svc.search("gear", brand="nonexistent")
    assert result["count"] == 0
    assert result["results"] == []
    assert result["categories"] == ["Gloves", "Helmet"]
    assert result["brands"] == ["Steelbird", "Vega"]
    print("OK test_search_filter_no_matches_keeps_facets")


# ------------------------------------------------------------------
# pagination metadata (Phase 8.2)
# ------------------------------------------------------------------

def test_search_returns_total_and_facets():
    fake = FakeApi([
        _raw_item("B0RAW01", title="Steelbird Helmet", brand="Steelbird"),
        _raw_item("B0RAW02", title="Vega Gloves", brand="Vega"),
    ], total=42)
    svc = AmazonSearchService(api=fake, credential_id="cid",
                              credential_secret="csec")
    result = svc.search("gear")
    assert result["total"] == 42
    assert result["categories"] == ["Gloves", "Helmet"]
    assert result["brands"] == ["Steelbird", "Vega"]
    print("OK test_search_returns_total_and_facets")


def test_search_total_falls_back_to_count():
    svc = _make_service([_raw_item()])
    result = svc.search("helmet")
    assert result["total"] == result["count"] == 1
    print("OK test_search_total_falls_back_to_count")


# ------------------------------------------------------------------
# credentials / get_api()
# ------------------------------------------------------------------

def test_get_api_without_credentials_raises(monkeypatch):
    monkeypatch.delenv(amazon_credentials._CREDENTIAL_ID_ENV, raising=False)
    monkeypatch.delenv(amazon_credentials._CREDENTIAL_SECRET_ENV, raising=False)
    monkeypatch.setattr(amazon_credentials, "DEFAULT_CREDENTIAL_ID", None)
    monkeypatch.setattr(amazon_credentials, "DEFAULT_CREDENTIAL_SECRET", None)
    svc = AmazonSearchService(credential_id=None, credential_secret=None)
    try:
        svc.get_api()
        assert False, "expected AmazonSearchError"
    except AmazonSearchError:
        pass
    print("OK test_get_api_without_credentials_raises")


def test_get_api_uses_injected_api():
    fake = FakeApi([])
    svc = AmazonSearchService(api=fake)
    assert svc.get_api() is fake
    print("OK test_get_api_uses_injected_api")


# ------------------------------------------------------------------
# flat conversion details
# ------------------------------------------------------------------

def test_raw_to_flat_missing_price_and_rating():
    raw = _raw_item()
    raw["offersV2"] = {"listings": []}
    raw["customerReviews"] = {}
    raw["images"] = {"primary": {}}
    flat = _make_service([], )._raw_to_flat(raw)
    assert flat["price"] is None
    assert flat["mrp"] is None
    assert flat["discount"] is None
    assert flat["rating"] == 0
    assert flat["review_count"] == 0
    assert flat["image"] == ""
    assert flat["affiliate_url"].startswith("https://www.amazon.in/dp/B0RAW01")
    print("OK test_raw_to_flat_missing_price_and_rating")


def test_build_affiliate_url_fallback():
    svc = _make_service([])
    raw = _raw_item(has_detail_url=False)
    flat = svc._raw_to_flat(raw)
    assert "tag=" in flat["affiliate_url"]
    assert "B0RAW01" in flat["affiliate_url"]
    print("OK test_build_affiliate_url_fallback")


def test_raw_to_flat_bad_rating():
    raw = _raw_item()
    raw["customerReviews"] = {"starRating": "not-a-number", "count": "also-bad"}
    flat = _make_service([])._raw_to_flat(raw)
    assert flat["rating"] == 0
    assert flat["review_count"] == 0
    print("OK test_raw_to_flat_bad_rating")
