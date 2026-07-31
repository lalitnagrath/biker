"""
Tests for ProductImportService (Phase 8.1 - Amazon import into SQLite).

Uses a tmp SQLite file so the service's multiple connections share state.
Image downloads are stubbed.
"""

import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import db.import_service as mod
from db.import_service import ProductImportService


def _sample_product(asin="B0IMP01", title="Test Gloves", brand="Vega",
                    price=999, mrp=1299, image="https://ex.com/g.jpg"):
    return {
        "asin": asin,
        "slug": "test-gloves",
        "title": title,
        "brand": brand,
        "category": "Gloves",
        "status": "draft",
        "price": price,
        "mrp": mrp,
        "discount": 23,
        "rating": 4.2,
        "review_count": 55,
        "affiliate_url": f"https://www.amazon.in/dp/{asin}?tag=x",
        "image": image,
        "amazon_image_url": image,
        "compatible_bikes": ["*"],
    }


def _make_service(tmp_path, **kwargs):
    db_path = tmp_path / "test.db"
    return ProductImportService(
        db_url=f"sqlite:///{db_path}",
        image_dir=tmp_path / "img",
        **kwargs,
    )


def _db_rows(tmp_path, table):
    con = sqlite3.connect(tmp_path / "test.db")
    rows = con.execute(f"SELECT * FROM {table}").fetchall()
    con.close()
    return rows


def _stub_download(monkeypatch):
    def fake(url, dest):
        dest.write_bytes(b"fakedata")
        return True
    monkeypatch.setattr(mod, "_download_image", fake)


# ------------------------------------------------------------------
# Basic import
# ------------------------------------------------------------------

def test_import_new_product_as_draft(tmp_path):
    svc = _make_service(tmp_path)
    report = svc.import_products([_sample_product()], download_images=False)
    assert report["submitted"] == 1
    assert len(report["imported"]) == 1
    assert report["skipped_existing"] == []
    assert report["failed"] == []

    rows = _db_rows(tmp_path, "products")
    assert len(rows) == 1
    con = sqlite3.connect(tmp_path / "test.db")
    status, slug = con.execute("SELECT status, slug FROM products").fetchone()
    con.close()
    assert status == "draft"
    assert slug == "test-gloves"
    print("OK test_import_new_product_as_draft")


def test_import_skips_existing_asins_untouched(tmp_path):
    svc = _make_service(tmp_path)
    svc.import_products([_sample_product()], download_images=False)
    second = _sample_product(price=500)
    report = svc.import_products([second], download_images=False)
    assert report["imported"] == []
    assert len(report["skipped_existing"]) == 1
    assert report["skipped_existing"][0]["price"] == 500
    rows = _db_rows(tmp_path, "products")
    assert len(rows) == 1
    con = sqlite3.connect(tmp_path / "test.db")
    price = con.execute("SELECT price FROM products").fetchone()[0]
    con.close()
    assert price == 999  # original value never modified
    print("OK test_import_skips_existing_asins_untouched")


def test_import_report_structure(tmp_path):
    svc = _make_service(tmp_path)
    report = svc.import_products([_sample_product()], download_images=False)
    assert set(report) == {
        "submitted", "imported", "skipped_existing", "failed", "images"
    }
    assert set(report["images"]) == {"downloaded", "skipped", "failed"}
    print("OK test_import_report_structure")


def test_import_ignores_products_without_asin(tmp_path):
    svc = _make_service(tmp_path)
    report = svc.import_products(
        [{"title": "No ASIN", "price": 100}], download_images=False
    )
    assert report["imported"] == []
    assert report["failed"] == []
    assert report["submitted"] == 1
    print("OK test_import_ignores_products_without_asin")


# ------------------------------------------------------------------
# Images
# ------------------------------------------------------------------

def test_import_downloads_image_and_links(tmp_path, monkeypatch):
    _stub_download(monkeypatch)
    svc = _make_service(tmp_path)
    report = svc.import_products([_sample_product()], download_images=True)
    assert report["images"] == {"downloaded": 1, "skipped": 0, "failed": 0}
    dest = tmp_path / "img" / "test-gloves.jpg"
    assert dest.exists()
    assert dest.read_bytes() == b"fakedata"

    rows = _db_rows(tmp_path, "images")
    assert len(rows) == 1
    url, local_path = rows[0][2], rows[0][3]
    assert url == "static/images/products/test-gloves.jpg"
    assert local_path == url
    print("OK test_import_downloads_image_and_links")


def test_import_image_skipped_when_no_url(tmp_path):
    svc = _make_service(tmp_path)
    product = _sample_product(image="")
    report = svc.import_products([product], download_images=True)
    assert report["images"] == {"downloaded": 0, "skipped": 1, "failed": 0}
    assert len(report["imported"]) == 1
    print("OK test_import_image_skipped_when_no_url")


def test_import_image_failed_reported(tmp_path, monkeypatch):
    def fake(url, dest):
        return False
    monkeypatch.setattr(mod, "_download_image", fake)
    svc = _make_service(tmp_path)
    report = svc.import_products([_sample_product()], download_images=True)
    assert report["images"] == {"downloaded": 0, "skipped": 0, "failed": 1}
    assert len(report["imported"]) == 1  # product still imported
    print("OK test_import_image_failed_reported")


# ------------------------------------------------------------------
# Failure handling
# ------------------------------------------------------------------

def test_import_failed_reported(tmp_path, monkeypatch):
    class BrokenWriter:
        def __init__(self, db_url=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def save_product(self, flat):
            raise RuntimeError("disk full")

        session = MagicMock()

    monkeypatch.setattr(mod, "DatabaseWriter", BrokenWriter)
    svc = _make_service(tmp_path)
    report = svc.import_products([_sample_product()], download_images=True)
    assert report["imported"] == []
    assert len(report["failed"]) == 1
    assert report["failed"][0]["asin"] == "B0IMP01"
    assert "disk full" in report["failed"][0]["error"]
    print("OK test_import_failed_reported")


def test_existing_asins_returns_set(tmp_path):
    svc = _make_service(tmp_path)
    assert svc.existing_asins() == set()
    svc.import_products(
        [_sample_product(), _sample_product("B0IMP02", title="Boots")],
        download_images=False,
    )
    assert svc.existing_asins() == {"B0IMP01", "B0IMP02"}
    print("OK test_existing_asins_returns_set")
