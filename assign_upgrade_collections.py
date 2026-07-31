"""
Assign every active product to the Pimp My Ride Upgrade Collections.

Priority order (first source that yields >=1 collection wins; one product may
still end up with multiple collections because a single source can map to many):

  A. Existing manual assignments      -> never overwritten (product is skipped)
  B. Category mapping                 -> strongest signal
  C. Product title keywords           -> substring phrases, word-boundary match
  D. Brand keywords                   -> brand name match
  E. Description keywords             -> same phrase matching on description

The script is idempotent: products that already have any Upgrade Collection are
left untouched, so re-running never creates duplicate or extra assignments.
Unknown categories and unknown keywords are NOT discarded - they are collected
into the report so you can extend the mapping tables.

Active products = products that appear on the generated site (flat status
"approved" or "review", as computed by ProductService/quality pipeline).

Usage:
    python assign_upgrade_collections.py                          # dry-run
    python assign_upgrade_collections.py --apply                  # write changes
    python assign_upgrade_collections.py --apply --report out.txt
    python assign_upgrade_collections.py --product B0H4RQ1PC1 --verbose
    python assign_upgrade_collections.py --category "Ear Plugs" --collection comfort --apply

Options:
    --dry-run            preview only, never writes (default)
    --apply              write assignments to the database
    --report PATH        write the full report to PATH (UTF-8)
    --product ASIN       restrict to specific product(s); repeatable
    --category NAME      add an ad-hoc category->collection mapping
    --collection SLUG    ... (used together with --category; repeatable)
    --verbose            print a per-product line for every product
"""

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, joinedload

from db.models import Product, UpgradeCollection

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

DB_URL_DEFAULT = os.getenv("DB_URL", "sqlite:///bikereview.db")

# ---------------------------------------------------------------------------
# Source tables. Keys are normalized: lowercase, non-alnum -> '_' for
# categories; lowercase phrases for keywords. Values are collection slugs.
# Edit here to extend the built-in mapping.
# ---------------------------------------------------------------------------

# B. Category mapping (user-approved base table).
CATEGORY_TO_COLLECTIONS: Dict[str, List[str]] = {
    # Protection
    "helmet": ["protection"],
    "full_face": ["protection"],
    "half_face": ["protection"],
    "modular": ["protection"],
    "open_face": ["protection"],
    "gloves": ["protection"],
    "riding_gloves": ["protection"],
    "jackets": ["protection"],
    "riding_jacket": ["protection"],
    "bike_cover": ["protection"],
    # Touring Gear
    "phone_mount": ["smart-rider", "touring-gear"],
    "handlebar_mount": ["smart-rider", "touring-gear"],
    "action_camera": ["smart-rider", "touring-gear"],
    "tyre_inflator": ["bike-care", "touring-gear"],
    "portable": ["bike-care", "touring-gear"],
    "luggage": ["touring-gear"],
    "tank_bag": ["touring-gear"],
    "tail_bag": ["touring-gear"],
    "saddle_bag": ["touring-gear"],
    # Smart Rider
    "charger": ["smart-rider"],
    "usb_charger": ["smart-rider"],
    "bluetooth_intercom": ["smart-rider"],
    "dash_cam": ["smart-rider"],
    "dash_camera": ["smart-rider"],
    # Bike Care
    "engine_oil": ["bike-care"],
    "fully_synthetic": ["bike-care"],
    "semi_synthetic": ["bike-care"],
    "chain_lube": ["bike-care"],
    "chain_cleaner": ["bike-care"],
    "cleaning_kit": ["detailing", "bike-care"],
    "tool_kit": ["bike-care"],
    "toolkit": ["bike-care"],
    "air_pump": ["bike-care"],
    # Lighting
    "auxiliary_lights": ["lighting"],
    "fog_lights": ["lighting"],
    "led_headlights": ["lighting"],
    "headlight": ["lighting"],
    # Rider Comfort
    "seat_cushion": ["rider-comfort"],
    "backrest": ["rider-comfort"],
    # Security (Disc Lock is the only explicitly listed security category)
    "disc_lock": ["protection", "security"],
}

