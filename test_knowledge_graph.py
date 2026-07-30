"""
Tests for Motorcycle Knowledge Graph (repository + service).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.base import Base
from db.models import (
    Motorcycle, MotorcycleTag, MotorcycleFAQ, UpgradeSection,
    MotorcycleUpgradeSection, ProductUpgradeSection,
    MotorcycleRecommendedProduct, MotorcycleCollection, MotorcycleRelation,
    Product, Brand, Category, Collection, CollectionItem, Image,
)
from db.motorcycle_repository import MotorcycleKnowledgeRepository
from db.knowledge_graph_service import MotorcycleKnowledgeGraphService


def _setup_db():
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    return engine


def _seed_product(engine, **overrides):
    with Session(engine) as session:
        b = Brand(name="Test Brand", slug="test-brand")
        session.add(b)
        session.flush()
        cat = Category(name="Helmet", slug="helmet", niche="motorcycles")
        session.add(cat)
        session.flush()
        p = Product(
            asin=overrides.get("asin", "TESTASIN001"),
            slug=overrides.get("slug", "test-product"),
            title=overrides.get("title", "Test Product"),
            brand_id=b.id,
            niche="motorcycles",
            price=overrides.get("price", 1000),
            rating=overrides.get("rating", 4.0),
            score=overrides.get("score", 80),
            status=overrides.get("status", "active"),
        )
        session.add(p)
        session.commit()
        return p.id


def _seed_collection(engine):
    with Session(engine) as session:
        c = Collection(name="Test Collection", slug="test-collection")
        session.add(c)
        session.commit()
        return c.id


# =====================================================================
# Repository Tests
# =====================================================================

def test_create_motorcycle():
    engine = _setup_db()
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        bike = repo.create({
            "make": "Honda",
            "model": "CB350",
            "slug": "honda-cb350",
            "year_start": 2021,
            "category": "Classic",
            "engine_cc": 350,
            "type": "Retro Classic",
            "hero_image": "/images/honda-cb350.jpg",
            "description": "A modern classic motorcycle",
        })
        assert bike.id is not None
        assert bike.make == "Honda"
        assert bike.model == "CB350"
        assert bike.hero_image == "/images/honda-cb350.jpg"
        assert bike.description == "A modern classic motorcycle"
        assert bike.engine_cc == 350
        assert bike.type == "Retro Classic"
    print("OK test_create_motorcycle")


def test_get_motorcycle():
    engine = _setup_db()
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        bike = repo.create({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
        fetched = repo.get(bike.id)
        assert fetched is not None
        assert fetched.model == "CB350"
    print("OK test_get_motorcycle")


def test_get_by_slug():
    engine = _setup_db()
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        repo.create({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
        fetched = repo.get_by_slug("honda-cb350")
        assert fetched is not None
        assert fetched.model == "CB350"
    print("OK test_get_by_slug")


def test_update_motorcycle():
    engine = _setup_db()
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        bike = repo.create({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
        repo.update(bike.id, {"hero_image": "/new/image.jpg", "description": "Updated desc"})
        session.flush()
        fetched = repo.get(bike.id)
        assert fetched.hero_image == "/new/image.jpg"
        assert fetched.description == "Updated desc"
    print("OK test_update_motorcycle")


def test_delete_motorcycle():
    engine = _setup_db()
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        bike = repo.create({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
        assert repo.delete(bike.id) is True
        assert repo.get(bike.id) is None
        assert repo.delete(9999) is False
    print("OK test_delete_motorcycle")


def test_search_motorcycles():
    engine = _setup_db()
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        repo.create({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
        repo.create({"make": "Royal Enfield", "model": "Classic 350", "slug": "re-classic-350"})
        repo.create({"make": "Honda", "model": "Activa", "slug": "honda-activa", "type": "Scooter"})
        session.flush()
        result, total = repo.search(make="Honda")
        assert total == 2
        assert len(result) == 2
        result2, total2 = repo.search(query="Classic")
        assert total2 == 1
    print("OK test_search_motorcycles")


def test_tags():
    engine = _setup_db()
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        bike = repo.create({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
        repo.set_tags(bike.id, ["classic", "retro", "350cc"])
        tags = repo.get_tags(bike.id)
        assert sorted(tags) == sorted(["classic", "retro", "350cc"])
        repo.set_tags(bike.id, ["updated"])
        tags = repo.get_tags(bike.id)
        assert tags == ["updated"]
    print("OK test_tags")


def test_faqs():
    engine = _setup_db()
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        bike = repo.create({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
        repo.set_faqs(bike.id, [
            {"question": "Q1?", "answer": "A1"},
            {"question": "Q2?", "answer": "A2"},
        ])
        faqs = repo.get_faqs(bike.id)
        assert len(faqs) == 2
        assert faqs[0]["question"] == "Q1?"
        assert faqs[1]["question"] == "Q2?"
    print("OK test_faqs")


def test_upgrade_sections():
    engine = _setup_db()
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        created = repo.seed_upgrade_sections()
        assert len(created) == 6
        names = {s.name for s in created}
        assert "Protection" in names
        assert "Style" in names
        assert "Lighting" in names
        assert "Touring" in names
        assert "Comfort" in names
        assert "Maintenance" in names
        # Idempotent
        created2 = repo.seed_upgrade_sections()
        assert len(created2) == 0
        all_sections = repo.get_all_upgrade_sections()
        assert len(all_sections) == 6
    print("OK test_upgrade_sections")


def test_motorcycle_upgrade_sections():
    engine = _setup_db()
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        repo.seed_upgrade_sections()
        bike = repo.create({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
        sections = repo.get_all_upgrade_sections()
        section_ids = [s.id for s in sections[:3]]
        repo.set_motorcycle_upgrade_sections(bike.id, section_ids)
        fetched = repo.get(bike.id)
        assert len(fetched.upgrade_sections) == 3
        fetched_sids = sorted(s.id for s in fetched.upgrade_sections)
        assert fetched_sids == sorted(section_ids)
    print("OK test_motorcycle_upgrade_sections")


def test_product_upgrade_sections():
    engine = _setup_db()
    pid = _seed_product(engine)
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        repo.seed_upgrade_sections()
        sections = repo.get_all_upgrade_sections()
        section_ids = [s.id for s in sections[:2]]
        repo.set_product_upgrade_sections(pid, section_ids)
        session.flush()
        products = repo.get_products_by_upgrade_section(sections[0].id)
        assert len(products) == 1
        assert products[0].id == pid
    print("OK test_product_upgrade_sections")


def test_recommended_products():
    engine = _setup_db()
    pid = _seed_product(engine)
    bike_id = None
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        bike = repo.create({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
        bike_id = bike.id
        repo.add_recommended_product(bike.id, pid)
        assert repo.add_recommended_product(bike.id, pid) is False
        fetched = repo.get(bike.id)
        assert len(fetched.recommended_products) == 1
        assert fetched.recommended_products[0].id == pid
        repo.remove_recommended_product(bike.id, pid)
        assert repo.remove_recommended_product(bike.id, 9999) is False
        session.commit()
    with Session(engine) as session2:
        repo2 = MotorcycleKnowledgeRepository(session2)
        fetched = repo2.get(bike_id)
        assert fetched is not None
        assert len(fetched.recommended_products) == 0
    print("OK test_recommended_products")


def test_collections():
    engine = _setup_db()
    cid = _seed_collection(engine)
    bike_id = None
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        bike = repo.create({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
        bike_id = bike.id
        repo.add_collection(bike.id, cid)
        assert repo.add_collection(bike.id, cid) is False
        fetched = repo.get(bike.id)
        assert len(fetched.collections) == 1
        assert fetched.collections[0].id == cid
        repo.remove_collection(bike.id, cid)
        assert repo.remove_collection(bike.id, 9999) is False
        session.commit()
    with Session(engine) as session2:
        repo2 = MotorcycleKnowledgeRepository(session2)
        fetched = repo2.get(bike_id)
        assert fetched is not None
        assert len(fetched.collections) == 0
    print("OK test_collections")

def test_related_motorcycles():
    engine = _setup_db()
    bike1_id = None
    with Session(engine) as session:
        repo = MotorcycleKnowledgeRepository(session)
        bike1 = repo.create({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
        bike2 = repo.create({"make": "Royal Enfield", "model": "Classic 350", "slug": "re-classic-350"})
        bike1_id = bike1.id
        repo.add_related(bike1.id, bike2.id)
        assert repo.add_related(bike1.id, bike2.id) is False
        assert repo.add_related(bike1.id, bike1.id) is False
        fetched = repo.get(bike1.id)
        assert len(fetched.related_motorcycles) == 1
        assert fetched.related_motorcycles[0].id == bike2.id
        repo.remove_related(bike1.id, bike2.id)
        assert repo.remove_related(bike1.id, 9999) is False
        session.commit()
    with Session(engine) as session2:
        repo2 = MotorcycleKnowledgeRepository(session2)
        fetched = repo2.get(bike1_id)
        assert fetched is not None
        assert len(fetched.related_motorcycles) == 0
    print("OK test_related_motorcycles")


# =====================================================================
# Service Tests
# =====================================================================

def test_service_crud():
    engine = _setup_db()
    service = MotorcycleKnowledgeGraphService()
    service._engine = engine
    data = {
        "make": "Yamaha",
        "model": "MT-15",
        "slug": "yamaha-mt-15",
        "type": "Naked",
        "engine_cc": 155,
        "tags": ["naked", "street"],
        "faqs": [{"question": "Is it good?", "answer": "Yes"}],
    }
    result = service.create_motorcycle(data)
    assert result["make"] == "Yamaha"
    assert "tags" in result
    assert "faqs" in result
    assert result["slug"] == "yamaha-mt-15"

    fetched = service.get_motorcycle_by_slug("yamaha-mt-15")
    assert fetched is not None
    assert fetched["model"] == "MT-15"

    fetched_by_id = service.get_motorcycle(result["id"])
    assert fetched_by_id is not None
    assert fetched_by_id["make"] == "Yamaha"

    updated = service.update_motorcycle(result["id"], {"hero_image": "/img/hero.jpg"})
    assert updated["hero_image"] == "/img/hero.jpg"

    assert service.delete_motorcycle(result["id"]) is True
    assert service.get_motorcycle(result["id"]) is None
    assert service.delete_motorcycle(9999) is False
    print("OK test_service_crud")


def test_service_search():
    engine = _setup_db()
    service = MotorcycleKnowledgeGraphService()
    service._engine = engine
    service.create_motorcycle({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
    service.create_motorcycle({"make": "Honda", "model": "Activa", "slug": "honda-activa", "type": "Scooter"})

    results = service.search_motorcycles(make="Honda")
    assert len(results) == 2
    results = service.search_motorcycles(query="Activa")
    assert len(results) == 1
    print("OK test_service_search")


def test_service_upgrade_sections():
    engine = _setup_db()
    service = MotorcycleKnowledgeGraphService()
    service._engine = engine
    created = service.seed_upgrade_sections()
    assert len(created) == 6
    all_sections = service.get_all_upgrade_sections()
    assert len(all_sections) == 6
    created2 = service.seed_upgrade_sections()
    assert len(created2) == 0
    print("OK test_service_upgrade_sections")


def test_service_set_motorcycle_upgrade_sections():
    engine = _setup_db()
    service = MotorcycleKnowledgeGraphService()
    service._engine = engine
    service.seed_upgrade_sections()
    bike = service.create_motorcycle({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
    sections = service.get_all_upgrade_sections()
    section_ids = [s["id"] for s in sections[:3]]
    result = service.set_motorcycle_upgrade_sections(bike["id"], section_ids)
    assert len(result["upgrade_sections"]) == 3
    print("OK test_service_set_motorcycle_upgrade_sections")


def test_service_recommended_products():
    engine = _setup_db()
    pid = _seed_product(engine)
    service = MotorcycleKnowledgeGraphService()
    service._engine = engine
    bike = service.create_motorcycle({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
    result = service.add_recommended_product(bike["id"], pid)
    assert result is not None
    assert pid in result["recommended_product_ids"]
    result2 = service.remove_recommended_product(bike["id"], pid)
    assert result2 is not None
    assert pid not in result2["recommended_product_ids"]
    print("OK test_service_recommended_products")


def test_service_collections():
    engine = _setup_db()
    cid = _seed_collection(engine)
    service = MotorcycleKnowledgeGraphService()
    service._engine = engine
    bike = service.create_motorcycle({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
    result = service.add_collection(bike["id"], cid)
    assert result is not None
    assert cid in result["collection_ids"]
    result2 = service.remove_collection(bike["id"], cid)
    assert result2 is not None
    assert cid not in result2["collection_ids"]
    print("OK test_service_collections")


def test_service_related():
    engine = _setup_db()
    service = MotorcycleKnowledgeGraphService()
    service._engine = engine
    bike1 = service.create_motorcycle({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
    bike2 = service.create_motorcycle({"make": "RE", "model": "Classic 350", "slug": "re-classic-350"})
    result = service.add_related(bike1["id"], bike2["id"])
    assert result is not None
    slugs = [r["slug"] for r in result["related_motorcycles"]]
    assert "re-classic-350" in slugs
    result2 = service.remove_related(bike1["id"], bike2["id"])
    assert len(result2["related_motorcycles"]) == 0
    print("OK test_service_related")


def test_service_set_recommended_products():
    engine = _setup_db()
    pid = _seed_product(engine)
    service = MotorcycleKnowledgeGraphService()
    service._engine = engine
    bike = service.create_motorcycle({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
    result = service.set_recommended_products(bike["id"], [pid])
    assert pid in result["recommended_product_ids"]
    result = service.set_recommended_products(bike["id"], [])
    assert result["recommended_product_ids"] == []
    print("OK test_service_set_recommended_products")


def test_service_set_collections():
    engine = _setup_db()
    cid1 = _seed_collection(engine)
    with Session(engine) as session:
        c2 = Collection(name="C2", slug="c2")
        session.add(c2)
        session.commit()
        cid3 = c2.id
    service = MotorcycleKnowledgeGraphService()
    service._engine = engine
    bike = service.create_motorcycle({"make": "Honda", "model": "CB350", "slug": "honda-cb350"})
    result = service.add_collection(bike["id"], cid1)
    result = service.add_collection(bike["id"], cid3)
    assert sorted(result["collection_ids"]) == sorted([cid1, cid3])
    print("OK test_service_set_collections")


def test_service_include_full():
    engine = _setup_db()
    service = MotorcycleKnowledgeGraphService()
    service._engine = engine
    bike = service.create_motorcycle({"make": "Honda", "model": "CB350", "slug": "honda-cb350", "tags": ["tag1"], "faqs": [{"question": "Q?", "answer": "A"}]})
    result = service.get_motorcycle(bike["id"], include_full=False)
    assert result is not None
    assert result["tags"] == []
    assert result["faqs"] == []
    assert result["upgrade_sections"] == []
    assert result["related_motorcycles"] == []
    result_full = service.get_motorcycle(bike["id"], include_full=True)
    assert result_full is not None
    assert "tag1" in result_full["tags"]
    assert len(result_full["faqs"]) == 1
    print("OK test_service_include_full")


# =====================================================================
# Main
# =====================================================================

def main():
    print("=" * 60)
    print("Running Motorcycle Knowledge Graph Tests")
    print("=" * 60)
    print()
    tests = [
        test_create_motorcycle,
        test_get_motorcycle,
        test_get_by_slug,
        test_update_motorcycle,
        test_delete_motorcycle,
        test_search_motorcycles,
        test_tags,
        test_faqs,
        test_upgrade_sections,
        test_motorcycle_upgrade_sections,
        test_product_upgrade_sections,
        test_recommended_products,
        test_collections,
        test_related_motorcycles,
        test_service_crud,
        test_service_search,
        test_service_upgrade_sections,
        test_service_set_motorcycle_upgrade_sections,
        test_service_recommended_products,
        test_service_collections,
        test_service_related,
        test_service_set_recommended_products,
        test_service_set_collections,
        test_service_include_full,
    ]
    failures = []
    for t in tests:
        try:
            t()
        except Exception as e:
            failures.append((t.__name__, e))
            import traceback
            traceback.print_exc()
            print()

    print()
    if failures:
        print("=" * 60)
        print(f"FAILED: {len(failures)} test(s) failed:")
        for name, err in failures:
            print(f"  - {name}: {err}")
        print("=" * 60)
        return 1
    else:
        print("=" * 60)
        print(f"OK All {len(tests)} tests passed!")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
