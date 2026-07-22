"""
Product Ranking Module
======================
Modular scoring system for ranking products by quality.

This module provides helper functions to extract various product signals
and calculate composite scores. The system is designed to be easily extensible
with new ranking factors like ratings, review count, bestseller rank,
manual editor score, and price history.

Usage:
    from product_ranking import calculate_quality_score
    
    quality_score = calculate_quality_score(product)
    products.sort(key=lambda x: calculate_quality_score(x), reverse=True)
"""

from typing import Dict, Any, Optional, List
import math


# ===== Signal Extractors =====

def extract_rating(product: Dict[str, Any]) -> float:
    """
    Extract the product rating from the product data.
    
    Args:
        product: Product dictionary containing rating information
        
    Returns:
        float: Rating value (typically 0-5 scale), 0.0 if not available
    """
    # Pre-populated _rating from Creators API (SearchItems response)
    rating = product.get('_rating')
    if rating is not None:
        try:
            return float(rating)
        except (TypeError, ValueError):
            pass
    
    # Try common field names for ratings
    rating = product.get('rating')
    if rating is not None:
        try:
            return float(rating)
        except (TypeError, ValueError):
            pass
    
    # Try nested structures (Amazon API format)
    customer_review = product.get('customerReview') or product.get('customerReviews') or {}
    if isinstance(customer_review, dict):
        rating = customer_review.get('rating') or customer_review.get('starRating')
        if rating is not None:
            try:
                return float(rating)
            except (TypeError, ValueError):
                pass
    
    return 0.0


def extract_review_count(product: Dict[str, Any]) -> int:
    """
    Extract the number of customer reviews from the product data.
    
    Args:
        product: Product dictionary containing review information
        
    Returns:
        int: Number of reviews, 0 if not available
    """
    # Pre-populated _review_count from Creators API (SearchItems response)
    count = product.get('_review_count')
    if count is not None:
        try:
            return int(count)
        except (TypeError, ValueError):
            pass
    
    # Try common field names
    count = product.get('reviewCount') or product.get('review_count') or product.get('reviews')
    if count is not None:
        try:
            return int(count)
        except (TypeError, ValueError):
            pass
    
    # Try nested structures
    customer_review = product.get('customerReview') or product.get('customerReviews') or {}
    if isinstance(customer_review, dict):
        count = customer_review.get('count') or customer_review.get('reviewCount')
        if count is not None:
            try:
                return int(count)
            except (TypeError, ValueError):
                pass
    
    return 0


def extract_bestseller_rank(product: Dict[str, Any]) -> Optional[int]:
    """
    Extract the bestseller rank from the product data.
    
    Args:
        product: Product dictionary containing bestseller rank information
        
    Returns:
        Optional[int]: Bestseller rank (lower is better), None if not available
    """
    rank = product.get('bestsellerRank') or product.get('bestseller_rank')
    if rank is not None:
        try:
            return int(rank)
        except (TypeError, ValueError):
            pass
    return None


def extract_editor_score(product: Dict[str, Any]) -> float:
    """
    Extract the manual editor score from the product data.
    
    Args:
        product: Product dictionary containing editor score information
        
    Returns:
        float: Editor score (typically 0-100 scale), 0.0 if not available
    """
    score = product.get('editorScore') or product.get('editor_score') or product.get('editor_rating')
    if score is not None:
        try:
            return float(score)
        except (TypeError, ValueError):
            pass
    return 0.0