# C. Product title keywords (word-boundary phrase match).
TITLE_KEYWORDS: Dict[str, List[str]] = {
    # Protection
    "helmet": ["protection"],
    "bicycle helmet": ["protection"],
    "riding gloves": ["protection"],
    "gloves": ["protection"],
    "riding jacket": ["protection"],
    "jacket": ["protection"],
    "riding pants": ["protection"],
    "knee guard": ["protection"],
    "elbow guard": ["protection"],
    "visor": ["protection"],
    "bike cover": ["protection"],
    # Touring Gear
    "tank bag": ["touring-gear"],
    "tail bag": ["touring-gear"],
    "saddle bag": ["touring-gear"],
    "side bag": ["touring-gear"],
    "top box": ["touring-gear"],
    "luggage rack": ["touring-gear"],
    "luggage": ["touring-gear"],
    "pannier": ["touring-gear"],
    "carrier": ["touring-gear"],
    "windshield": ["touring-gear"],
    "wind screen": ["touring-gear"],
    # Smart Rider
    "phone mount": ["smart-rider", "touring-gear"],
    "mobile holder": ["smart-rider", "touring-gear"],
    "bluetooth": ["smart-rider"],
    "intercom": ["smart-rider"],
    "action camera": ["smart-rider"],
    "dash cam": ["smart-rider"],
    "camera": ["smart-rider"],
    "gps tracker": ["smart-rider"],
    "gps": ["smart-rider"],
    "usb charger": ["smart-rider"],
    "charger": ["smart-rider"],
    # Bike Care
    "tyre inflator": ["bike-care", "touring-gear"],
    "air pump": ["bike-care"],
    "air compressor": ["bike-care"],
    "engine oil": ["bike-care"],
    "chain lube": ["bike-care"],
    "chain cleaner": ["bike-care", "detailing"],
    "cleaning kit": ["detailing", "bike-care"],
    "tool kit": ["bike-care"],
    "toolkit": ["bike-care"],
    # Lighting
    "headlight": ["lighting"],
    "fog light": ["lighting"],
    "fog lamp": ["lighting"],
    "auxiliary light": ["lighting"],
    "led headlight": ["lighting"],
    "indicator": ["lighting"],
    "indicators": ["lighting"],
    "turn signal": ["lighting"],
    # Security
    "disc lock": ["protection", "security"],
    "chain lock": ["security"],
    "anti theft": ["security"],
    "anti-theft": ["security"],
    "alarm": ["security"],
    "lock": ["security"],
    "horn": ["security"],
    "horns": ["security"],
    # Detailing
    "polish": ["detailing"],
    "spray polish": ["detailing"],
    "wax": ["detailing"],
    "shampoo": ["detailing"],
    "cleaner": ["detailing"],
    # Rider Comfort
    "ear plugs": ["rider-comfort"],
    "earplugs": ["rider-comfort"],
    "seat cover": ["rider-comfort"],
    "seat cushion": ["rider-comfort"],
    "cushion": ["rider-comfort"],
    "backrest": ["rider-comfort"],
    "handlebar grip": ["rider-comfort"],
    "grips": ["rider-comfort"],
    "footrest": ["rider-comfort"],
    "sissy bar": ["rider-comfort"],
    # Bike Styling
    "mirror": ["bike-styling"],
    "mirrors": ["bike-styling"],
    "rear view mirror": ["bike-styling"],
}

