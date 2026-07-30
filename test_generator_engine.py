"""
Tests for GeneratorEngine (Milestone 7 — Website Generation Engine 2.0).

Verifies:
  - Motorcycle page data from Knowledge Graph
  - Dynamic page sections from UpgradeSection
  - Comparison tables
  - Breadcrumbs
  - Collections integration
  - Related motorcycles / recommended products
  - FAQs and tags
  - Index / listing data
  - Works for any future niche (no hardcoded sections)
"""

import os
import sys

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.base import Base
import db.models  # registers ALL models with Base.metadata
from db.models import Product, Brand, ProductUpgradeSection, Collection
from db.generator_engine import GeneratorEngine
from db.knowledge_graph_service import MotorcycleKnowledgeGraphService


# ------------------------------------------------------------------
# Helpers — all share a SINGLE in-memory engine
# ------------------------------------------------------------------

def _make_engine():
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    return engine


def _make_gen(engine=None) -> GeneratorEngine:
    if engine is None:
        engine = _make_engine()
    gen = GeneratorEngine("sqlite://")
    gen._engine = engine
    gen._kg._engine = engine
    gen._collections._engine = engine
    gen.seed_upgrade_sections()
    return gen


def _seed_product(engine, asin="B0TEST01", title="Test Helmet",
                  brand_name="TestBrand") -> int:
    with Session(engine) as session:
        brand = session.query(Brand).filter_by(name=brand_name).first()
        if not brand:
            brand = Brand(name=brand_name, slug=brand_name.lower())
            session.add(brand)
            session.flush()
        p = Product(
            asin=asin,
            slug=asin.lower(),
            title=title,
            brand_id=brand.id,
            niche="motorcycle",
        )
        session.add(p)
        session.flush()
        pid = p.id
        session.commit()
    return pid


def _link_product_to_section(engine, product_id, section_id):
    with Session(engine) as session:
        session.add(ProductUpgradeSection(
            product_id=product_id, upgrade_section_id=section_id
        ))
        session.commit()


# ======================================================================
# Tests
# ======================================================================

def test_get_all_motorcycles_empty():
    gen = _make_gen()
    assert gen.get_all_motorcycles() == []


def test_get_motorcycle_after_create():
    gen = _make_gen()
    bike = gen.seed_motorcycle("Honda", "CB350", "honda-cb350",
                                category="Standard", engine_cc=350,
                                bike_type="Naked")
    assert bike["make"] == "Honda"
    assert bike["model"] == "CB350"
    assert bike["slug"] == "honda-cb350"

    fetched = gen.get_motorcycle("honda-cb350")
    assert fetched is not None
    assert fetched["make"] == "Honda"
    assert fetched["engine_cc"] == 350
    assert fetched["type"] == "Naked"


def test_get_motorcycle_not_found():
    gen = _make_gen()
    assert gen.get_motorcycle("nonexistent") is None


def test_get_all_motorcycles_multiple():
    gen = _make_gen()
    gen.seed_motorcycle("Honda", "CB350", "honda-cb350")
    gen.seed_motorcycle("Royal Enfield", "Classic 350", "re-classic-350")
    assert len(gen.get_all_motorcycles()) == 2


def test_build_page_sections_no_upgrade_sections():
    gen = _make_gen()
    bike = gen.seed_motorcycle("Honda", "CB350", "honda-cb350")
    assert gen.build_page_sections(bike) == []


def test_build_page_sections_with_upgrade_sections():
    gen = _make_gen()
    bike = gen.seed_motorcycle("Honda", "CB350", "honda-cb350")
    all_sections = gen._kg.get_all_upgrade_sections()
    assert len(all_sections) > 0
    gen.add_motorcycle_to_section(bike["id"], [s["id"] for s in all_sections[:2]])
    bike_full = gen.get_motorcycle("honda-cb350")
    sections = gen.build_page_sections(bike_full)
    assert len(sections) == 2
    for sec in sections:
        assert "id" in sec
        assert "title" in sec
        assert "products" in sec
        assert "total_products" in sec


def test_build_comparison_table_empty():
    gen = _make_gen()
    assert gen.build_comparison_table([]) == []


