"""
Heuristic product classifier for imported Amazon products.

Implements the BikeReview India AI classification rules as a deterministic,
keyword-driven classifier.  For each product it determines:

    category                -> one of CATEGORIES (most specific possible)
    collections             -> one or more of COLLECTIONS (additive)
    type                    -> "Universal" | "Bike Specific" | "Unknown"
    compatible_motorcycles  -> bike names extracted from the title/text
    confidence              -> "High" | "Medium" | "Low"

The classifier is pure: it takes text and an optional list of known bikes and
returns a dict, so it is easy to unit test and does not touch the database.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Taxonomy (authoritative, do not invent new values)
# ---------------------------------------------------------------------------

CATEGORIES: List[str] = [
    "Mirror", "Mobile Holder", "Helmet", "Riding Jacket", "Gloves",
    "Tank Pad", "Lever", "Crash Guard", "Windshield", "LED Indicator",
    "Tail Light", "Fog Light", "Seat Cover", "Tank Bag", "Saddle Bag",
    "Chain Cleaner", "Chain Lube", "Engine Oil", "Phone Charger",
    "Security Lock", "GPS Tracker", "Air Pump", "Toolkit", "Cleaning Kit",
    # Additional types found in imported data (the spec list is "examples",
    # the rule is "most specific category possible").
    "Bike Cover", "Bike Alarm", "Handlebar Grip", "Dash Cam", "Horn",
    "Ear Plugs", "Action Camera Mount", "Footrest", "Tail Bag",
    "Riding Pants", "Headlight", "Motorcycle",
]

COLLECTIONS: List[str] = [
    "Bike Styling", "Lighting", "Protection", "Performance", "Touring",
    "Security", "Cleaning", "Maintenance", "Rider Gear", "Luggage",
    "Navigation & Charging", "Comfort", "Adventure", "Daily Commute",
    "Premium Upgrades", "Cafe Racer", "Off Road",
]

# Category keywords.  Phrases must be ordered most-specific first so the
# longest matched phrase wins ties between competing categories.
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "Mirror": ["bar end mirror", "rear view mirror", "side mirror",
               "wing mirror", "mirror", "mirrors"],
    "Mobile Holder": ["mobile holder", "phone holder", "mobile mount",
                      "phone mount", "smartphone mount", "cell phone holder",
                      "mobile stand", "phone stand"],
    "Helmet": ["helmet visor", "full face helmet", "half face helmet",
               "modular helmet", "open face helmet", "helmet"],
    "Riding Jacket": ["riding jacket", "motorcycle jacket", "mesh jacket",
                      "leather jacket", "riding suit", "jacket"],
    "Gloves": ["riding gloves", "motorcycle gloves", "winter gloves",
               "hand gloves", "gloves"],
    "Tank Pad": ["tank pad", "tank protector", "tank grip", "fuel tank pad",
                 "tank cover pad"],
    "Lever": ["clutch lever", "brake lever", "gear lever", "short lever",
              "lever"],
    "Crash Guard": ["crash guard", "crash bar", "crash cage", "crash slider",
                    "engine guard", "engine cage", "frame slider",
                    "leg guard"],
    "Windshield": ["windshield", "wind screen", "windscreen", "visor",
                   "screen guard glass"],
    "LED Indicator": ["led indicator", "turn indicator", "turn signal",
                      "blinker", "indicator lights", "indicators",
                      "signal lights", "indicator"],
    "Tail Light": ["tail light", "tail lamp", "taillight", "brake light",
                   "stop light", "led tail"],
    "Fog Light": ["fog light", "fog lamp", "auxiliary light", "aux light",
                  "driving light", "led fog"],
    "Seat Cover": ["seat cover", "seat cushion", "seat pad", "grip seat",
                   "bike seat cover"],
    "Tank Bag": ["tank bag", "magnetic tank bag", "tank bag with mobile"],
    "Saddle Bag": ["saddle bag", "saddle bags", "side bag", "side bags",
                   "pannier", "pannier bag"],
    "Chain Cleaner": ["chain cleaner", "chain degreaser", "chain wash",
                      "chain cleaning spray"],
    "Chain Lube": ["chain lube", "chain lubricant", "chain oil", "chain spray",
                   "lube spray"],
    "Engine Oil": ["engine oil", "motor oil", "fully synthetic",
                   "semi synthetic", "semi-synthetic", "synthetic oil",
                   "two stroke oil", "2t oil"],
    "Phone Charger": ["phone charger", "mobile charger", "usb charger",
                      "type c charger", "type-c charger", "fast charger",
                      "quick charger", "car charger", "charger"],
    "Security Lock": ["disc lock", "chain lock", "brake lock", "security lock",
                      "anti theft lock", "anti-theft lock", "lock alarm",
                      "wheel lock"],
    "GPS Tracker": ["gps tracker", "gps", "vehicle tracker", "vehicle locator",
                    "gps device", "gps module"],
    "Air Pump": ["air pump", "tyre inflator", "tire inflator",
                 "air compressor", "inflator", "pump"],
    "Toolkit": ["tool kit", "toolkit", "tool box", "screwdriver set",
                "socket set", "wrench set", "spanner set", "multi tool",
                "puncture repair kit"],
    "Cleaning Kit": ["cleaning kit", "wash kit", "detailing kit",
                     "bike cleaner", "shampoo", "polish", "wax", "microfiber",
                     "microfibre cloth", "dry wash"],
    "Bike Cover": ["bike cover", "bike body cover", "body cover",
                   "motorcycle cover", "scooty cover", "scooter cover",
                   "two wheeler cover", "rain cover", "dustproof cover",
                   "all weather cover"],
    "Bike Alarm": ["bike alarm", "wireless bike alarm", "bike alarm system",
                   "security alarm", "anti theft alarm", "anti-theft alarm",
                   "anti theft vibration sensor", "alarm with remote",
                   "alarm"],
    "Handlebar Grip": ["handlebar grips", "handlebar grip", "handle grips",
                       "bar grips", "hand grips", "grips"],
    "Dash Cam": ["dash cam", "dashcam", "dash camera", "dual channel dash",
                 "car dash cam", "car dashcam", "front and rear dash cam",
                 "vehicle dash cam"],
    "Horn": ["dual tone horn", "bike horn", "electric horn", "air horn",
             "horn for bike", "horns"],
    "Motorcycle": ["dirt bike", "pit bike", "super cross", "supercross",
                   "off road motorcycle", "kids dirt bike", "quad bike",
                   "atv", "motorcycle booking", "single seat motorcycle",
                   "motorbike"],
}

# Base collections implied by the classified category (additive).
CATEGORY_COLLECTIONS: Dict[str, List[str]] = {
    "Mirror": ["Bike Styling", "Premium Upgrades", "Cafe Racer"],
    "Mobile Holder": ["Navigation & Charging", "Touring", "Daily Commute"],
    "Helmet": ["Rider Gear", "Protection", "Daily Commute"],
    "Riding Jacket": ["Rider Gear", "Protection"],
    "Gloves": ["Rider Gear", "Protection"],
    "Tank Pad": ["Bike Styling", "Protection", "Premium Upgrades"],
    "Lever": ["Performance", "Bike Styling", "Cafe Racer"],
    "Crash Guard": ["Protection", "Adventure"],
    "Windshield": ["Bike Styling", "Touring", "Protection"],
    "LED Indicator": ["Lighting", "Bike Styling"],
    "Tail Light": ["Lighting", "Bike Styling"],
    "Fog Light": ["Lighting", "Adventure", "Bike Styling"],
    "Seat Cover": ["Comfort", "Daily Commute"],
    "Tank Bag": ["Touring", "Luggage", "Daily Commute"],
    "Saddle Bag": ["Touring", "Luggage", "Daily Commute"],
    "Chain Cleaner": ["Cleaning", "Maintenance"],
    "Chain Lube": ["Cleaning", "Maintenance", "Performance"],
    "Engine Oil": ["Maintenance", "Performance"],
    "Phone Charger": ["Navigation & Charging", "Daily Commute"],
    "Security Lock": ["Security", "Protection"],
    "GPS Tracker": ["Security", "Navigation & Charging"],
    "Air Pump": ["Maintenance", "Touring", "Daily Commute"],
    "Toolkit": ["Maintenance", "Touring", "Daily Commute"],
    "Cleaning Kit": ["Cleaning", "Maintenance"],
    "Bike Cover": ["Protection", "Daily Commute"],
    "Bike Alarm": ["Security", "Protection"],
    "Handlebar Grip": ["Comfort", "Bike Styling"],
    "Dash Cam": ["Navigation & Charging", "Security", "Touring"],
    "Horn": ["Security", "Daily Commute"],
    "Motorcycle": ["Daily Commute", "Adventure"],
}

# Extra keyword -> collection supplements (topical collections not implied by
# the base category mapping).  Ordered most-specific first.
KEYWORD_COLLECTIONS: List[Tuple[str, List[str]]] = [
    ("cafe racer", ["Cafe Racer", "Bike Styling"]),
    ("cafe style", ["Cafe Racer", "Bike Styling"]),
    ("scrambler", ["Cafe Racer", "Off Road"]),
    ("scram", ["Cafe Racer", "Off Road"]),
    ("off road", ["Off Road", "Adventure"]),
    ("offroad", ["Off Road", "Adventure"]),
    ("enduro", ["Off Road", "Adventure"]),
    ("dirt bike", ["Off Road", "Adventure"]),
    ("motocross", ["Off Road", "Adventure"]),
    ("adventure", ["Adventure", "Off Road"]),
    ("rally", ["Adventure", "Off Road"]),
    ("touring", ["Touring"]),
    ("long ride", ["Touring"]),
    ("long drive", ["Touring"]),
    ("carbon fiber", ["Premium Upgrades"]),
    ("carbon fibre", ["Premium Upgrades"]),
    ("carbon", ["Premium Upgrades"]),
    ("billet", ["Premium Upgrades"]),
    ("forged", ["Premium Upgrades"]),
    ("anodized", ["Premium Upgrades"]),
    ("premium", ["Premium Upgrades"]),
    ("racing", ["Performance"]),
    ("performance", ["Performance"]),
    ("led", ["Lighting"]),
    ("anti theft", ["Security"]),
    ("anti-theft", ["Security"]),
    ("lock alarm", ["Security"]),
    ("gps", ["Navigation & Charging"]),
    ("waterproof", ["Touring"]),
    ("comfort", ["Comfort"]),
    ("cushion", ["Comfort"]),
    ("backrest", ["Comfort"]),
    ("pillion", ["Comfort"]),
    ("tank bag", ["Luggage"]),
    ("saddle bag", ["Luggage"]),
    ("pannier", ["Luggage"]),
    ("luggage", ["Luggage"]),
    ("top box", ["Luggage"]),
    ("tail bag", ["Luggage"]),
    ("helmet", ["Rider Gear"]),
    ("gloves", ["Rider Gear"]),
    ("jacket", ["Rider Gear"]),
    ("riding gear", ["Rider Gear"]),
    ("chain cleaner", ["Cleaning"]),
    ("chain lube", ["Cleaning"]),
    ("cleaning", ["Cleaning"]),
    ("engine oil", ["Maintenance"]),
    ("maintenance", ["Maintenance"]),
    ("lock", ["Security"]),
]

# Categories whose products are treated as Universal when no bike is named.
UNIVERSAL_CATEGORIES: Set[str] = {
    "Mirror", "Mobile Holder", "Helmet", "Riding Jacket", "Gloves",
    "Tank Pad", "Lever", "Seat Cover", "Chain Cleaner", "Chain Lube",
    "Engine Oil", "Phone Charger", "Air Pump", "Toolkit", "Cleaning Kit",
    "Bike Cover", "Bike Alarm", "Handlebar Grip", "Dash Cam", "Horn",
}

# Titles that are actual motorcycles (whole bikes / booking listings), only
# considered when no accessory category matched.
_MOTORCYCLE_STRONG = [
    "dirt bike", "pit bike", "super cross", "supercross", "off road motorcycle",
    "kids dirt bike", "quad bike", "atv", "single seat motorcycle",
    "motorbike",
]
_MOTORCYCLE_SIGNALS = [
    "booking", "ex showroom", "ex-showroom", "petrol engine",
    "single seat", "automatic transmission",
]

# Match confidence tiers (mirrors compatibility_builder semantics).
_CONF_FULL = 1.0            # "make model" / full slug phrase present
_CONF_MODEL = 0.9           # multi-token model phrase present
_CONF_UNIQUE_MODEL = 0.85   # unique single-token model present
_CONF_MAKE_MODEL = 0.7      # single-token model + make both present


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _norm_text(text: Optional[str]) -> str:
    """Lowercase; collapse everything non-alphanumeric to a single space."""
    if not text:
        return ""
    s = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", s).strip()


_phrase_cache: Dict[str, re.Pattern] = {}


def _has_phrase(text: str, phrase: str) -> bool:
    pat = _phrase_cache.get(phrase)
    if pat is None:
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])")
        _phrase_cache[phrase] = pat
    return bool(pat.search(text))


# ---------------------------------------------------------------------------
# Bike matching (self-contained so the classifier stays DB-free)
# ---------------------------------------------------------------------------

class Bike:
    """A known motorcycle the classifier can extract from product text."""

    __slots__ = ("make", "model", "slug", "norm_model", "norm_full")

    def __init__(self, make: str, model: str, slug: str):
        self.make = make or ""
        self.model = model or ""
        self.slug = slug or ""
        self.norm_model = _norm_text(self.model)
        self.norm_full = _norm_text(slug) or _norm_text(f"{self.make} {self.model}")

    @property
    def name(self) -> str:
        return (f"{self.make} {self.model}").strip()

    def as_dict(self) -> Dict[str, str]:
        return {"make": self.make, "model": self.model, "slug": self.slug}


class BikeMatcher:
    """Match known bikes inside free text."""

    def __init__(self, bikes: List[Dict[str, str]]):
        self.bikes: List[Bike] = []
        self._single_tokens: Set[str] = set()
        for b in bikes:
            bb = Bike(b.get("make", ""), b.get("model", ""), b.get("slug", ""))
            if not bb.norm_model:
                continue
            self.bikes.append(bb)
            if len(bb.norm_model.split()) == 1:
                # unique single-token models are strong signals
                self._single_tokens.add(bb.norm_model)
        self._unique_single_tokens = self._single_tokens

    def match(self, text: Optional[str]) -> List[Tuple[Bike, float]]:
        if not text:
            return []
        t = " " + _norm_text(text) + " "
        results: List[Tuple[Bike, float]] = []
        for b in self.bikes:
            full = b.norm_full
            if full and _has_phrase(t, full):
                results.append((b, _CONF_FULL))
                continue
            tokens = b.norm_model.split()
            if len(tokens) >= 2:
                if _has_phrase(t, b.norm_model):
                    results.append((b, _CONF_MODEL))
                continue
            model = b.norm_model
            if model in self._unique_single_tokens:
                if _has_phrase(t, model):
                    results.append((b, _CONF_UNIQUE_MODEL))
            elif b.make and _has_phrase(t, _norm_text(b.make)) and _has_phrase(t, model):
                results.append((b, _CONF_MAKE_MODEL))
        return self._dedupe_subsumed(results)

    @staticmethod
    def _dedupe_subsumed(
        results: List[Tuple[Bike, float]]
    ) -> List[Tuple[Bike, float]]:
        """Drop generic model matches subsumed by a more specific one."""
        by_make: Dict[str, List[Tuple[Bike, float]]] = defaultdict(list)
        for b, s in results:
            by_make[b.make].append((b, s))
        out: List[Tuple[Bike, float]] = []
        for items in by_make.values():
            items.sort(key=lambda x: len(x[0].norm_model.split()), reverse=True)
            kept: List[Tuple[Bike, float]] = []
            for b, s in items:
                subsumed = False
                for k, _ in kept:
                    if (len(b.norm_model.split()) < len(k.norm_model.split())
                            and b.norm_model and b.norm_model in k.norm_model):
                        subsumed = True
                        break
                if not subsumed:
                    kept.append((b, s))
            out.extend(kept)
        return out


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class ProductClassifier:
    """Keyword-driven classifier following the BikeReview AI rules."""

    def __init__(self, bikes: Optional[List[Dict[str, str]]] = None):
        self.matcher = BikeMatcher(bikes or [])

    # -- category ----------------------------------------------------------

    def _match_category(self, text: str) -> Optional[str]:
        best: Optional[str] = None
        best_score = (0, 0)
        for cat, phrases in CATEGORY_KEYWORDS.items():
            matched = [p for p in phrases if _has_phrase(text, p)]
            if not matched:
                continue
            longest = max(len(p.split()) for p in matched)
            score = (len(matched), longest)
            if score > best_score:
                best_score, best = score, cat
        return best

    def _match_motorcycle(self, text: str) -> bool:
        """True if the text describes a whole motorcycle (not an accessory)."""
        for phrase in _MOTORCYCLE_STRONG:
            if _has_phrase(text, phrase):
                return True
        has_moto = (
            _has_phrase(text, "motorcycle")
            or _has_phrase(text, "motorcycles")
            or _has_phrase(text, "motorbike")
        )
        if not has_moto:
            return False
        if re.search(r"\d+\s*cc(?![a-z0-9])", text):
            return True
        return any(_has_phrase(text, s) for s in _MOTORCYCLE_SIGNALS)

    # -- collections -------------------------------------------------------

    def _match_collections(self, text: str, category: Optional[str]) -> List[str]:
        colls: List[str] = []
        if category:
            for c in CATEGORY_COLLECTIONS.get(category, []):
                if c not in colls:
                    colls.append(c)
        for phrase, tags in KEYWORD_COLLECTIONS:
            if _has_phrase(text, phrase):
                for c in tags:
                    if c not in colls:
                        colls.append(c)
        return colls

    # -- compatibility -----------------------------------------------------

    def _match_compatibility(self, text: str):
        matches = self.matcher.match(text)
        matches.sort(key=lambda x: (-x[1], x[0].name))
        return matches

    # -- public API --------------------------------------------------------

    def classify(
        self,
        title: Optional[str] = None,
        description: Optional[str] = None,
        bullets: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        parts = [title or ""]
        if description:
            parts.append(description)
        if bullets:
            parts.extend(bullets)
        text = _norm_text("\n".join(p for p in parts if p))

        category = self._match_category(text)
        if category is None and self._match_motorcycle(text):
            category = "Motorcycle"
        collections = self._match_collections(text, category)

        matches = self._match_compatibility(text)
        compatible: List[str] = []
        compatible_slugs: List[str] = []
        best_conf = 0.0
        if matches:
            compatible = [b.name for b, _ in matches]
            compatible_slugs = [b.slug for b, _ in matches if b.slug]
            best_conf = matches[0][1]

        if matches:
            ctype = "Bike Specific"
        elif category in UNIVERSAL_CATEGORIES:
            ctype = "Universal"
        else:
            ctype = "Unknown"

        confidence = self._confidence(category, ctype, best_conf, text)
        return {
            "category": category,
            "collections": collections,
            "type": ctype,
            "compatible_motorcycles": compatible,
            "compatible_motorcycle_slugs": compatible_slugs,
            "confidence": confidence,
        }

    def _confidence(self, category: Optional[str], ctype: str,
                    best_conf: float, text: str) -> str:
        if not category:
            return "Low"
        if ctype == "Bike Specific":
            if best_conf >= 0.9:
                return "High"
            return "Medium"
        if ctype == "Universal":
            if _has_phrase(text, "universal") or _has_phrase(text, "universal fit"):
                return "High"
            return "Medium"
        return "Low"


def default_classifier(bikes: Optional[List[Dict[str, str]]] = None) -> ProductClassifier:
    return ProductClassifier(bikes)
