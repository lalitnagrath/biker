"""
Tests for SmartCollectionService and CollectionRepository.
"""

import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.base import Base
from db.models import Collection, CollectionItem, CollectionRelation, Product, Brand, Category, Image
from db.collection_repository import CollectionRepository
from db.smart_collections import SmartCollectionService, _collection_to_dict


def _setup_db():
    """Create an in-memory SQLite DB with all tables."""
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    return engine


def _seed_product(engine, **overrides):
    """Insert a product and return its id."""
    data = {
        "asin": "B0TEST001",
        "title": "Test Helmet",
        "slug": "test-helmet",
        "niche": "motorcycles",
        "price": 2999,
        "mrp": 3999,
        "rating": 4.2,
        "review_count": 150,
        "score": 82,
        "status": "active",
    }
    data.update(overrides)
    with Session(engine) as session:
        p = Product(**data)
        session.add(p)
        session.flush()
        pid = p.id
        session.commit()
    return pid


def _seed_category(engine, name="Helmet", niche="motorcycles"):
    with Session(engine) as session:
        c = Category(name=name, slug=name.lower(), niche=niche)
        session.add(c)
        session.flush()
        cid = c.id
        session.commit()
    return cid


def _link_product_category(engine, product_id, category_id):
    from db.models import ProductCategory
    with Session(engine) as session:
        pc = ProductCategory(product_id=product_id, category_id=category_id)
        session.add(pc)
        session.commit()


def _seed_brand(engine, name="TestBrand"):
    with Session(engine) as session:
        b = Brand(name=name, slug=name.lower())
        session.add(b)
        session.flush()
        bid = b.id
        session.commit()
    return bid


def _link_brand(engine, product_id, brand_id):
    with Session(engine) as session:
        p = session.query(Product).get(product_id)
        p.brand_id = brand_id
        session.commit()


# ------------------------------------------------------------------
# CollectionRepository tests
# ------------------------------------------------------------------

def test_create_collection():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)
        c = repo.create_collection({
            "name": "Premium Helmets",
            "slug": "premium-helmets",
            "niche": "motorcycles",
            "description": "Top-rated helmets",
            "rule_type": "rule",
            "rule_definition": {"conditions": [{"field": "score", "op": ">=", "value": 85}], "logic": "and"},
            "is_featured": True,
        })
        assert c.id is not None
        assert c.name == "Premium Helmets"
        assert c.slug == "premium-helmets"
    print("OK test_create_collection")


def test_get_collection():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)
        c = repo.create_collection({"name": "Test", "slug": "test"})
        session.flush()
        cid = c.id

        fetched = repo.get_collection(cid)
        assert fetched is not None
        assert fetched.name == "Test"

        not_found = repo.get_collection(9999)
        assert not_found is None
    print("OK test_get_collection")


def test_get_by_slug():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)
        repo.create_collection({"name": "Test", "slug": "test-collection"})
        session.flush()

        fetched = repo.get_by_slug("test-collection")
        assert fetched is not None
        assert fetched.name == "Test"

        not_found = repo.get_by_slug("nonexistent")
        assert not_found is None
    print("OK test_get_by_slug")


def test_update_collection():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)
        c = repo.create_collection({"name": "Old", "slug": "old"})
        session.flush()
        cid = c.id

        updated = repo.update_collection(cid, {"name": "New", "description": "Updated desc"})
        assert updated is not None
        assert updated.name == "New"
        assert updated.description == "Updated desc"

        not_found = repo.update_collection(9999, {"name": "Nope"})
        assert not_found is None
    print("OK test_update_collection")


def test_delete_collection():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)
        c = repo.create_collection({"name": "Delete Me", "slug": "delete-me"})
        session.flush()
        cid = c.id

        ok = repo.delete_collection(cid)
        assert ok is True

        not_found = repo.delete_collection(9999)
        assert not_found is False
    print("OK test_delete_collection")