def test_build_comparison_table():
    gen = _make_gen()
    b1 = gen.seed_motorcycle("Honda", "CB350", "honda-cb350",
                              engine_cc=350, bike_type="Naked")
    b2 = gen.seed_motorcycle("Royal Enfield", "Classic 350", "re-classic-350",
                              engine_cc=350, bike_type="Cruiser")
    table = gen.build_comparison_table([b1["id"], b2["id"]])
    assert len(table) == 2
    row = table[0]
    assert "make" in row and "model" in row and "engine_cc" in row
    assert "type" in row and "slug" in row


def test_breadcrumbs_motorcycle():
    gen = _make_gen()
    c = gen.build_breadcrumbs("motorcycle", brand="Honda", model="CB350",
                               slug="honda-cb350")
    assert len(c) == 3
    assert c[0]["name"] == "Home"
    assert c[1]["name"] == "Motorcycles"
    assert c[2]["name"] == "Honda CB350"


def test_breadcrumbs_motorcycles_index():
    gen = _make_gen()
    c = gen.build_breadcrumbs("motorcycles_index")
    assert len(c) == 2 and c[-1]["name"] == "Motorcycles"


def test_breadcrumbs_collection():
    gen = _make_gen()
    c = gen.build_breadcrumbs("collection", name="Best Safety Gear")
    assert c[1]["name"] == "Collections" and c[2]["name"] == "Best Safety Gear"


def test_breadcrumbs_category():
    gen = _make_gen()
    c = gen.build_breadcrumbs("category", name="Helmets")
    assert c[1]["name"] == "Products" and c[2]["name"] == "Helmets"


def test_tags():
    gen = _make_gen()
    gen.seed_motorcycle("Honda", "CB350", "honda-cb350",
                         tags=["beginner-friendly", "retro"])
    assert sorted(gen.get_tags("honda-cb350")) == ["beginner-friendly", "retro"]


def test_faqs():
    gen = _make_gen()
    gen.seed_motorcycle("Honda", "CB350", "honda-cb350", faqs=[
        {"question": "Q1?", "answer": "A1", "sort_order": 1},
        {"question": "Q2?", "answer": "A2", "sort_order": 2},
    ])
    faqs = gen.get_faqs("honda-cb350")
    assert len(faqs) == 2
    assert faqs[0]["question"] == "Q1?"
    assert faqs[1]["answer"] == "A2"


def test_recommended_products():
    gen = _make_gen()
    pid = _seed_product(gen._engine, "B0REC01", "Rec Product")
    bike = gen.seed_motorcycle("Honda", "CB350", "honda-cb350")
    gen.add_recommended_product(bike["id"], pid)
    recs = gen.get_recommended_products("honda-cb350")
    assert len(recs) == 1
    assert recs[0]["id"] == pid


def test_related_motorcycles():
    gen = _make_gen()
    b1 = gen.seed_motorcycle("Honda", "CB350", "honda-cb350")
    b2 = gen.seed_motorcycle("Royal Enfield", "Classic 350", "re-classic-350")
    gen._kg.add_related(b1["id"], b2["id"])
    related = gen.get_related_motorcycles("honda-cb350")
    assert len(related) == 1
    assert related[0]["slug"] == "re-classic-350"


def test_collections_empty():
    gen = _make_gen()
    bike = gen.seed_motorcycle("Honda", "CB350", "honda-cb350")
    assert gen.get_motorcycle_collections(bike["id"]) == []


def test_build_motorcycle_index_data():
    gen = _make_gen()
    gen.seed_motorcycle("Honda", "CB350", "honda-cb350", bike_type="Naked")
    gen.seed_motorcycle("Royal Enfield", "Classic 350", "re-classic-350",
                         bike_type="Cruiser")
    idx = gen.build_motorcycle_index_data()
    assert idx["total_count"] == 2
    assert "Honda" in idx["brands_grouped"]
    assert idx["type_counts"]["Cruiser"] == 1


