"""
RecommendationEngine — produces grouped product recommendations
for a given motorcycle, category, or product context.

Recommendation groups:
  - Protection (helmets, guards, locks)
  - Style (jackets, gloves, decals)
  - Lighting (headlights, indicators, accessories)
  - Touring (luggage, GPS, comfort)
  - Maintenance (oil, lube, cleaners, inflators)

Uses ProductService for flat product dicts and SmartCollectionService
for rule-based collection membership.
"""

import os
from typing import Any, Dict, List, Optional

from db.product_service import ProductService
from db.smart_collections import SmartCollectionService

DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")


# Mapping of recommendation group -> canonical category names
GROUP_CATEGORIES: Dict[str, List[str]] = {
    "Protection": [
        "Helmet", "Disc Lock", "Chain Lock", "Alarm",
        "GPS Tracker", "Crash Guard", "Leg Guard",
        "Knee Guard", "Slider",
    ],
    "Style": [
        "Jackets", "Gloves", "Decals", "Seat Cover",
        "Handlebar Grip", "Mirror", "Footrest",
    ],
    "Lighting": [
        "Headlight", "Indicator", "Fog Light",
        "LED Light", "Underglow",
    ],
    "Touring": [
        "Saddle Bag", "Tail Bag", "Tank Bag",
        "GPS Tracker", "Tyre Inflator", "Windshield",
        "Backrest", "Luggage Rack",
    ],
    "Maintenance": [
        "Engine Oil", "Chain Lube", "Chain Cleaner",
        "Tyre Inflator", "Tool Kit", "Polish",
        "Bike Cover", "Charger",
    ],
}


class RecommendationEngine:

    def __init__(self, db_url: Optional[str] = None):
        self._db_url = db_url or DB_URL
        self._product_service = ProductService(db_url)
        self._collection_service = SmartCollectionService(db_url)

    def recommend_for_motorcycle(
        self, bike_slug: str, max_per_group: int = 4
    ) -> Dict[str, Any]:
        """Return grouped recommendations for a motorcycle."""
        products = self._product_service.load_all()
        bike_products = self._product_service.get_motorcycle_products(bike_slug)

        # Build product lookup by ASIN for compatibility check
        bike_asins = {p.get("asin") for p in bike_products if p.get("asin")}

        return self._build_grouped_recommendations(
            all_products=products,
            base_products=bike_products,
            match_fn=lambda p: p.get("asin") in bike_asins,
            max_per_group=max_per_group,
            context={"type": "motorcycle", "slug": bike_slug},
        )

    def recommend_for_category(
        self, category: str, max_per_group: int = 4
    ) -> Dict[str, Any]:
        """Return grouped recommendations for a product category."""
        products = self._product_service.load_all()
        cat_products = self._product_service.get_products_by_category(category)

        return self._build_grouped_recommendations(
            all_products=products,
            base_products=cat_products,
            match_fn=lambda p: p.get("category", "").lower() == category.lower(),
            max_per_group=max_per_group,
            context={"type": "category", "slug": category},
        )

    def recommend_for_product(
        self, product_slug: str, max_per_group: int = 4
    ) -> Dict[str, Any]:
        """Return grouped recommendations for a product page."""
        products = self._product_service.load_all()
        product = self._product_service.get_product(product_slug)
        if not product:
            return {
                "groups": {group: [] for group in GROUP_CATEGORIES},
                "context": {"type": "product", "slug": product_slug},
                "total_products": 0,
            }

        related = self._product_service.get_related_products(
            product_slug, max_results=20
        )

        return self._build_grouped_recommendations(
            all_products=products,
            base_products=related,
            match_fn=lambda p: p.get("slug") != product_slug,
            max_per_group=max_per_group,
            context={"type": "product", "slug": product_slug},
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_grouped_recommendations(
        self,
        all_products: List[dict],
        base_products: List[dict],
        match_fn,
        max_per_group: int,
        context: dict,
    ) -> Dict[str, Any]:
        """Build the grouped recommendation structure."""
        from product_engine import ranking_score, enforce_brand_diversity

        base_by_asin = {p.get("asin"): p for p in base_products if p.get("asin")}

        # Load collections for enrichment
        collections = self._collection_service.get_visible_collections()
        collection_map = {}
        for col in collections:
            for p in col.get("products", []):
                asin = p.get("asin")
                if asin:
                    collection_map.setdefault(asin, []).append(
                        {
                            "id": col["id"],
                            "name": col["name"],
                            "slug": col["slug"],
                        }
                    )

        result = {}
        for group_name, categories in GROUP_CATEGORIES.items():
            group_products = []
            seen_asins = set()

            for cat in categories:
                for p in all_products:
                    asin = p.get("asin")
                    if not asin or asin in seen_asins:
                        continue
                    if not match_fn(p):
                        continue
                    if p.get("category", "").lower() != cat.lower():
                        continue
                    seen_asins.add(asin)

                    enriched = dict(p)
                    enriched["_collection_membership"] = collection_map.get(asin, [])
                    enriched["_ranking_score"] = ranking_score(p)
                    group_products.append(enriched)

            # Sort by ranking score
            group_products.sort(
                key=lambda x: x.get("_ranking_score", 0), reverse=True
            )

            # Enforce brand diversity
            group_products = enforce_brand_diversity(
                group_products, max_per_brand=2
            )

            # Apply limit
            group_products = group_products[:max_per_group]

            # Clean up internal fields
            for p in group_products:
                p.pop("_collection_membership", None)
                p.pop("_ranking_score", None)

            result[group_name] = group_products

        return {
            "groups": result,
            "context": context,
            "total_products": sum(len(v) for v in result.values()),
        }

    def get_group_categories(self) -> Dict[str, List[str]]:
        """Return the category mapping used by the engine."""
        return dict(GROUP_CATEGORIES)

    def get_recommendation_groups(self) -> List[str]:
        """Return the list of recommendation group names."""
        return list(GROUP_CATEGORIES.keys())
