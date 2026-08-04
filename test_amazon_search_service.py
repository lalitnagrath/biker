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


class _GetItemsRequestContent:
    """Real minimal stand-in so item_ids/resources survive round-trip."""

    def __init__(self, **kwargs):
        self.item_ids = kwargs.get("item_ids", [])
        self.resources = kwargs.get("resources", [])


_models_pkg.GetItemsRequestContent = _GetItemsRequestContent
_models_pkg.GetItemsResource = MagicMock()
_enum_names = [
    "ITEM_INFO_DOT_TITLE",
    "ITEM_INFO_DOT_BY_LINE_INFO",
    "IMAGES_DOT_PRIMARY_DOT_SMALL",
    "IMAGES_DOT_PRIMARY_DOT_MEDIUM",
    "IMAGES_DOT_PRIMARY_DOT_LARGE",
    "IMAGES_DOT_PRIMARY_DOT_HIGH_RES",
    "OFFERS_V2_DOT_LISTINGS_DOT_PRICE",
    "OFFERS_V2_DOT_LISTINGS_DOT_AVAILABILITY",
    "OFFERS_V2_DOT_LISTINGS_DOT_IS_BUY_BOX_WINNER",
    "OFFERS_V2_DOT_LISTINGS_DOT_DEAL_DETAILS",
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
    svc = _make_service([
        _raw_item("B0RAW01", title="Steelbird Helmet",
                  image_url="https://m.media-amazon.com/images/I/1.jpg"),
        _raw_item("B0RAW02", title="Steelbird Riding Gloves",
                  image_url="https://m.media-amazon.com/images/I/2.jpg"),
    ])
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


# ------------------------------------------------------------------
# Quality curation: filters, scoring, dedupe, fallback, badges
# ------------------------------------------------------------------

_WORD_POOL = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf",
              "Hotel", "India", "Juliet", "Kilo", "Lima", "Mike", "November",
              "Oscar", "Papa", "Quebec", "Romeo", "Sierra", "Tango", "Uniform",
              "Victor", "Whiskey", "Xray", "Yankee", "Zulu", "Atlas", "Beacon",
              "Comet", "Drift", "Ember", "Falcon", "Glide", "Harbor", "Ivy",
              "Jaguar", "Kite", "Lumen", "Mosaic", "Nimbus", "Orbit", "Pulse",
              "Quartz", "Raven", "Sable", "Talon", "Umbra", "Voyage", "Willow",
              "Zephyr"]


def _items_rating(rating, count, prefix="Item"):
    return [_raw_item(f"B0R{i:04d}",
                      title=f"{prefix} {_WORD_POOL[i]}",
                      rating=rating,
                      image_url=f"https://m.media-amazon.com/images/I/{prefix}{i}.jpg")
            for i in range(count)]


def _quality_items(count, rating=4.1, reviews=60, discount=25):
    return [_raw_item(f"B0Q{i:04d}",
                      title=f"Quality {_WORD_POOL[i]}",
                      rating=rating,
                      review_count=reviews,
                      discount_pct=discount,
                      image_url=f"https://m.media-amazon.com/images/I/q{i}.jpg")
            for i in range(count)]


def test_search_min_rating_filter():
    items = _items_rating(4.2, 10) + _items_rating(3.5, 3)
    result = _make_service(items).search("helmet", min_rating=4.0, min_reviews=0)
    assert result["count"] == 10
    assert all(p["rating"] >= 4.0 for p in result["results"])
    assert result["filters"]["rating"] == 4.0
    assert result["fallback"] is False
    print("OK test_search_min_rating_filter")


def test_search_min_reviews_filter():
    items = _quality_items(10, reviews=60) + _quality_items(3, reviews=10)
    result = _make_service(items).search("helmet", min_rating=0, min_reviews=30)
    assert result["count"] == 10
    assert all(p["review_count"] >= 30 for p in result["results"])
    print("OK test_search_min_reviews_filter")


def test_search_min_discount_filter():
    items = _quality_items(10, discount=25) + _quality_items(3, discount=5)
    result = _make_service(items).search("helmet", min_rating=0, min_discount=20)
    assert result["count"] == 10
    assert all(p["discount"] >= 20 for p in result["results"])
    print("OK test_search_min_discount_filter")


def test_search_quality_sort_desc():
    items = [
        _raw_item("B0R01", title="Low", rating=3.9, review_count=40),
        _raw_item("B0R02", title="High", rating=4.7, review_count=2000),
        _raw_item("B0R03", title="Mid", rating=4.3, review_count=300),
    ]
    for _ in range(12):  # pad so the fallback never kicks in
        items.append(_raw_item(f"B0P{len(items):04d}", title=f"Pad {len(items)}",
                               rating=4.0, review_count=100))
    result = _make_service(items).search("helmet", min_rating=0)
    scores = [p["score"] for p in result["results"]]
    assert scores == sorted(scores, reverse=True), scores
    # the highest-quality item must be first
    assert result["results"][0]["asin"] == "B0R02"
    print("OK test_search_quality_sort_desc")


def test_search_dedupe_keeps_highest_score():
    items = []
    for i in range(10):
        brand = "Steelbird" + _WORD_POOL[i]
        items.append(_raw_item(f"B0G{i:04d}", title="Flip Up Helmet",
                               brand=brand, rating=4.2, review_count=100))
        items.append(_raw_item(f"B0H{i:04d}", title="Flip Up Helmet",
                               brand=brand, rating=4.5, review_count=200))
    result = _make_service(items).search("helmet", min_rating=0)
    # every duplicate pair collapses to the better-rated version
    assert result["count"] == 10
    assert all(p["rating"] >= 4.4 for p in result["results"])
    print("OK test_search_dedupe_keeps_highest_score")