def test_collection_crud():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)

        # Create
        c = repo.create_collection({
            "name": "Safety First",
            "slug": "safety-first",
            "niche": "motorcycles",
            "description": "Safety gear collection",
            "hero_image": "https://example.com/hero.jpg",
            "seo_title": "Safety First - BikeReview",
            "seo_description": "Best safety gear",
            "is_visible": True,
            "is_featured": False,
            "rule_type": "manual",
            "sort_order": 1,
        })
        session.flush()
        cid = c.id

        # Verify all fields
        assert c.hero_image == "https://example.com/hero.jpg"
        assert c.seo_title == "Safety First - BikeReview"
        assert c.seo_description == "Best safety gear"
        assert c.is_visible is True
        assert c.is_featured is False
        assert c.rule_type == "manual"
        assert c.sort_order == 1

        # Update
        repo.update_collection(cid, {"name": "Safety First Updated", "is_featured": True})
        session.flush()
        assert c.name == "Safety First Updated"
        assert c.is_featured is True

        # Search
        results, total = repo.search_collections(query="Safety")
        assert total >= 1

        results, total = repo.search_collections(is_featured=True)
        assert total >= 1

        # Delete
        repo.delete_collection(cid)
        session.flush()
        assert repo.get_collection(cid) is None
    print("OK test_collection_crud")


def test_product_membership():
    engine = _setup_db()
    pid = _seed_product(engine)

    with Session(engine) as session:
        repo = CollectionRepository(session)
        c = repo.create_collection({"name": "Test", "slug": "test"})
        session.flush()
        cid = c.id

        # Add product
        item = repo.add_product(cid, pid, sort_order=5, badge="Best Seller", notes="Great product", is_featured=True)
        assert item.product_id == pid
        assert item.sort_order == 5
        assert item.badge == "Best Seller"
        assert item.notes == "Great product"
        assert item.is_featured is True

        # Adding same product again should update, not duplicate
        repo.add_product(cid, pid, sort_order=10)
        session.flush()
        items = session.query(CollectionItem).filter_by(collection_id=cid).all()
        assert len(items) == 1
        assert items[0].sort_order == 10

        # Set product order
        repo.set_product_order(cid, [pid])
        session.flush()
        assert items[0].sort_order == 0

        # Set featured
        repo.set_product_featured(cid, pid, False)
        assert items[0].is_featured is False

        # Remove product
        repo.remove_product(cid, pid)
        session.flush()
        assert session.query(CollectionItem).filter_by(collection_id=cid).count() == 0
    print("OK test_product_membership")


def test_related_collections():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)
        c1 = repo.create_collection({"name": "A", "slug": "a"})
        c2 = repo.create_collection({"name": "B", "slug": "b"})
        session.flush()

        repo.add_related(c1.id, c2.id)
        session.flush()
        assert session.query(CollectionRelation).count() == 1

        # Add same relation again (idempotent)
        repo.add_related(c1.id, c2.id)
        session.flush()
        assert session.query(CollectionRelation).count() == 1

        # Remove
        repo.remove_related(c1.id, c2.id)
        session.flush()
        assert session.query(CollectionRelation).count() == 0
    print("OK test_related_collections")


def test_rule_evaluation():
    engine = _setup_db()

    # Seed a product with score=82, category=Helmet, brand=TestBrand
    pid = _seed_product(engine, score=82, asin="B0TEST002")
    bid = _seed_brand(engine)
    _link_brand(engine, pid, bid)
    cid = _seed_category(engine, "Helmet")
    _link_product_category(engine, pid, cid)

    from sqlalchemy.orm import joinedload
    with Session(engine) as session:
        product = (
            session.query(Product)
            .options(
                joinedload(Product.brand),
                joinedload(Product.categories),
            )
            .filter(Product.id == pid)
            .first()
        )

        # Test rule: score >= 80 AND category == Helmet
        rule = {
            "conditions": [
                {"field": "score", "op": ">=", "value": 80},
                {"field": "category", "op": "==", "value": "Helmet"},
            ],
            "logic": "and",
        }
        assert CollectionRepository.evaluate_rule(rule, product) is True

        # Test rule: score >= 90 (should fail)
        rule2 = {
            "conditions": [{"field": "score", "op": ">=", "value": 90}],
            "logic": "and",
        }
        assert CollectionRepository.evaluate_rule(rule2, product) is False

        # Test rule: price <= 3000
        rule3 = {
            "conditions": [{"field": "price", "op": "<=", "value": 3000}],
            "logic": "and",
        }
        assert CollectionRepository.evaluate_rule(rule3, product) is True

        # Test rule with OR logic
        rule4 = {
            "conditions": [
                {"field": "score", "op": ">=", "value": 90},
                {"field": "category", "op": "==", "value": "Helmet"},
            ],
            "logic": "or",
        }
        assert CollectionRepository.evaluate_rule(rule4, product) is True

        # Test "in" operator
        rule5 = {
            "conditions": [
                {"field": "category", "op": "in", "value": ["Helmet", "Jackets"]},
            ],
            "logic": "and",
        }
        assert CollectionRepository.evaluate_rule(rule5, product) is True

        # Test "not_in" operator
        rule6 = {
            "conditions": [
                {"field": "category", "op": "not_in", "value": ["Jackets", "Gloves"]},
            ],
            "logic": "and",
        }
        assert CollectionRepository.evaluate_rule(rule6, product) is True

    print("OK test_rule_evaluation")


