"""
Tests for RecommendationEngine.

All DB-dependent services are mocked.
"""

import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))

# Mock DB-dependent services BEFORE importing RecommendationEngine
mock_module = type(sys)('db.product_service')
mock_module.ProductService = MagicMock
sys.modules['db.product_service'] = mock_module

mock_smart = type(sys)('db.smart_collections')
mock_smart.SmartCollectionService = MagicMock
sys.modules['db.smart_collections'] = mock_smart

from db.recommendation_engine import (
    RecommendationEngine,
    GROUP_CATEGORIES,
)


def make_engine():
    """Return a RecommendationEngine with mocked services."""
    engine = RecommendationEngine(db_url="sqlite://")
    # Replace real services with mocks
    engine._product_service = MagicMock()
    engine._product_service.load_all.return_value = []
    engine._product_service.get_product.return_value = None
    engine._product_service.get_motorcycle_products.return_value = []
    engine._product_service.get_products_by_category.return_value = []
    engine._product_service.get_related_products.return_value = []

    engine._collection_service = MagicMock()
    engine._collection_service.get_visible_collections.return_value = []
    engine._collection_service.get_featured_collections.return_value = []
    return engine


def test_group_categories_structure():
    assert "Protection" in GROUP_CATEGORIES
    assert "Style" in GROUP_CATEGORIES
    assert "Lighting" in GROUP_CATEGORIES
    assert "Touring" in GROUP_CATEGORIES
    assert "Maintenance" in GROUP_CATEGORIES
    print("OK test_group_categories_structure")


def test_group_categories_content():
    assert "Helmet" in GROUP_CATEGORIES["Protection"]
    assert "Disc Lock" in GROUP_CATEGORIES["Protection"]
    assert "Jackets" in GROUP_CATEGORIES["Style"]
    assert "Gloves" in GROUP_CATEGORIES["Style"]
    assert "Saddle Bag" in GROUP_CATEGORIES["Touring"]
    assert "Engine Oil" in GROUP_CATEGORIES["Maintenance"]
    assert "Chain Lube" in GROUP_CATEGORIES["Maintenance"]
    print("OK test_group_categories_content")


def test_get_group_categories():
    engine = make_engine()
    categories = engine.get_group_categories()
    assert categories == GROUP_CATEGORIES
    print("OK test_get_group_categories")


def test_get_recommendation_groups():
    engine = make_engine()
    groups = engine.get_recommendation_groups()
    assert "Protection" in groups
    assert "Style" in groups
    assert "Lighting" in groups
    assert "Touring" in groups
    assert "Maintenance" in groups
    assert len(groups) == 5
    print("OK test_get_recommendation_groups")


def test_recommend_for_product_empty():
    engine = make_engine()
    result = engine.recommend_for_product("nonexistent-product")
    assert "groups" in result
    assert "context" in result
    assert result["context"]["slug"] == "nonexistent-product"
    assert result["context"]["type"] == "product"
    assert result["total_products"] == 0
    for group_name in GROUP_CATEGORIES:
        assert group_name in result["groups"]
        assert isinstance(result["groups"][group_name], list)
        assert len(result["groups"][group_name]) == 0
    print("OK test_recommend_for_product_empty")


def test_recommend_for_category_empty():
    engine = make_engine()
    result = engine.recommend_for_category("Nonexistent Category")
    assert "groups" in result
    assert result["context"]["slug"] == "Nonexistent Category"
    assert result["context"]["type"] == "category"
    for group_name in GROUP_CATEGORIES:
        assert group_name in result["groups"]
    print("OK test_recommend_for_category_empty")


def test_recommend_for_motorcycle_empty():
    engine = make_engine()
    result = engine.recommend_for_motorcycle("nonexistent-bike")
    assert "groups" in result
    assert result["context"]["slug"] == "nonexistent-bike"
    assert result["context"]["type"] == "motorcycle"
    for group_name in GROUP_CATEGORIES:
        assert group_name in result["groups"]
    print("OK test_recommend_for_motorcycle_empty")


def test_max_per_group():
    engine = make_engine()
    result = engine.recommend_for_product("nonexistent", max_per_group=4)
    for group_name in GROUP_CATEGORIES:
        assert len(result["groups"][group_name]) <= 4
    print("OK test_max_per_group")


def main():
    print("=" * 60)
    print("Running RecommendationEngine Tests")
    print("=" * 60)
    print()
    tests = [
        test_group_categories_structure,
        test_group_categories_content,
        test_get_group_categories,
        test_get_recommendation_groups,
        test_recommend_for_product_empty,
        test_recommend_for_category_empty,
        test_recommend_for_motorcycle_empty,
        test_max_per_group,
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
