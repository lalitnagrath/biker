"""
Tests for the heuristic ProductClassifier (category / collections /
compatibility / confidence) and the ClassificationService persistence path.
"""

import os
import sys

import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from db.classification_service import ClassificationService
from db.models import AccessoryType, Motorcycle, Product, UpgradeCollection
from db.product_classifier import (
    CATEGORIES,
    COLLECTIONS,
    ProductClassifier,
)

_BIKES = [
    {"make": "Royal Enfield", "model": "Hunter 350", "slug": "royal-enfield-hunter-350"},
    {"make": "Royal Enfield", "model": "Classic 350", "slug": "royal-enfield-classic-350"},
    {"make": "Royal Enfield", "model": "Himalayan 450", "slug": "royal-enfield-himalayan-450"},
    {"make": "Honda", "model": "CB350RS", "slug": "honda-cb350rs"},
    {"make": "KTM", "model": "390 Duke", "slug": "ktm-390-duke"},
]


def _classifier(**kwargs):
    return ProductClassifier(_BIKES)


def _cl(title, **kw):
    return _classifier().classify(title=title, **kw)


# ------------------------------------------------------------------
# Category
# ------------------------------------------------------------------

def test_category_bar_end_mirror():
    r = _cl("OTOROYS Premium Motorcycle Bar End Mirror Metal Handle ABS")
    assert r["category"] == "Mirror"
    print("OK test_category_bar_end_mirror")


def test_category_most_specific_wins():
    # "helmet visor" must beat bare "visor" -> Helmet, not Windshield
    r = _cl("Full Face Helmet Visor for Bike")
    assert r["category"] == "Helmet"
    print("OK test_category_most_specific_wins")


def test_category_windshield_visor():
    r = _cl("TVS Bike Windshield Visor Wind Screen Glass")
    assert r["category"] == "Windshield"
    print("OK test_category_windshield_visor")


def test_category_unknown_when_no_match():
    r = _cl("Random Plastic Accessory Item for Bike")
    assert r["category"] is None
    assert r["type"] == "Unknown"
    assert r["confidence"] == "Low"
    print("OK test_category_unknown_when_no_match")


def test_taxonomy_sizes():
    assert len(CATEGORIES) == 30
    assert len(COLLECTIONS) == 17
    print("OK test_taxonomy_sizes")


# ------------------------------------------------------------------
# Collections
# ------------------------------------------------------------------

def test_collections_multiple_assigned():
    r = _cl("Royal Enfield Hunter 350 Crash Guard Leg Guard")
    assert "Protection" in r["collections"]
    assert "Adventure" in r["collections"]
    assert len(r["collections"]) >= 2
    print("OK test_collections_multiple_assigned")


def test_collections_keyword_supplements():
    r = _cl("KTM 390 Duke LED Tail Light")
    assert "Lighting" in r["collections"]
    print("OK test_collections_keyword_supplements")


def test_collections_all_within_predefined():
    r = _cl("Premium Billet Clutch Lever Cafe Racer Style")
    for c in r["collections"]:
        assert c in COLLECTIONS, c
    assert "Cafe Racer" in r["collections"]
    assert "Premium Upgrades" in r["collections"]
    print("OK test_collections_all_within_predefined")


# ------------------------------------------------------------------
# Compatibility
# ------------------------------------------------------------------

def test_bike_specific_extracts_bike():
    r = _cl("Royal Enfield Hunter 350 Crash Guard")
    assert r["type"] == "Bike Specific"
    assert r["compatible_motorcycles"] == ["Royal Enfield Hunter 350"]
    assert r["compatible_motorcycle_slugs"] == ["royal-enfield-hunter-350"]
    assert r["confidence"] == "High"
    print("OK test_bike_specific_extracts_bike")


def test_universal_category_without_bike():
    r = _cl("Steelbird Full Face Helmet")
    assert r["type"] == "Universal"
    assert r["compatible_motorcycles"] == []
    assert r["confidence"] == "Medium"
    print("OK test_universal_category_without_bike")


def test_universal_explicit_word_high_confidence():
    r = _cl("Mobile Holder Universal Fit for All Bikes")
    assert r["type"] == "Universal"
    assert r["confidence"] == "High"
    print("OK test_universal_explicit_word_high_confidence")


def test_non_universal_category_no_bike_is_unknown():
    # Windshield without a bike and not in the universal whitelist
    r = _cl("Heavy Metal Visor for Bike")
    assert r["type"] == "Unknown"
    assert r["confidence"] == "Low"
    print("OK test_non_universal_category_no_bike_is_unknown")