def test_search_collections():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)
        repo.create_collection({"name": "Premium Helmets", "slug": "premium-helmets", "is_visible": True, "is_featured": True, "niche": "motorcycles"})
        repo.create_collection({"name": "Budget Friendly", "slug": "budget-friendly", "is_visible": True, "is_featured": False, "niche": "motorcycles"})
        repo.create_collection({"name": "Safety Gear", "slug": "safety-gear", "is_visible": False, "niche": "motorcycles"})
        session.flush()

        visible, total = repo.search_collections(is_visible=True)
        assert total == 2

        featured, total = repo.search_collections(is_featured=True)
        assert total == 1

        query_results, total = repo.search_collections(query="helmet")
        assert total >= 1

        by_niche, total = repo.search_collections(niche="motorcycles")
        assert total >= 2

        not_found, total = repo.search_collections(niche="cars")
        assert total == 0
    print("OK test_search_collections")


def test_visible_collections():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)
        repo.create_collection({"name": "Visible", "slug": "visible", "is_visible": True})
        repo.create_collection({"name": "Hidden", "slug": "hidden", "is_visible": False})
        session.flush()

        visible = repo.get_visible_collections()
        assert len(visible) == 1
        assert visible[0].name == "Visible"
    print("OK test_visible_collections")


def test_featured_collections():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)
        repo.create_collection({"name": "Featured", "slug": "featured", "is_visible": True, "is_featured": True})
        repo.create_collection({"name": "Not Featured", "slug": "not-featured", "is_visible": True, "is_featured": False})
        session.flush()

        featured = repo.get_featured_collections()
        assert len(featured) == 1
        assert featured[0].name == "Featured"
    print("OK test_featured_collections")


def test_rule_collections():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)
        repo.create_collection({"name": "Manual", "slug": "manual", "rule_type": "manual"})
        repo.create_collection({"name": "Rule Based", "slug": "rule-based", "rule_type": "rule"})
        session.flush()

        rules = repo.get_rule_collections()
        assert len(rules) == 1
        assert rules[0].name == "Rule Based"
    print("OK test_rule_collections")


# ------------------------------------------------------------------
# SmartCollectionService tests
# ------------------------------------------------------------------

def _seed_service_collections(engine):
    """Seed the DB with some collections for service-level testing."""
    # We use the service's own DB connection, so just use the engine URL
    pass


def test_service_get_collections():
    engine = _setup_db()
    # Create collection directly
    with Session(engine) as session:
        repo = CollectionRepository(session)
        repo.create_collection({"name": "Svc Test", "slug": "svc-test", "is_visible": True})
        session.commit()

    svc = SmartCollectionService(db_url="sqlite://")
    svc._engine = engine  # Use our in-memory engine

    collections = svc.get_collections()
    assert len(collections) >= 1
    found = [c for c in collections if c["slug"] == "svc-test"]
    assert len(found) == 1
    assert found[0]["name"] == "Svc Test"

    print("OK test_service_get_collections")


def test_service_get_collection_by_slug():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)
        repo.create_collection({"name": "Slug Test", "slug": "slug-test"})
        session.commit()

    svc = SmartCollectionService(db_url="sqlite://")
    svc._engine = engine

    c = svc.get_collection_by_slug("slug-test")
    assert c is not None
    assert c["name"] == "Slug Test"

    assert svc.get_collection_by_slug("nonexistent") is None
    print("OK test_service_get_collection_by_slug")


