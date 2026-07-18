"""
Scoring Engine
==============
Modular, configurable recommendation scoring for the curated product library.

This module is the single place that turns raw product signals into a
*recommendation score*. It is deliberately decoupled from product_engine's
ranking/badge logic so the weighting scheme can be tuned, made category
specific, and unit tested without touching the rest of the pipeline.

Design principles
----------------
1. Editorial data is OWNED by us and ALWAYS wins. A product flagged
   ``editors_choice`` or given an explicit ``override_rank`` is pinned to the
   top regardless of its automatic score.
2. The internal recommendation score is NEVER surfaced to users. Templates
   only ever see the derived badge, best_for, pros, price and rating. This
   module returns a score for ranking only; callers must not render it.
3. Weights are configurable (defaults documented in the spec) and can be
   overridden per category via SCORING_PRESETS so a helmet can prioritise
   safety/reputation while a chain lube prioritises longevity/reviews.
4. Stateless and O(n) per product, so it scales to thousands of products.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from product_engine import (
    TRUSTED_BRANDS,
    compatibility_priority,
    editorial_signal,
    _as_float,
    _as_int,
)

# ===== Default Weights =====
# Mirrors the product spec. Editorial is intentionally NOT a mathematical
# weight: an editor's score / choice OVERRIDES ranking, badges and best_for
# rather than contributing a blended 10% to the score.
#   Amazon Rating    25%
#   Review Count     20%
#   Brand Reputation 20%
#   Compatibility    15%
#   Features         10%
DEFAULT_WEIGHTS = {
    "amazon_rating": 25,
    "review_count": 20,
    "brand_reputation": 20,
    "compatibility": 15,
    "features": 10,
}


# ===== Category-Specific Presets =====
# Each preset is a dict that OVERRIDES default weights for that category.
# Use case driven emphasis:
#   - helmets:  safety/reputation matters most  -> brand + rating up
#   - gloves:   protection matters most         -> features + rating up
#   - chain_lube: longevity matters most         -> review_count + rating up
#   - phone_mount: stability matters most        -> compatibility + rating up
# Weights are kept on the same 0-100 conceptual scale; the engine normalises
# them internally so cross-category ranking stays comparable.
SCORING_PRESETS = {
    "helmet": {
        "amazon_rating": 30,
        "review_count": 15,
        "brand_reputation": 25,
        "compatibility": 10,
        "features": 10,
        "editorial_score": 10,
    },
    "gloves": {
        "amazon_rating": 25,
        "review_count": 15,
        "brand_reputation": 20,
        "compatibility": 10,
        "features": 20,
        "editorial_score": 10,
    },
    "chain_lube": {
        "amazon_rating": 25,
        "review_count": 25,
        "brand_reputation": 15,
        "compatibility": 10,
        "features": 10,
        "editorial_score": 15,
    },
    "chain_cleaner": {
        "amazon_rating": 25,
        "review_count": 25,
        "brand_reputation": 15,
        "compatibility": 10,
        "features": 10,
        "editorial_score": 15,
    },
    "phone_mount": {
        "amazon_rating": 25,
        "review_count": 15,
        "brand_reputation": 15,
        "compatibility": 25,
        "features": 10,
        "editorial_score": 10,
    },
}

# Map spec-friendly "category emphasis" language to concrete signal boosts.
# These are referenced by documentation/tests so the intent is explicit.
CATEGORY_EMPHASIS = {
    "helmet": "safety",
    "gloves": "protection",
    "chain_lube": "longevity",
    "chain_cleaner": "longevity",
    "phone_mount": "stability",
}


@dataclass
class ScoringConfig:
    """Configurable scoring configuration.

    ``weights`` are normalised internally (so they need not sum to 100).
    ``editorial_override`` controls whether editors_choice / override_rank
    pin products to the top (always True by default per spec requirement #4).
    """

    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    editorial_override: bool = True
    presets: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: dict(SCORING_PRESETS)
    )

    def weights_for(self, category: Optional[str]) -> Dict[str, float]:
        """Return the effective weights for a category (preset merged over defaults)."""
        if not category:
            return dict(self.weights)
        cat = category.strip().lower()
        preset = self.presets.get(cat)
        if not preset:
            return dict(self.weights)
        merged = dict(self.weights)
        merged.update(preset)
        return merged


# Module-level default config (loaded once; overridable via set_default_config).
_CONFIG = ScoringConfig()


def set_default_config(config: ScoringConfig) -> None:
    """Replace the global default scoring config (used for testing / tuning)."""
    global _CONFIG
    _CONFIG = config


def get_default_config() -> ScoringConfig:
    """Return the active global scoring config."""
    return _CONFIG


# ===== Individual Signal Extractors =====
# Each returns a normalised 0-1 value; the weight scales it. This keeps the
# engine linear and the score bounded regardless of category weights.

def _signal_amazon_rating(product: dict) -> float:
    rating = _as_float(product.get("rating", 0))  # 0-5
    return min(1.0, rating / 5.0)


def _signal_review_count(product: dict) -> float:
    reviews = _as_int(product.get("review_count", product.get("reviews", 0)))
    if reviews <= 0:
        return 0.0
    # log10: 10 -> ~0.2, 100 -> 0.4, 1000 -> 0.6, 100000 -> 1.0
    return min(1.0, math.log10(reviews + 1) / 5.0)


def _signal_brand_reputation(product: dict) -> float:
    brand = (product.get("brand") or "").strip().lower()
    return 1.0 if brand in TRUSTED_BRANDS else 0.0


def _signal_compatibility(product: dict, bike: Optional[dict]) -> float:
    if bike is None:
        return 0.5  # neutral when no bike context (counts as present but mid)
    cp = compatibility_priority(product, bike)
    if cp == 0:
        return 0.0  # incompatible
    # priority 1 -> 1.0, priority 5 -> 0.2
    return max(0.0, (6 - cp) / 5.0)


def _signal_features(product: dict) -> float:
    features = product.get("features") or []
    # Editorial "features" list length as a lightweight depth signal (0-1).
    if not features:
        return 0.0
    return min(1.0, len(features) / 5.0)


def _signal_editorial_score(product: dict) -> float:
    # Editor score is stored 0-100 in editorial data; fall back to the
    # derived editorial_signal (0-1, real review content only) so products
    # without a manual score still receive a trustworthy editorial signal.
    raw = product.get("editor_rating", 0)
    if raw:
        try:
            return min(1.0, float(raw) / 100.0)
        except (TypeError, ValueError):
            pass
    return editorial_signal(product)  # 0-1, anchored to real rating


# ===== Core Scoring =====

# Presentation-agnostic reason types. Templates decide how to render these.
#   editorial_choice  -> product hand-picked by an editor
#   editorial_rank    -> product given an explicit editor rank
#   rating            -> Amazon customer rating strength
#   reviews           -> volume of customer reviews (social proof)
#   brand             -> brand reputation
#   compatibility     -> fit for the selected motorcycle
#   features          -> depth of editorial feature list
#   default           -> generic fallback when nothing stronger applies
REASON_TYPE_EDITORIAL_CHOICE = "editorial_choice"
REASON_TYPE_EDITORIAL_RANK = "editorial_rank"
REASON_TYPE_RATING = "rating"
REASON_TYPE_REVIEWS = "reviews"
REASON_TYPE_BRAND = "brand"
REASON_TYPE_COMPATIBILITY = "compatibility"
REASON_TYPE_FEATURES = "features"
REASON_TYPE_DEFAULT = "default"


# Internal recommendation confidence tiers (NOT shown as a number to users).
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"


def _build_reason_objects(
    product: dict,
    category: Optional[str],
    signals: Dict[str, float],
    weights: Dict[str, float],
    editors_choice: bool,
    override_rank: int,
) -> List[Dict[str, Any]]:
    """Build structured, presentation-agnostic reason objects.

    Each object is: ``{"type": str, "value": Any, "priority": int}`` where
    lower ``priority`` means more important. Editorial overrides carry the
    highest priority (lowest number). The remaining reasons are the strongest
    contributing data signals, ordered by weighted contribution, so a UI can
    render "why" without ever seeing the raw numeric score.
    """
    reasons: List[Dict[str, Any]] = []
    priority = 0

    # 1. Editorial override is the decisive reason when present.
    if editors_choice:
        reasons.append({
            "type": REASON_TYPE_EDITORIAL_CHOICE,
            "value": True,
            "priority": priority,
        })
        priority += 1
    elif override_rank > 0:
        reasons.append({
            "type": REASON_TYPE_EDITORIAL_RANK,
            "value": override_rank,
            "priority": priority,
        })
        priority += 1

    # 2. Strongest data signals (by weight * signal contribution).
    contribs = []
    for k, val in signals.items():
        w = weights.get(k, 0.0)
        contribs.append((w * val, k, val))
    contribs.sort(reverse=True)

    rating = _as_float(product.get("rating", 0))
    reviews = _as_int(product.get("review_count", product.get("reviews", 0)))
    brand = (product.get("brand") or "").strip()

    for _, k, val in contribs:
        if val <= 0:
            continue
        if k == "amazon_rating" and rating >= 4.0:
            reasons.append({"type": REASON_TYPE_RATING, "value": rating, "priority": priority})
        elif k == "review_count" and reviews >= 100:
            reasons.append({"type": REASON_TYPE_REVIEWS, "value": reviews, "priority": priority})
        elif k == "brand_reputation" and brand:
            reasons.append({"type": REASON_TYPE_BRAND, "value": brand, "priority": priority})
        elif k == "compatibility" and val >= 0.8:
            reasons.append({"type": REASON_TYPE_COMPATIBILITY, "value": round(val, 2), "priority": priority})
        elif k == "features" and val >= 0.4:
            reasons.append({"type": REASON_TYPE_FEATURES, "value": round(val, 2), "priority": priority})
        else:
            continue
        priority += 1
        if len(reasons) >= 4:
            break

    if not reasons:
        reasons.append({"type": REASON_TYPE_DEFAULT, "value": category or "", "priority": priority})
    return reasons


def _compute_confidence(
    product: dict,
    signals: Dict[str, float],
) -> str:
    """Return an internal confidence tier for the recommendation.

    Derived from four factors (never exposed as a raw number to users):
        * review count  -> more reviews = more reliable social proof
        * rating         -> higher, consistent rating = stronger signal
        * brand reputation -> trusted brand lowers uncertainty
        * feature completeness -> richer editorial data = better understood

    Tiers: high / medium / low. This is an internal quality signal used for
    logging, debugging and future UI hints — not a displayed score.
    """
    reviews = _as_int(product.get("review_count", product.get("reviews", 0)))
    rating = _as_float(product.get("rating", 0))
    brand = (product.get("brand") or "").strip().lower()
    features = product.get("features") or []
    pros = product.get("pros") or []
    cons = product.get("cons") or []

    points = 0

    # Review volume (0-2)
    if reviews >= 1000:
        points += 2
    elif reviews >= 100:
        points += 1

    # Rating strength (0-2)
    if rating >= 4.3:
        points += 2
    elif rating >= 4.0:
        points += 1

    # Brand reputation (0-1)
    if brand in TRUSTED_BRANDS:
        points += 1

    # Feature / editorial completeness (0-1)
    if len(features) >= 3 and pros and cons:
        points += 1

    # Total possible = 6
    if points >= 5:
        return CONFIDENCE_HIGH
    if points >= 3:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def compute_recommendation_score(
    product: dict,
    category: Optional[str] = None,
    bike: Optional[dict] = None,
    config: Optional[ScoringConfig] = None,
) -> Dict[str, Any]:
    """Compute a weighted recommendation score for one product.

    IMPORTANT: Editorial data is KEPT OUT of the mathematical score. An
    editor's score / Editor's Choice / override_rank does not blend into the
    number; instead it OVERRIDES ranking, badges and best_for (see
    ``sort_key_for_ranking`` and ``recommend_for_category``). This keeps the
    auto-score purely data-driven while letting human judgment always win.

    Returns a dict:
        {
            "score": float,        # normalised 0-1 weighted blend (auto only)
            "overridden": bool,    # True if editorial override applies
            "override_rank": int,  # the editor-set rank (0 if none)
            "editors_choice": bool,
            "signals": dict,       # normalised 0-1 per-signal
            "weighted": dict,      # weight*signal per signal
            "reasons": list[dict], # structured WHY objects:
                                  #   {"type", "value", "priority"}
                                  #   presentation-agnostic; templates render
            "confidence": str,     # internal: "high"|"medium"|"low"
        }

    The numeric ``score`` MUST NOT be rendered to end users. It exists only
    for ordering. ``reasons`` are structured objects (type/value/priority) so
    the UI layer decides how to present them. ``confidence`` is an internal
    tier derived from reviews/rating/brand/features, never shown as a number.
    """
    cfg = config or _CONFIG
    weights = cfg.weights_for(category)

    signals = {
        "amazon_rating": _signal_amazon_rating(product),
        "review_count": _signal_review_count(product),
        "brand_reputation": _signal_brand_reputation(product),
        "compatibility": _signal_compatibility(product, bike),
        "features": _signal_features(product),
    }

    total_weight = sum(weights.get(k, 0.0) for k in signals) or 1.0
    weighted = {}
    raw = 0.0
    for k, val in signals.items():
        w = weights.get(k, 0.0)
        contrib = w * val
        weighted[k] = round(contrib, 4)
        raw += contrib
    # Normalise to 0-1 so the score is comparable across weight schemes.
    score = round(raw / total_weight, 4)

    override_rank = _as_int(product.get("override_rank", 0))
    editors_choice = bool(product.get("editors_choice", False))
    overridden = bool(cfg.editorial_override and (editors_choice or override_rank > 0))

    reasons = _build_reason_objects(
        product, category, signals, weights, editors_choice, override_rank
    )
    confidence = _compute_confidence(product, signals)

    return {
        "score": score,
        "overridden": overridden,
        "override_rank": override_rank,
        "editors_choice": editors_choice,
        "signals": signals,
        "weighted": weighted,
        "reasons": reasons,        # structured objects: {type, value, priority}
        "confidence": confidence,  # internal: high | medium | low
    }


def is_editorial_override(product: dict, config: Optional[ScoringConfig] = None) -> bool:
    """Return True if a product is manually pinned above automatic rankings."""
    cfg = config or _CONFIG
    if not cfg.editorial_override:
        return False
    return bool(product.get("editors_choice") or _as_int(product.get("override_rank", 0)) > 0)


def sort_key_for_ranking(
    product: dict,
    precomputed: Optional[Dict[str, Any]] = None,
    category: Optional[str] = None,
    bike: Optional[dict] = None,
    config: Optional[ScoringConfig] = None,
) -> tuple:
    """Return a sort key (higher == better) that honours editorial overrides.

    Editorial overrides always outrank automatic scores:
      * editors_choice  -> top tier
      * override_rank N -> tier ordered by N (lower N = higher)
      * everything else-> sorted by computed score

    The key is a tuple so Python sorts overrides above scores deterministically.
    """
    result = precomputed or compute_recommendation_score(product, category, bike, config)
    if result["editors_choice"]:
        return (2, 0, result["score"])          # highest tier, rank 0
    if result["override_rank"] > 0:
        return (1, -result["override_rank"], result["score"])  # tier 1, lower rank first
    return (0, 0, result["score"])              # automatic tier