# D. Brand keywords (exact, case-insensitive brand name match).
BRAND_KEYWORDS: Dict[str, List[str]] = {
    # Protection (helmets / riding gear)
    "vega": ["protection"], "steelbird": ["protection"], "studds": ["protection"],
    "axor": ["protection"], "rynox": ["protection"], "raida": ["protection"],
    "cramster": ["protection"], "smk": ["protection"], "ls2": ["protection"],
    "mt": ["protection"], "edyell": ["protection"], "blaq": ["protection"],
    "eliane": ["protection"], "gocart": ["protection"], "badowl": ["protection"],
    "shivexim": ["protection"], "radeya": ["protection"], "otoroys": ["protection"],
    "royal enfield": ["protection"], "harley-davidson": ["protection"],
    "tvs": ["protection"], "allextreme": ["protection"], "xtrim": ["protection"],
    # Touring Gear (luggage / bags)
    "viaterra": ["touring-gear"], "guardiangears": ["touring-gear"], "fatmug": ["touring-gear"],
    "seize": ["touring-gear"], "pivalo": ["touring-gear"], "motard": ["touring-gear"],
    "travalate": ["touring-gear"], "arthlaksh": ["touring-gear"], "zulfiqar": ["touring-gear"],
    "taanc": ["touring-gear"], "gr": ["touring-gear"], "b.k": ["touring-gear"],
    # Bike Care (oils / lubes / cleaners)
    "motul": ["bike-care"], "castrol": ["bike-care"], "kangaroo": ["bike-care"],
    "mikanix": ["bike-care"], "michelin": ["bike-care"], "motomax": ["bike-care"],
    "wuerth": ["bike-care"], "vista": ["bike-care"], "gulf": ["bike-care"],
    "yamaha": ["bike-care"], "spinlay": ["bike-care"], "kelvinn": ["bike-care"],
    "oto2eye": ["bike-care"], "oswe": ["bike-care"], "sheeba": ["bike-care"],
    # Smart Rider (cameras / dashcams / GPS / mounts)
    "70mai": ["smart-rider"], "qubo": ["smart-rider"], "redtiger": ["smart-rider"],
    "vantrue": ["smart-rider"], "hayden": ["smart-rider"], "crossbeats": ["smart-rider"],
    "onelap": ["smart-rider"], "bobo": ["smart-rider"], "gigaglitz": ["smart-rider"],
    "sounce": ["smart-rider"], "wecool": ["smart-rider"], "uspot": ["smart-rider"],
    "prakalp": ["smart-rider"], "yellowfin": ["smart-rider"], "prolet": ["smart-rider"],
    "livowalny": ["smart-rider"],
    # Rider Comfort (ear plugs / footrests / seat covers)
    "3m": ["rider-comfort"], "kyna": ["rider-comfort"], "loop": ["rider-comfort"], "zirak": ["rider-comfort"],
    "gikzol": ["rider-comfort"], "easepres": ["rider-comfort"], "jazelora": ["rider-comfort"],
    "futurekart": ["rider-comfort"], "dazzliq": ["rider-comfort"], "karam": ["rider-comfort"],
    "pari": ["rider-comfort"], "nikavi": ["rider-comfort"],
}

# E. Description keywords (same phrase matcher; descriptions are currently
# empty in the catalog, this table is here for when they are populated).
DESCRIPTION_KEYWORDS: Dict[str, List[str]] = {}

# Tokens that never count as "unknown keywords".
STOPWORDS = {
    "the", "and", "for", "with", "from", "bike", "motorcycle", "universal",
    "compatible", "this", "that", "bicycle", "motorcycles", "scooty", "scooter",
    "car", "cycle", "sizes", "size", "pack", "pcs", "pair", "piece", "set",
    "waterproof", "storage", "case", "accessory", "accessories", "mobile",
    "black", "red", "blue", "yellow", "green", "white", "silver", "grey",
    "best", "new", "free", "high", "quality", "easy", "india", "amazon",
    "bikeesentials", "product", "kit", "vibration", "anti", "universal",
}

# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _norm_key(name: str) -> str:
    """Category name -> mapping key: lowercase, non-alnum -> '_'."""
    if not name:
        return ""
    s = re.sub(r"[^a-z0-9]+", "_", name.lower())
    return s.strip("_")


def _norm_text(text: str) -> str:
    """Text for phrase matching: lowercase, punctuation -> spaces."""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


_phrase_cache: Dict[str, re.Pattern] = {}


def _has_phrase(text: str, phrase: str) -> bool:
    pat = _phrase_cache.get(phrase)
    if pat is None:
        pat = re.compile(rf"\b{re.escape(phrase)}\b")
        _phrase_cache[phrase] = pat
    return bool(pat.search(text))


def _match_keywords(text: str, table: Dict[str, List[str]]) -> Tuple[List[str], List[str]]:
    """Return (collection slugs, matched keyword phrases) for a text."""
    if not text:
        return [], []
    norm = _norm_text(text)
    slugs: List[str] = []
    matched: List[str] = []
    for phrase, colls in table.items():
        if _has_phrase(norm, phrase):
            matched.append(phrase)
            for s in colls:
                if s not in slugs:
                    slugs.append(s)
    return slugs, matched


# ---------------------------------------------------------------------------
# Core assignment
# ---------------------------------------------------------------------------


def _product_record(p: Product, source: str, slugs: List[str]) -> dict:
    return {
        "asin": p.asin or "",
        "slug": p.slug or "",
        "title": (p.title or "")[:110],
        "brand": p.brand.name if p.brand else "",
        "category": (p.categories[0].name if p.categories else ""),
        "source": source,
        "collections": slugs,
    }