def test_search_smart_fallback_relaxes_rating():
    items = _items_rating(4.5, 5, prefix="Tier") + _items_rating(3.9, 9, prefix="Base")
    result = _make_service(items).search("helmet", min_rating=4.0, min_reviews=0)
    assert result["fallback"] is True
    assert result["filters"]["rating"] == 3.9
    assert result["count"] >= 10
    print("OK test_search_smart_fallback_relaxes_rating")


def test_search_no_fallback_below_floor_for_low_request():
    items = _items_rating(4.0, 5)
    result = _make_service(items).search("helmet", min_rating=3.5, min_reviews=0)
    assert result["fallback"] is False
    assert result["filters"]["rating"] == 3.5
    assert result["count"] == 5
    print("OK test_search_no_fallback_below_floor_for_low_request")


def test_search_badges_attached():
    items = [
        _raw_item("B0B01", title="Top Helmet", rating=4.8, review_count=5000,
                  discount_pct=30),
        _raw_item("B0B02", title="Meh Helmet", rating=3.8, review_count=5,
                  discount_pct=0),
    ]
    for _ in range(11):
        items.append(_raw_item(f"B0X{len(items):04d}", title=f"Fill {len(items)}",
                               rating=4.0, review_count=90))
    result = _make_service(items).search("helmet", min_rating=0)
    top = result["results"][0]
    assert top["asin"] == "B0B01"
    assert any(b["label"] == "Best Rated" for b in top["badges"])
    assert any(b["label"] == "Popular" for b in top["badges"])
    print("OK test_search_badges_attached")


def test_search_no_rating_data_falls_back_to_discount_ranking():
    # Source returns items with no review data at all (rating=0, count=0).
    items = [
        _raw_item("B0N01", title="A Helmet", brand="Steelbird", rating=0,
                  review_count=0, discount_pct=40),
        _raw_item("B0N02", title="B Helmet", brand="Vega", rating=0,
                  review_count=0, discount_pct=5),
        _raw_item("B0N03", title="C Helmet", brand="Studds", rating=0,
                  review_count=0, discount_pct=20),
    ]
    result = _make_service(items).search("helmet", min_rating=4.0, min_reviews=30)
    assert result["no_rating_data"] is True
    assert result["fallback"] is False
    assert result["filters"]["rating"] == 0.0
    # rating/review filters skipped; discount still enforced
    assert result["count"] == 3
    assert result["results"][0]["asin"] == "B0N01"  # highest discount first
    assert result["results"][-1]["asin"] == "B0N02"
    print("OK test_search_no_rating_data_falls_back_to_discount_ranking")


def test_search_no_rating_data_still_applies_discount_filter():
    items = [
        _raw_item("B0N10", title="A Helmet", rating=0, review_count=0,
                  discount_pct=40),
        _raw_item("B0N11", title="B Helmet", rating=0, review_count=0,
                  discount_pct=5),
    ]
    result = _make_service(items).search("helmet", min_rating=4.0,
                                         min_reviews=30, min_discount=15)
    assert result["no_rating_data"] is True
    assert [p["asin"] for p in result["results"]] == ["B0N10"]
    print("OK test_search_no_rating_data_still_applies_discount_filter")


class ReviewEnrichingFakeApi(FakeApi):
    """FakeApi variant whose search omits reviews but get_items supplies them."""

    def __init__(self, items, reviews, **kwargs):
        super().__init__(items, **kwargs)
        self.reviews = reviews

    def get_items(self, x_marketplace, get_items_request_content):
        self.calls.append({"marketplace": x_marketplace,
                           "request": get_items_request_content})
        ids = get_items_request_content.item_ids
        return {"itemsResult": {
            "items": [
                {"asin": asin, "customerReviews": {
                    "starRating": rating, "count": count}}
                for asin, (rating, count) in self.reviews.items()
                if asin in ids
            ]
        }}


def test_search_enriches_reviews_via_get_items():
    svc = AmazonSearchService(
        api=ReviewEnrichingFakeApi(
            [_raw_item("B0E01", title="A Helmet", rating=0, review_count=0),
             _raw_item("B0E02", title="B Helmet", rating=0, review_count=0)],
            reviews={"B0E01": (4.5, 210), "B0E02": (3.7, 12)},
        ),
        credential_id="cid",
        credential_secret="csec",
    )
    result = svc.search("helmet", min_rating=4.0, min_reviews=30)
    # ratings arrive via enrichment, so the normal path runs (no no_rating_data)
    assert result["no_rating_data"] is False
    assert result["count"] == 1
    item = result["results"][0]
    assert item["asin"] == "B0E01"
    assert item["rating"] == 4.5
    assert item["review_count"] == 210
    print("OK test_search_enriches_reviews_via_get_items")


def test_search_enrichment_failure_is_ignored():
    class FailingFakeApi(FakeApi):
        def get_items(self, x_marketplace, get_items_request_content):
            raise RuntimeError("boom")

    svc = AmazonSearchService(
        api=FailingFakeApi([_raw_item("B0F01", title="A Helmet",
                                      rating=0, review_count=0)]),
        credential_id="cid",
        credential_secret="csec",
    )
    result = svc.search("helmet", min_rating=4.0)
    assert result["no_rating_data"] is True
    assert result["count"] == 1  # still falls back gracefully
    print("OK test_search_enrichment_failure_is_ignored")
