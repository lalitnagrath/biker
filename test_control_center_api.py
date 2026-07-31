"""
Tests for the Control Center API endpoints added in Phase 8.1:
  - GET  /api/amazon/search
  - POST /api/import

The Amazon/import services are faked so no network or DB writes occur.
"""

import os
import sys
import types
from unittest.mock import MagicMock

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Stub the CreatorsAPI SDK before importing the server
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
_resp_mod.SearchItemsResponseContent = MagicMock
_api_pkg.default_api = _default_api
_models_pkg.search_items_response_content = _resp_mod
sys.modules["creatorsapi_python_sdk"] = _sdk_pkg
sys.modules["creatorsapi_python_sdk.api"] = _api_pkg
sys.modules["creatorsapi_python_sdk.api.default_api"] = _default_api
sys.modules["creatorsapi_python_sdk.api_client"] = _api_client
sys.modules["creatorsapi_python_sdk.models"] = _models_pkg
sys.modules["creatorsapi_python_sdk.models.search_items_response_content"] = _resp_mod

import editorial.server as server
from db.amazon_search_service import AmazonSearchError
from fastapi.testclient import TestClient


class FakeSearchService:
    def __init__(self, results=None, error=None):
        self.results = results
        self.error = error
        self.last_kwargs = None

    def search(self, keyword, item_count=20, page=1, known_asins=None,
               category=None, brand=None):
        self.last_kwargs = {
            "keyword": keyword,
            "item_count": item_count,
            "page": page,
            "known_asins": known_asins,
            "category": category,
            "brand": brand,
        }
        if self.error:
            raise self.error
        results = [
            {
                "asin": "B0API01",
                "title": "API Jacket",
                "brand": "API Brand",
                "category": "Jackets",
                "status": "draft",
                "price": 2499,
                "mrp": 3200,
                "discount": 22,
                "rating": 4.1,
                "review_count": 30,
                "affiliate_url": "https://www.amazon.in/dp/B0API01?tag=x",
                "image": "",
                "amazon_image_url": "",
                "compatible_bikes": ["*"],
                "in_library": "B0API01" in (known_asins or set()),
            },
            {
                "asin": "B0API02",
                "title": "Library Glove",
                "brand": "API Brand",
                "category": "Gloves",
                "status": "draft",
                "price": 899,
                "rating": 4.5,
                "affiliate_url": "https://www.amazon.in/dp/B0API02?tag=x",
                "image": "",
                "amazon_image_url": "",
                "compatible_bikes": ["*"],
                "in_library": "B0API02" in (known_asins or set()),
            },
        ]
        return {
            "keyword": keyword,
            "page": page,
            "count": len(results),
            "results": results,
        }


class FakeImportService:
    def __init__(self, report=None):
        self.report = report or {
            "submitted": 0,
            "imported": [],
            "skipped_existing": [],
            "failed": [],
            "images": {"downloaded": 0, "skipped": 0, "failed": 0},
        }
        self.last_args = None

    def existing_asins(self):
        return {"B0API02"}

    def import_products(self, products, download_images=True):
        self.last_args = {"products": products,
                          "download_images": download_images}
        return {
            "submitted": len(products),
            "imported": products,
            "skipped_existing": [],
            "failed": [],
            "images": {"downloaded": 2, "skipped": 0, "failed": 0},
        }


def _patch(monkeypatch, search=None, importer=None):
    monkeypatch.setattr(server, "AmazonSearchService",
                        lambda **kw: search or FakeSearchService())
    monkeypatch.setattr(server, "ProductImportService",
                        lambda **kw: importer or FakeImportService())


def _client():
    return TestClient(server.app)


# ------------------------------------------------------------------
# /api/amazon/search
# ------------------------------------------------------------------

def test_search_requires_keyword(monkeypatch):
    _patch(monkeypatch)
    resp = _client().get("/api/amazon/search")
    assert resp.status_code == 400
    assert "error" in resp.json()
    print("OK test_search_requires_keyword")


def test_search_returns_results_with_in_library(monkeypatch):
    fake = FakeSearchService()
    _patch(monkeypatch, search=fake)
    resp = _client().get("/api/amazon/search?keyword=jacket&item_count=10&page=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["keyword"] == "jacket"
    assert data["page"] == 1
    assert data["count"] == 2
    flags = {p["asin"]: p["in_library"] for p in data["results"]}
    assert flags == {"B0API01": False, "B0API02": True}
    assert fake.last_kwargs["item_count"] == 10
    assert fake.last_kwargs["known_asins"] == {"B0API02"}
    print("OK test_search_returns_results_with_in_library")


def test_search_returns_502_on_error(monkeypatch):
    _patch(monkeypatch, search=FakeSearchService(
        error=AmazonSearchError("Amazon search failed")))
    resp = _client().get("/api/amazon/search?keyword=helmet")
    assert resp.status_code == 502
    assert "error" in resp.json()
    print("OK test_search_returns_502_on_error")


def test_search_forwards_category_brand_and_pagination(monkeypatch):
    fake = FakeSearchService()
    _patch(monkeypatch, search=fake)
    resp = _client().get(
        "/api/amazon/search?keyword=helmet&category=Helmet&brand=Steelbird&page=3&item_count=10"
    )
    assert resp.status_code == 200
    assert fake.last_kwargs["category"] == "Helmet"
    assert fake.last_kwargs["brand"] == "Steelbird"
    assert fake.last_kwargs["page"] == 3
    assert fake.last_kwargs["item_count"] == 10
    print("OK test_search_forwards_category_brand_and_pagination")


# ------------------------------------------------------------------
# /api/import
# ------------------------------------------------------------------

def test_import_empty_body_400(monkeypatch):
    _patch(monkeypatch)
    resp = _client().post("/api/import", json={"products": []})
    assert resp.status_code == 400
    resp2 = _client().post("/api/import", json={})
    assert resp2.status_code == 400
    print("OK test_import_empty_body_400")


def test_import_returns_report(monkeypatch):
    fake = FakeImportService()
    _patch(monkeypatch, importer=fake)
    products = [{"asin": "B0API01", "title": "API Jacket"}]
    resp = _client().post(
        "/api/import",
        json={"products": products, "download_images": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["submitted"] == 1
    assert len(data["imported"]) == 1
    assert data["images"] == {"downloaded": 2, "skipped": 0, "failed": 0}
    assert fake.last_args["download_images"] is False
    assert fake.last_args["products"] == products
    print("OK test_import_returns_report")