def assign(session: Session, active_asins: set, extra_mappings: List[Tuple[str, str]],
           verbose: bool = False) -> dict:
    collections_by_slug = {c.slug: c for c in session.query(UpgradeCollection).all()}

    cat_map = dict(CATEGORY_TO_COLLECTIONS)
    for cat_name, coll_slug in extra_mappings:
        key = _norm_key(cat_name)
        if key in cat_map:
            if coll_slug not in cat_map[key]:
                cat_map[key].append(coll_slug)
        else:
            cat_map[key] = [coll_slug]

    products = (
        session.query(Product)
        .options(joinedload(Product.categories),
                 joinedload(Product.brand),
                 joinedload(Product.upgrade_collections))
        .filter(Product.asin.in_(active_asins))
        .order_by(Product.id)
        .all()
    )

    processed: List[dict] = []
    already_assigned: List[dict] = []
    assigned: List[dict] = []
    skipped: List[dict] = []
    no_collection: List[dict] = []
    unknown_categories: Counter = Counter()
    unknown_keywords: Counter = Counter()
    per_collection: Counter = Counter()

    for p in products:
        rec = _product_record(p, "", [])
        processed.append(rec)

        existing = [c.slug for c in p.upgrade_collections]
        if existing:
            rec["source"] = "manual"
            rec["collections"] = existing
            already_assigned.append(rec)
            if verbose:
                print(f"  [skip  ] {rec['asin']} {rec['title']!r} already assigned")
            continue

        # Priority B -> C -> D -> E (first source with >=1 collection wins).
        chosen_source = None
        chosen_slugs: List[str] = []
        chosen_matched: List[str] = []

        # B. Category mapping
        slugs: List[str] = []
        matched_cats: List[str] = []
        for cat in p.categories:
            key = _norm_key(cat.name)
            colls = cat_map.get(key)
            if not colls:
                unknown_categories[cat.name or ""] += 1
                continue
            matched_cats.append(cat.name)
            for s in colls:
                if s not in slugs:
                    slugs.append(s)
        if slugs:
            chosen_source, chosen_slugs, chosen_matched = "category", slugs, matched_cats

        # C. Title keywords
        if not chosen_source:
            slugs, matched = _match_keywords(p.title or "", TITLE_KEYWORDS)
            if slugs:
                chosen_source, chosen_slugs, chosen_matched = "title", slugs, matched

        # D. Brand keywords
        if not chosen_source and p.brand and p.brand.name:
            bname = (p.brand.name or "").strip().lower()
            slugs = BRAND_KEYWORDS.get(bname, [])
            if slugs:
                chosen_source, chosen_slugs, chosen_matched = "brand", slugs, [bname]

        # E. Description keywords
        if not chosen_source:
            slugs, matched = _match_keywords(p.description or "", DESCRIPTION_KEYWORDS)
            if slugs:
                chosen_source, chosen_slugs, chosen_matched = "description", slugs, matched

        if not chosen_source:
            no_collection.append(rec)
            for tok in _candidate_tokens(p.title or ""):
                unknown_keywords[tok] += 1
            if verbose:
                print(f"  [none  ] {rec['asin']} {rec['title']!r} no collection")
            continue

        # Resolve slugs to DB objects; missing slug = config error -> skipped.
        colls = []
        for s in chosen_slugs:
            c = collections_by_slug.get(s)
            if c is None:
                skipped.append(rec)
                break
            colls.append(c)
        else:
            p.upgrade_collections = colls
            for s in chosen_slugs:
                per_collection[s] += 1
            rec["source"] = chosen_source
            rec["collections"] = chosen_slugs
            assigned.append(rec)
            if verbose:
                print(f"  [assign] {rec['asin']} {rec['title']!r} "
                      f"<- {chosen_source} {chosen_matched} -> {chosen_slugs}")
            continue

    return {
        "processed": processed,
        "already_assigned": already_assigned,
        "assigned": assigned,
        "skipped": skipped,
        "no_collection": no_collection,
        "unknown_categories": dict(unknown_categories),
        "unknown_keywords": dict(unknown_keywords),
        "per_collection": dict(per_collection),
    }


def _candidate_tokens(title: str) -> List[str]:
    """Significant title tokens that could be new keyword mappings."""
    toks = _norm_text(title).split()
    return [t for t in toks if len(t) >= 4 and t not in STOPWORDS]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _fmt_records(records: List[dict], limit: int = 40) -> List[str]:
    lines = []
    for r in records[:limit]:
        colls = ", ".join(r["collections"]) or "-"
        src = r.get("source", "")
        lines.append(f"  - {r['title']} [{r['category']}] {src} -> {colls}")
    if len(records) > limit:
        lines.append(f"  ... and {len(records) - limit} more")
    return lines