def test_niche_agnostic():
    """Proves the engine works for ANY niche — no hardcoded logic."""
    gen = _make_gen()
    gen.seed_motorcycle("Generic", "Model X", "generic-x",
                         category="Electric", engine_cc=0,
                         bike_type="Scooter", tags=["electric", "urban"])
    all_sections = gen._kg.get_all_upgrade_sections()
    gen.add_motorcycle_to_section(
        gen.get_motorcycle("generic-x")["id"],
        [s["id"] for s in all_sections[:3]]
    )
    bike_full = gen.get_motorcycle("generic-x")
    sections = gen.build_page_sections(bike_full)
    assert len(sections) == 3
    assert "electric" in gen.get_tags("generic-x")

    # Breadcrumbs don't hardcode "motorcycles" for categories
    assert gen.build_breadcrumbs("category", name="Accessories")[-1]["name"] == "Accessories"


def test_max_products_per_section():
    gen = _make_gen()
    bike = gen.seed_motorcycle("Honda", "CB350", "honda-cb350")
    all_sections = gen._kg.get_all_upgrade_sections()
    sec = all_sections[0]
    gen.add_motorcycle_to_section(bike["id"], [sec["id"]])

    # Add 10 products to that section using the shared engine
    for i in range(10):
        pid = _seed_product(gen._engine, f"B0MAX{i:03d}", f"Product {i}")
        _link_product_to_section(gen._engine, pid, sec["id"])

    bike_full = gen.get_motorcycle("honda-cb350")
    sections = gen.build_page_sections(bike_full, max_products_per_section=3)
    assert len(sections[0]["products"]) == 3
    assert sections[0]["total_products"] == 10


def test_section_no_products():
    gen = _make_gen()
    bike = gen.seed_motorcycle("Honda", "CB350", "honda-cb350")
    all_sections = gen._kg.get_all_upgrade_sections()
    gen.add_motorcycle_to_section(bike["id"], [all_sections[0]["id"]])
    bike_full = gen.get_motorcycle("honda-cb350")
    sections = gen.build_page_sections(bike_full)
    assert sections[0]["products"] == []
    assert sections[0]["total_products"] == 0


def test_get_all_collections():
    gen = _make_gen()
    collections = gen.get_all_collections()
    assert isinstance(collections, list)


def test_recommended_products_none():
    gen = _make_gen()
    gen.seed_motorcycle("Honda", "CB350", "honda-cb350")
    assert gen.get_recommended_products("honda-cb350") == []


def test_get_motorcycle_missing_returns_none():
    assert _make_gen().get_motorcycle("no-such-bike") is None


# ======================================================================
# Run
# ======================================================================

def main():
    tests = [
        ("empty_list", test_get_all_motorcycles_empty),
        ("create_and_fetch", test_get_motorcycle_after_create),
        ("not_found", test_get_motorcycle_not_found),
        ("multiple", test_get_all_motorcycles_multiple),
        ("no_upgrade_sections", test_build_page_sections_no_upgrade_sections),
        ("upgrade_sections", test_build_page_sections_with_upgrade_sections),
        ("comparison_empty", test_build_comparison_table_empty),
        ("comparison_table", test_build_comparison_table),
        ("breadcrumbs_motorcycle", test_breadcrumbs_motorcycle),
        ("breadcrumbs_index", test_breadcrumbs_motorcycles_index),
        ("breadcrumbs_collection", test_breadcrumbs_collection),
        ("breadcrumbs_category", test_breadcrumbs_category),
        ("tags", test_tags),
        ("faqs", test_faqs),
        ("recommended_products", test_recommended_products),
        ("related_motorcycles", test_related_motorcycles),
        ("collections_empty", test_collections_empty),
        ("index_data", test_build_motorcycle_index_data),
        ("niche_agnostic", test_niche_agnostic),
        ("max_products", test_max_products_per_section),
        ("section_no_products", test_section_no_products),
        ("get_all_collections", test_get_all_collections),
        ("recs_none", test_recommended_products_none),
        ("missing_motorcycle", test_get_motorcycle_missing_returns_none),
    ]

    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  GeneratorEngine Tests: {passed} passed, {failed} failed")
    print(f"{'='*60}")
    return failed


if __name__ == "__main__":
    sys.exit(main())