def test_uses_description_and_bullets():
    r = _classifier().classify(
        title="Riding Gloves",
        description="Made for Royal Enfield Classic 350 touring",
        bullets=["Premium leather", "Universal fit"],
    )
    assert r["category"] == "Gloves"
    assert r["type"] == "Bike Specific"
    assert r["compatible_motorcycles"] == ["Royal Enfield Classic 350"]
    print("OK test_uses_description_and_bullets")


def test_bike_cover_category():
    r = _cl("Fuzicon Scooty Cover for Honda Activa 125 - Water Resistant Bike Body Cover")
    assert r["category"] == "Bike Cover"
    assert "Protection" in r["collections"]
    print("OK test_bike_cover_category")


def test_whole_motorcycle_detected():
    r = _cl("HARLEY-DAVIDSON X440 S Motorcycle 440cc Matte Black booking for Ex-Showroom")
    assert r["category"] == "Motorcycle"
    print("OK test_whole_motorcycle_detected")


def test_motorcycle_does_not_override_accessory():
    # "motorcycle" alone in an accessory title must not win over the accessory
    r = _cl("Premium Motorcycle Bar End Mirror Metal Handle")
    assert r["category"] == "Mirror"
    print("OK test_motorcycle_does_not_override_accessory")


def test_bike_alarm_category():
    r = _cl("Quick Sense Wireless Bike Alarm 113dB Anti-Theft Vibration Sensor with Remote")
    assert r["category"] == "Bike Alarm"
    assert "Security" in r["collections"]
    print("OK test_bike_alarm_category")


# ------------------------------------------------------------------
# Service (in-memory SQLite)
# ------------------------------------------------------------------

def _db():
    eng = create_engine("sqlite:///:memory:", echo=False)
    sqlalchemy.orm.configure_mappers()
    import db.models as models  # noqa: F401
    models.Base.metadata.create_all(eng)
    return eng


def test_service_ensure_taxonomy_creates_rows():
    eng = _db()
    with Session(eng) as s:
        svc = ClassificationService(s)
        res = svc.ensure_taxonomy()
        s.commit()
        assert res["accessory_types_created"] == 30
        assert res["collections_created"] == 17
        assert s.query(AccessoryType).count() == 30
        assert s.query(UpgradeCollection).count() == 17
    print("OK test_service_ensure_taxonomy_creates_rows")


def test_service_classify_all_writes_product():
    eng = _db()
    with Session(eng) as s:
        svc = ClassificationService(s)
        svc.ensure_taxonomy()
        s.commit()
        hunter = Motorcycle(make="Royal Enfield", model="Hunter 350",
                            slug="royal-enfield-hunter-350")
        s.add(hunter)
        s.add(Product(asin="B0T01", title="Hunter 350 Crash Guard Leg Guard",
                      niche="motorcycles"))
        s.add(Product(asin="B0T02", title="Steelbird Full Face Helmet",
                      niche="motorcycles"))
        s.commit()

    with Session(eng) as s:
        svc = ClassificationService(s)
        report = svc.classify_all(dry_run=False)
        assert report["total"] == 2
        assert report["by_type"].get("Bike Specific") == 1
        assert report["by_type"].get("Universal") == 1

    with Session(eng) as s:
        guard = s.query(Product).filter_by(asin="B0T01").one()
        assert guard.compatibility_type == "specific"
        assert guard.compatible_bikes == ["royal-enfield-hunter-350"]
        assert guard.classification_confidence == "High"
        atype = s.get(AccessoryType, guard.accessory_type_id)
        assert atype.name == "Crash Guard"
        colls = [c.name for c in guard.upgrade_collections]
        assert "Protection" in colls and "Adventure" in colls

        helmet = s.query(Product).filter_by(asin="B0T02").one()
        assert helmet.universal is True
        assert helmet.compatibility_type == "universal"
    print("OK test_service_classify_all_writes_product")


def test_service_classify_dry_run_writes_nothing():
    eng = _db()
    with Session(eng) as s:
        svc = ClassificationService(s)
        svc.ensure_taxonomy()
        s.commit()
        s.add(Product(asin="B0T03", title="Random Plastic Accessory Item",
                      niche="motorcycles"))
        s.commit()

    with Session(eng) as s:
        report = ClassificationService(s).classify_all(dry_run=True)
        assert report["total"] == 1

    with Session(eng) as s:
        p = s.query(Product).filter_by(asin="B0T03").one()
        assert p.accessory_type_id is None
        assert p.compatibility_type is None
        assert p.classification_confidence is None
    print("OK test_service_classify_dry_run_writes_nothing")