def render_report(report: dict) -> str:
    L = []
    L.append("=" * 66)
    L.append("  Upgrade Collection Assignment Report")
    L.append("=" * 66)
    L.append("")

    processed = report["processed"]
    assigned = report["assigned"]
    already = report["already_assigned"]
    skipped = report["skipped"]
    no_coll = report["no_collection"]
    unknown_cats = report["unknown_categories"]
    unknown_kws = report["unknown_keywords"]
    per_coll = report["per_collection"]

    L.append(f"  Products processed:          {len(processed)}")
    L.append(f"  Products assigned:           {len(assigned)}")
    L.append(f"  Products already assigned:   {len(already)}  (manual, untouched)")
    L.append(f"  Products skipped:            {len(skipped)}  (mapped collection not in DB)")
    L.append(f"  Products with no collection: {len(no_coll)}")
    L.append(f"  Unknown categories:          {len(unknown_cats)}")
    L.append(f"  Unknown keywords:            {len(unknown_kws)}")
    L.append("")

    L.append("  --- Count per Upgrade Collection ---")
    if per_coll:
        for slug in sorted(per_coll, key=lambda s: (-per_coll[s], s)):
            L.append(f"    {slug:<14} {per_coll[slug]}")
    else:
        L.append("    (none)")
    L.append("")

    L.append("  --- Products assigned ---")
    L.extend(_fmt_records(assigned))
    L.append("")

    L.append("  --- Products already assigned (manual, untouched) ---")
    L.extend(_fmt_records(already))
    L.append("")

    L.append("  --- Products skipped (mapped collection missing from DB) ---")
    L.extend(_fmt_records(skipped))
    L.append("")

    L.append("  --- Unknown categories (not discarded) ---")
    if unknown_cats:
        for name in sorted(unknown_cats, key=lambda n: (-unknown_cats[n], n)):
            L.append(f"    {name or '(empty)'}  ({unknown_cats[name]} products)")
    else:
        L.append("    (none)")
    L.append("")

    L.append("  --- Unknown keywords (candidates to add to keyword tables) ---")
    if unknown_kws:
        for tok in sorted(unknown_kws, key=lambda t: (-unknown_kws[t], t))[:25]:
            L.append(f"    {tok:<22} ({unknown_kws[tok]})")
        if len(unknown_kws) > 25:
            L.append(f"    ... and {len(unknown_kws) - 25} more")
    else:
        L.append("    (none)")
    L.append("")

    L.append("  --- Products with no collection ---")
    L.extend(_fmt_records(no_coll))
    L.append("")

    return "\n".join(L)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assign active products to Upgrade Collections "
                    "(category-first, then title/brand/description keywords).")
    parser.add_argument("--dry-run", action="store_true",
                        help="preview only, never write (default)")
    parser.add_argument("--apply", action="store_true",
                        help="write assignments to the database")
    parser.add_argument("--report", default=None, metavar="PATH",
                        help="write the full report to PATH (UTF-8)")
    parser.add_argument("--product", dest="asins", action="append", default=[],
                        metavar="ASIN", help="restrict to a product (repeatable)")
    parser.add_argument("--category", dest="categories", action="append", default=[],
                        metavar="NAME",
                        help="ad-hoc category->collection mapping (with --collection)")
    parser.add_argument("--collection", dest="collections", action="append", default=[],
                        metavar="SLUG",
                        help="collection slug for --category (repeatable)")
    parser.add_argument("--verbose", action="store_true",
                        help="print a line for every product")
    parser.add_argument("--db", default=None, help="SQLAlchemy DB URL")
    args = parser.parse_args(argv)

    if args.apply and args.dry_run:
        print("error: --apply and --dry-run are mutually exclusive")
        return 2

    if len(args.categories) != len(args.collections):
        print("error: --category and --collection must be used in matching pairs")
        return 2

    extra_mappings = list(zip(args.categories, args.collections))

    # Active products = what the generated site shows (approved / review).
    from db.product_service import ProductService
    active = {
        p["asin"] for p in ProductService().load_all()
        if p.get("status") in ("approved", "review")
    }
    if args.asins:
        active &= set(args.asins)

    eng = create_engine(args.db or DB_URL_DEFAULT, echo=False)
    with Session(eng) as session:
        report = assign(session, active, extra_mappings, verbose=args.verbose)

        if args.apply:
            session.commit()
            print(f"  Applied assignments for {len(report['assigned'])} product(s).")

        text = render_report(report)
        print(text)

        if args.report:
            Path(args.report).write_text(text + "\n", encoding="utf-8")
            print(f"  Full report written to {args.report}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
