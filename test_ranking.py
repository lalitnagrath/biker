#!/usr/bin/env python3
"""
Test script for product_ranking module
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from product_ranking import (
    extract_rating,
    extract_review_count,
    extract_bestseller_rank,
    extract_editor_score,
    extract_price_history,
    calculate_quality_score,
    calculate_rating_score,
    calculate_popularity_score,
    calculate_discount_score,
    calculate_keyword_score,
    calculate_bestseller_score,
    calculate_editor_score,
    calculate_price_history_score,
    rank_products,
    get_top_products,
    DEAL_FOCUSED_WEIGHTS,
    QUALITY_FOCUSED_WEIGHTS,
    BALANCED_WEIGHTS
)

def test_extract_rating():
    """Test rating extraction"""
    print("Testing extract_rating()...")
    
    # Test with direct rating field
    product1 = {'rating': 4.5}
    assert extract_rating(product1) == 4.5, "Failed to extract direct rating"
    
    # Test with nested customerReview
    product2 = {'customerReview': {'rating': 3.8}}
    assert extract_rating(product2) == 3.8, "Failed to extract nested rating"
    
    # Test with no rating
    product3 = {'name': 'Test Product'}
    assert extract_rating(product3) == 0.0, "Failed to handle missing rating"
    
    # Test with invalid rating
    product4 = {'rating': 'N/A'}
    assert extract_rating(product4) == 0.0, "Failed to handle invalid rating"
    
    print("✓ extract_rating() tests passed")


def test_extract_review_count():
    """Test review count extraction"""
    print("Testing extract_review_count()...")
    
    # Test with direct field
    product1 = {'review_count': 150}
    assert extract_review_count(product1) == 150, "Failed to extract review_count"
    
    # Test with reviews field
    product2 = {'reviews': 2500}
    assert extract_review_count(product2) == 2500, "Failed to extract reviews"
    
    # Test with nested structure
    product3 = {'customerReview': {'count': 500}}
    assert extract_review_count(product3) == 500, "Failed to extract nested review count"
    
    # Test with no reviews
    product4 = {'name': 'Test'}
    assert extract_review_count(product4) == 0, "Failed to handle missing reviews"
    
    print("✓ extract_review_count() tests passed")


def test_calculate_discount_score():
    """Test discount score calculation"""
    print("Testing calculate_discount_score()...")
    
    # Test with _savings_pct field
    product1 = {'_savings_pct': 50.0}
    score1 = calculate_discount_score(product1)
    assert score1 == 1.0, f"Expected 1.0 for 50% discount, got {score1}"
    
    # Test with 25% discount
    product2 = {'_savings_pct': 25.0}
    score2 = calculate_discount_score(product2)
    assert score2 == 0.5, f"Expected 0.5 for 25% discount, got {score2}"
    
    # Test with no discount
    product3 = {}
    score3 = calculate_discount_score(product3)
    assert score3 == 0.0, f"Expected 0.0 for no discount, got {score3}"
    
    print("✓ calculate_discount_score() tests passed")


def test_calculate_quality_score():
    """Test quality score calculation"""
    print("Testing calculate_quality_score()...")
    
    # Test with default weights (discount only)
    product1 = {'_savings_pct': 50.0}
    score1 = calculate_quality_score(product1)
    assert score1 == 1.0, f"Expected 1.0, got {score1}"
    assert '_quality_score' in product1, "Quality score not stored in product"
    
    # Test with custom weights
    product2 = {
        '_savings_pct': 30.0,
        'rating': 4.5,
        'review_count': 1000
    }
    weights = {
        'discount': 1.0,
        'rating': 1.0,
        'review_count': 1.0
    }
    score2 = calculate_quality_score(product2, weights=weights)
    assert score2 > 0, f"Expected positive score, got {score2}"
    
    print("✓ calculate_quality_score() tests passed")


def test_rank_products():
    """Test product ranking"""
    print("Testing rank_products()...")
    
    products = [
        {'_savings_pct': 10.0, 'name': 'Product A'},
        {'_savings_pct': 50.0, 'name': 'Product B'},
        {'_savings_pct': 30.0, 'name': 'Product C'},
    ]
    
    ranked = rank_products(products, reverse=True)
    
    # Check that products are sorted by quality score (discount)
    assert ranked[0]['name'] == 'Product B', "Highest discount should be first"
    assert ranked[1]['name'] == 'Product C', "Medium discount should be second"
    assert ranked[2]['name'] == 'Product A', "Lowest discount should be third"
    
    # Check that _quality_score was added
    for product in ranked:
        assert '_quality_score' in product, "Quality score not added to product"
    
    print("✓ rank_products() tests passed")


def test_preset_weights():
    """Test preset weight configurations"""
    print("Testing preset weights...")
    
    # Verify all presets exist and have required keys
    for preset_name, preset in [
        ('DEAL_FOCUSED_WEIGHTS', DEAL_FOCUSED_WEIGHTS),
        ('QUALITY_FOCUSED_WEIGHTS', QUALITY_FOCUSED_WEIGHTS),
        ('BALANCED_WEIGHTS', BALANCED_WEIGHTS)
    ]:
        assert 'discount' in preset, f"{preset_name} missing 'discount' key"
        assert 'rating' in preset, f"{preset_name} missing 'rating' key"
        assert 'review_count' in preset, f"{preset_name} missing 'review_count' key"
    
    print("✓ Preset weights tests passed")


def test_extensibility():
    """Test that the system is extensible with new signals"""
    print("Testing extensibility...")
    
    # Test bestseller rank extraction
    product1 = {'bestsellerRank': 1234}
    rank = extract_bestseller_rank(product1)
    assert rank == 1234, f"Failed to extract bestseller rank: {rank}"
    
    # Test editor score extraction
    product2 = {'editor_score': 85}
    score = extract_editor_score(product2)
    assert score == 85.0, f"Failed to extract editor score: {score}"
    
    # Test price history extraction
    product3 = {
        'price_history': {
            'current': 100.0,
            'lowest': 80.0,
            'highest': 150.0
        }
    }
    history = extract_price_history(product3)
    assert history is not None, "Failed to extract price history"
    assert history['current'] == 100.0, "Price history current price incorrect"
    
    # Test that calculate_quality_score can use these new signals
    product4 = {
        '_savings_pct': 20.0,
        'bestsellerRank': 500,
        'editor_score': 90
    }
    weights = {
        'discount': 1.0,
        'bestseller_rank': 1.0,
        'editor_score': 1.0
    }
    score = calculate_quality_score(product4, weights=weights)
    assert score > 0, "Quality score should be positive with new signals"
    
    print("✓ Extensibility tests passed")


def test_bike_deals_json():
    """Test with actual bike-deals.json data"""
    print("Testing with bike-deals.json...")
    
    import json
    
    try:
        with open('bike-deals.json', 'r', encoding='utf-8') as f:
            products = json.load(f)
        
        if not products:
            print("⚠ bike-deals.json is empty, skipping")
            return
        
        # Test ranking on real data
        ranked = rank_products(products[:10], reverse=True)  # Test with first 10
        
        # Verify all have quality scores
        for product in ranked:
            assert '_quality_score' in product, f"Product {product.get('asin')} missing quality score"
        
        # Verify they're sorted
        scores = [p.get('_quality_score', 0.0) for p in ranked]
        assert scores == sorted(scores, reverse=True), "Products not sorted by quality score"
        
        print(f"✓ Successfully ranked {len(ranked)} products from bike-deals.json")
        
    except FileNotFoundError:
        print("⚠ bike-deals.json not found, skipping")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Running Product Ranking Module Tests")
    print("=" * 60)
    print()
    
    try:
        test_extract_rating()
        test_extract_review_count()
        test_calculate_discount_score()
        test_calculate_quality_score()
        test_rank_products()
        test_preset_weights()
        test_extensibility()
        test_bike_deals_json()
        
        print()
        print("=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"✗ Test failed: {e}")
        print("=" * 60)
        return 1
    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())