def test_service_crud():
    engine = _setup_db()
    svc = SmartCollectionService(db_url="sqlite://")
    svc._engine = engine

    # Create
    created = svc.create_collection({"name": "CRUD Test", "slug": "crud-test"})
    assert created["name"] == "CRUD Test"
    cid = created["id"]

    # Read
    fetched = svc.get_collection(cid)
    assert fetched is not None
    assert fetched["name"] == "CRUD Test"

    # Update
    updated = svc.update_collection(cid, {"description": "Updated desc"})
    assert updated["description"] == "Updated desc"

    # Delete
    deleted = svc.delete_collection(cid)
    assert deleted is True
    assert svc.get_collection(cid) is None
    print("OK test_service_crud")


def test_collection_to_dict():
    engine = _setup_db()
    with Session(engine) as session:
        repo = CollectionRepository(session)
        c = repo.create_collection({
            "name": "Dict Test",
            "slug": "dict-test",
            "description": "Test description",
            "is_featured": True,
        })
        session.commit()
        c = repo.get_collection(c.id)
        d = _collection_to_dict(c)
        assert d["name"] == "Dict Test"
        assert d["slug"] == "dict-test"
        assert d["description"] == "Test description"
        assert d["is_featured"] is True
        assert isinstance(d["products"], list)
        assert isinstance(d["related"], list)
    print("OK test_collection_to_dict")


def test_service_add_remove_product():
    engine = _setup_db()
    pid = _seed_product(engine)

    svc = SmartCollectionService(db_url="sqlite://")
    svc._engine = engine

    created = svc.create_collection({"name": "Membership Test", "slug": "membership-test"})
    cid = created["id"]

    # Add product
    result = svc.add_product(cid, pid, sort_order=1, badge="Hot")
    assert result is not None
    assert len(result["products"]) == 1

    # Remove product
    result = svc.remove_product(cid, pid)
    assert result is not None
    assert len(result["products"]) == 0
    print("OK test_service_add_remove_product")


def test_service_reorder():
    engine = _setup_db()
    p1 = _seed_product(engine, asin="B0ORDER1")
    p2 = _seed_product(engine, asin="B0ORDER2")

    svc = SmartCollectionService(db_url="sqlite://")
    svc._engine = engine

    c = svc.create_collection({"name": "Reorder Test", "slug": "reorder-test"})
    cid = c["id"]

    svc.add_product(cid, p1, sort_order=10)
    svc.add_product(cid, p2, sort_order=20)

    result = svc.reorder_products(cid, [p2, p1])
    assert result is not None
    assert result["products"][0]["id"] == p2
    print("OK test_service_reorder")


def test_service_featured():
    engine = _setup_db()
    pid = _seed_product(engine)

    svc = SmartCollectionService(db_url="sqlite://")
    svc._engine = engine

    c = svc.create_collection({"name": "Featured Test", "slug": "featured-test"})
    cid = c["id"]

    svc.add_product(cid, pid)
    result = svc.set_product_featured(cid, pid, True)
    assert result is not None
    assert pid in result["featured_product_ids"]
    print("OK test_service_featured")


def test_service_related():
    engine = _setup_db()
    svc = SmartCollectionService(db_url="sqlite://")
    svc._engine = engine

    c1 = svc.create_collection({"name": "Related A", "slug": "related-a"})
    c2 = svc.create_collection({"name": "Related B", "slug": "related-b"})

    result = svc.add_related(c1["id"], c2["id"])
    assert result is not None
    assert len(result["related"]) == 1

    result = svc.remove_related(c1["id"], c2["id"])
    assert result is not None
    assert len(result["related"]) == 0
    print("OK test_service_related")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Running SmartCollection Tests")
    print("=" * 60)
    print()
    tests = [
        test_create_collection,
        test_get_collection,
        test_get_by_slug,
        test_update_collection,
        test_delete_collection,
        test_collection_crud,
        test_product_membership,
        test_related_collections,
        test_rule_evaluation,
        test_search_collections,
        test_visible_collections,
        test_featured_collections,
        test_rule_collections,
        test_service_get_collections,
        test_service_get_collection_by_slug,
        test_service_crud,
        test_collection_to_dict,
        test_service_add_remove_product,
        test_service_reorder,
        test_service_featured,
        test_service_related,
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