def extract_price_history(product: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """
    Extract price history information from the product data.
    
    Args:
        product: Product dictionary containing price history
        
    Returns:
        Optional[Dict]: Dictionary with 'current', 'lowest', 'highest' prices,
                       None if not available
    """
    history = product.get('priceHistory') or product.get('price_history')
    if isinstance(history, dict):
        return {
            'current': history.get('current'),
            'lowest': history.get('lowest'),
            'highest': history.get('highest')
        }
    return None


# ===== Score Calculators =====

# ===== Brand Database =====

# Motorcycle/riding gear brand recognition scores (0.0-1.0)
BRAND_SCORES = {
    # Premium/High-end brands
    'alpinestars': 1.0, 'dainese': 1.0, 'shoei': 1.0, 'arai': 1.0, 'agv': 1.0,
    'rev\'it': 1.0, 'revit': 1.0, 'klim': 1.0, 'schuberth': 1.0, 'shark': 1.0,
    'held': 0.9,
    # Mid-range brands
    'royal enfield': 0.8, 'studds': 0.7, 'ls2': 0.8, 'smk': 0.7, 'vega': 0.6,
    'axor': 0.7, 'mt': 0.7, 'rynox': 0.8, 'viatierra': 0.7, 'korda': 0.6,
    'spg': 0.6, 'solace': 0.7, 'tvs': 0.7, 'hero': 0.7, 'bajaj': 0.7,
    # Budget brands
    'steelbird': 0.5, 'glide': 0.5, 'cross': 0.5, 'woca': 0.4, 'motul': 0.8,
    'castrol': 0.8, 'liqui moly': 0.8, 'shell': 0.8, 'hp': 0.7,
    # Global motorcycle gear
    'icon': 0.8, 'scorpion': 0.8, 'hjc': 0.8, 'bell': 0.8, 'nolan': 0.8,
    'x-lite': 0.8, 'caberg': 0.7, 'louis': 0.6, 'wunderlich': 0.8,
    'touratech': 0.9, 'givi': 0.8, 'shad': 0.7, 'sw-motech': 0.8,
    'oxford': 0.7, 'richa': 0.7, 'spada': 0.6, 'frank thomas': 0.6,
    'duke': 0.4, 'orion': 0.4, 'autofy': 0.3, 'kings': 0.3,
}

def calculate_brand_score(product: Dict[str, Any]) -> float:
    title = ''
    item_info = product.get('itemInfo') or {}
    title_data = item_info.get('title')
    if isinstance(title_data, dict):
        title = title_data.get('displayValue', '')
    elif isinstance(title_data, str):
        title = title_data

    if not title:
        return 0.0

    title_lower = title.lower()
    best_score = 0.0
    for brand, score in BRAND_SCORES.items():
        if brand in title_lower:
            best_score = max(best_score, score)
    return best_score


def calculate_quality_score(
    product: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None
) -> float:
    """
    Calculate a composite quality score for a product.
    
    This is the main entry point for ranking products. It combines multiple
    signals into a single quality score. The default implementation uses
    discount percentage as the primary factor, but can be extended with
    additional signals.
    
    Args:
        product: Product dictionary with product information
        weights: Optional dictionary of weights for different factors.
                Default weights:
                - discount: 1.0
                - rating: 0.0 (disabled by default, enable by setting weight > 0)
                - review_count: 0.0 (disabled by default)
                - bestseller_rank: 0.0 (disabled by default)
                - editor_score: 0.0 (disabled by default)
                - price_history: 0.0 (disabled by default)
        
    Returns:
        float: Quality score (higher is better)
    """
    if weights is None:
        weights = {
            'discount': 1.0,
            'rating': 0.0,
            'review_count': 0.0,
            'bestseller_rank': 0.0,
            'editor_score': 0.0,
            'price_history': 0.0
        }
    
    scores = {}
    
    # Discount score (primary factor)
    if weights.get('discount', 0) > 0:
        scores['discount'] = calculate_discount_score(product) * weights['discount']
    
    # Rating score
    if weights.get('rating', 0) > 0:
        scores['rating'] = calculate_rating_score(product) * weights['rating']
    
    # Review count score
    if weights.get('review_count', 0) > 0:
        scores['review_count'] = calculate_popularity_score(product) * weights['review_count']
    
    # Bestseller rank score
    if weights.get('bestseller_rank', 0) > 0:
        scores['bestseller_rank'] = calculate_bestseller_score(product) * weights['bestseller_rank']
    
    # Editor score
    if weights.get('editor_score', 0) > 0:
        scores['editor_score'] = calculate_editor_score(product) * weights['editor_score']
    
    # Price history score
    if weights.get('price_history', 0) > 0:
        scores['price_history'] = calculate_price_history_score(product) * weights['price_history']
    
    # Sum all weighted scores
    total_score = sum(scores.values())
    
    # Add the score to the product for later use
    product['_quality_score'] = total_score
    
    return total_score


def calculate_rating_score(product: Dict[str, Any]) -> float:
    """
    Calculate a normalized score based on product rating.
    
    Args:
        product: Product dictionary
        
    Returns:
        float: Normalized rating score (0.0-1.0)
    """
    rating = extract_rating(product)
    if rating <= 0:
        return 0.0
    
    # Normalize to 0-1 scale (assuming 5-star max)
    # Weight heavily toward 4+ star products
    if rating >= 4.5:
        return 1.0
    elif rating >= 4.0:
        return 0.8
    elif rating >= 3.5:
        return 0.6
    elif rating >= 3.0:
        return 0.4
    elif rating >= 2.0:
        return 0.2
    else:
        return 0.1


def calculate_popularity_score(product: Dict[str, Any]) -> float:
    """
    Calculate a normalized score based on review count (popularity).
    
    Uses logarithmic scaling to handle wide range of review counts:
    - 10 reviews -> ~0.2
    - 100 reviews -> ~0.4
    - 1000 reviews -> ~0.6
    - 10000 reviews -> ~0.8
    - 100000 reviews -> 1.0
    
    Args:
        product: Product dictionary
        
    Returns:
        float: Normalized popularity score (0.0-1.0)
    """
    review_count = extract_review_count(product)
    if review_count <= 0:
        return 0.0
    
    # Logarithmic scaling
    # log10(10) = 1, log10(100) = 2, log10(1000) = 3, etc.
    # Normalize to 0-1 range (assuming max ~100k reviews = 1.0)
    score = math.log10(review_count + 1) / 5.0
    return min(1.0, max(0.0, score))


def calculate_discount_score(product: Dict[str, Any]) -> float:
    """
    Calculate a normalized score based on discount percentage.
    
    Args:
        product: Product dictionary
        
    Returns:
        float: Normalized discount score (0.0-1.0)
    """
    # Use the existing _savings_pct field if available
    savings_pct = product.get('_savings_pct', 0.0)
    
    # If not available, try to extract from offers
    if savings_pct == 0.0:
        offers = (product.get('offersV2') or {}).get('listings') or []
        for listing in offers:
            price = listing.get('price') or {}
            savings = price.get('savings') or {}
            pct = savings.get('percentage')
            if pct is not None:
                try:
                    savings_pct = max(savings_pct, float(pct))
                except (TypeError, ValueError):
                    pass
    
    # Normalize to 0-1 scale (assuming 50% discount = 1.0)
    # This can be adjusted based on typical discount ranges
    normalized = min(1.0, savings_pct / 50.0)
    return max(0.0, normalized)


def calculate_keyword_score(product: Dict[str, Any], target_keywords: List[str]) -> float:
    """
    Calculate a score based on keyword relevance.
    
    Args:
        product: Product dictionary
        target_keywords: List of keywords to match against product title
        
    Returns:
        float: Keyword relevance score (0.0-1.0)
    """
    if not target_keywords:
        return 0.0
    
    title = ''
    item_info = product.get('itemInfo') or {}
    title_data = item_info.get('title')
    
    if isinstance(title_data, dict):
        title = title_data.get('displayValue', '')
    elif isinstance(title_data, str):
        title = title_data
    
    if not title:
        return 0.0
    
    title_lower = title.lower()
    matches = sum(1 for keyword in target_keywords if keyword.lower() in title_lower)
    
    # Normalize: all keywords matched = 1.0, none matched = 0.0
    if len(target_keywords) > 0:
        return min(1.0, matches / len(target_keywords))
    return 0.0


def calculate_bestseller_score(product: Dict[str, Any]) -> float:
    """
    Calculate a normalized score based on bestseller rank.
    
    Lower rank numbers are better (e.g., rank 1 is best).
    
    Args:
        product: Product dictionary
        
    Returns:
        float: Normalized bestseller score (0.0-1.0)
    """
    rank = extract_bestseller_rank(product)
    if rank is None or rank <= 0:
        return 0.0
    
    # Normalize: rank 1 = 1.0, rank 1000 = 0.5, rank 10000 = 0.1
    # Using inverse logarithmic scaling
    if rank <= 10:
        return 1.0
    elif rank <= 100:
        return 0.8
    elif rank <= 1000:
        return 0.6
    elif rank <= 10000:
        return 0.4
    elif rank <= 100000:
        return 0.2
    else:
        return 0.1


def calculate_editor_score(product: Dict[str, Any]) -> float:
    """
    Calculate a normalized score based on manual editor score.
    
    Args:
        product: Product dictionary
        
    Returns:
        float: Normalized editor score (0.0-1.0)
    """
    score = extract_editor_score(product)
    if score <= 0:
        return 0.0
    
    # Normalize to 0-1 scale (assuming 0-100 scale)
    return min(1.0, score / 100.0)


def calculate_price_history_score(product: Dict[str, Any]) -> float:
    """
    Calculate a score based on price history (is this a good deal historically?).
    
    Args:
        product: Product dictionary
        
    Returns:
        float: Price history score (0.0-1.0)
    """
    history = extract_price_history(product)
    if not history:
        return 0.0
    
    current = history.get('current')
    lowest = history.get('lowest')
    
    if not current or not lowest or lowest <= 0:
        return 0.0
    
    try:
        current_float = float(current)
        lowest_float = float(lowest)
        
        if current_float <= 0:
            return 0.0
        
        # Score based on how close current price is to historical low
        # If current == lowest, score = 1.0
        # If current is 2x the lowest, score = 0.5
        ratio = lowest_float / current_float
        return min(1.0, max(0.0, ratio))
    except (TypeError, ValueError):
        return 0.0


# ===== Batch Operations =====

def rank_products(
    products: List[Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
    reverse: bool = True
) -> List[Dict[str, Any]]:
    """
    Rank a list of products by quality score.
    
    Args:
        products: List of product dictionaries
        weights: Optional weights for scoring factors
        reverse: If True, sort descending (best first). If False, ascending.
        
    Returns:
        List[Dict]: Products sorted by quality score
    """
    # Calculate scores for all products
    for product in products:
        calculate_quality_score(product, weights)
    
    # Sort by quality score
    return sorted(products, key=lambda x: x.get('_quality_score', 0.0), reverse=reverse)


def get_top_products(
    products: List[Dict[str, Any]],
    top_n: int = 10,
    weights: Optional[Dict[str, float]] = None
) -> List[Dict[str, Any]]:
    """
    Get the top N products by quality score.
    
    Args:
        products: List of product dictionaries
        top_n: Number of top products to return
        weights: Optional weights for scoring factors
        
    Returns:
        List[Dict]: Top N products sorted by quality score
    """
    ranked = rank_products(products, weights=weights, reverse=True)
    return ranked[:top_n]


# ===== Preset Configurations =====

# Preset for deal-focused ranking (discount-heavy)
DEAL_FOCUSED_WEIGHTS = {
    'discount': 1.0,
    'rating': 0.3,
    'review_count': 0.2,
    'bestseller_rank': 0.0,
    'editor_score': 0.0,
    'price_history': 0.0
}

# Preset for quality-focused ranking
QUALITY_FOCUSED_WEIGHTS = {
    'discount': 0.3,
    'rating': 1.0,
    'review_count': 0.5,
    'bestseller_rank': 0.3,
    'editor_score': 0.5,
    'price_history': 0.2
}

# Preset for balanced ranking
BALANCED_WEIGHTS = {
    'discount': 0.7,
    'rating': 0.5,
    'review_count': 0.3,
    'bestseller_rank': 0.2,
    'editor_score': 0.3,
    'price_history': 0.2
}