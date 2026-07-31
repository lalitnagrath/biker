"""
Compatibility Builder
=====================
Scans every product and auto-populates bike compatibility.

For each product it:
  1. Extracts motorcycle names from the title, description, bullet points
     (editorial features), and editorial pros/cons.
  2. Matches the extracted names against the motorcycle database.
  3. If a confident match exists, stores the bike slugs in
     ``compatible_bikes`` and links the product to those motorcycles.
  4. If no motorcycle name is found AND the product's category is in the
     universal whitelist, the product is marked ``universal = true``.
     Otherwise it is left untouched for manual review.

Existing compatibility is preserved unless ``--overwrite`` is passed.

Usage:
    cd biker
    python compatibility_builder.py                # apply, keep existing
    python compatibility_builder.py --overwrite    # recompute everything
    python compatibility_builder.py --dry-run      # report only, no writes
    python compatibility_builder.py --report out.txt
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session, joinedload

from db.base import engine
from db.models import EditorialScore, Motorcycle, Product, ProductMotorcycle
from product_library import normalize_category

DB_URL_DEFAULT = os.getenv("DB_URL", "sqlite:///bikereview.db")

# Categories whose products may be marked universal when no bike name is found.
# Canonical (snake_case) forms plus a few raw display fallbacks.
UNIVERSAL_CATEGORY_WHITELIST = {
    "helmet",            # Helmet
    "jackets",           # Riding Jacket
    "gloves",            # Gloves
    "phone_mount",       # Phone Holder
    "tyre_inflator",     # Tyre Inflator
    "chain_cleaner",     # Chain Cleaner
    "chain_lube",        # Chain Lube
}
UNIVERSAL_CATEGORY_RAW = {
    "rain gear", "rain_gear", "rain suit", "raincoat",
    "first aid kit", "first_aid_kit",
}

# Match confidence tiers
_CONF_FULL = 1.0            # "make model" phrase present
_CONF_MODEL = 0.9           # multi-token model phrase present
_CONF_UNIQUE_MODEL = 0.85   # unique single-token model present
_CONF_MAKE_MODEL = 0.7      # single-token model + make present


def _norm(text: Optional[str]) -> str:
    """Lowercase and collapse everything non-alphanumeric to a single space."""
    if not text:
        return ""
    s = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", s).strip()


def _esc_re(s: str) -> str:
    return re.escape(s)


class BikeIndex:
    """Pre-built index of the motorcycle database for phrase matching."""

    def __init__(self, bikes: List[Dict[str, Any]]):
        self.bikes = bikes
        self._model_to_bikes: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for b in bikes:
            mn = _norm(b.get("model"))
            if mn:
                self._model_to_bikes[mn].append(b)
        self._unique_single_tokens: Set[str] = {
            mn for mn, bl in self._model_to_bikes.items()
            if len(mn.split()) == 1 and len(bl) == 1
        }

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def match(self, text: Optional[str]) -> List[Tuple[Dict[str, Any], float]]:
        """Return (bike, confidence) tuples for confident matches in text."""
        if not text:
            return []
        t = " " + _norm(text) + " "
        results: List[Tuple[Dict[str, Any], float]] = []
        for b in self.bikes:
            mn = _norm(b.get("model"))
            if not mn:
                continue
            make_n = _norm(b.get("make"))
            slug_n = _norm(b.get("slug"))

            full = slug_n or (f"{make_n} {mn}" if make_n else mn)
            if full and full in t:
                results.append((b, _CONF_FULL))
                continue

            tokens = mn.split()
            if len(tokens) >= 2:
                if re.search(r"(?<![a-z0-9])" + _esc_re(mn) + r"(?![a-z0-9])", t):
                    results.append((b, _CONF_MODEL))
                continue

            # single-token model
            if mn in self._unique_single_tokens:
                if re.search(r"(?<![a-z0-9])" + _esc_re(mn) + r"(?![a-z0-9])", t):
                    results.append((b, _CONF_UNIQUE_MODEL))
            elif make_n and re.search(r"(?<![a-z0-9])" + _esc_re(make_n) + r"(?![a-z0-9])", t) \
                    and re.search(r"(?<![a-z0-9])" + _esc_re(mn) + r"(?![a-z0-9])", t):
                results.append((b, _CONF_MAKE_MODEL))

        return self._dedupe_subsumed(results)

    def _dedupe_subsumed(
        self, results: List[Tuple[Dict[str, Any], float]]
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Drop generic model matches subsumed by a more specific one (same make).

        E.g. if both 'CB350' and 'H'ness CB350' match, keep only the specific one.
        """
        by_make: Dict[str, List[Tuple[Dict[str, Any], float]]] = defaultdict(list)
        for b, score in results:
            by_make[b.get("make", "")].append((b, score))

        out: List[Tuple[Dict[str, Any], float]] = []
        for items in by_make.values():
            items.sort(key=lambda x: len(_norm(x[0].get("model")).split()), reverse=True)
            kept: List[Tuple[Dict[str, Any], float]] = []
            for b, score in items:
                mn = _norm(b.get("model"))
                subsumed = False
                for k, _ in kept:
                    kn = _norm(k.get("model"))
                    if len(mn.split()) < len(kn.split()) and mn and mn in kn:
                        subsumed = True
                        break
                if not subsumed:
                    kept.append((b, score))
            out.extend(kept)
        return out


def _product_text(product: Product) -> str:
    """Gather all searchable text for a product."""
    parts = [product.title]
    if product.description:
        parts.append(product.description)
    ed: Optional[EditorialScore] = product.editorial_score
    if ed:
        for field in ("features", "pros", "cons", "recommended_for"):
            values = getattr(ed, field, None) or []
            if isinstance(values, list):
                for v in values:
                    if isinstance(v, str):
                        parts.append(v)
                    elif isinstance(v, dict):
                        for k2 in ("name", "text", "value", "title"):
                            if v.get(k2):
                                parts.append(str(v[k2]))
    return "\n".join(p for p in parts if p)


def _product_categories(product: Product) -> List[str]:
    return [c.name for c in product.categories] or []


def _category_in_universal_whitelist(cat_names: List[str]) -> bool:
    for name in cat_names:
        canonical = normalize_category(name)
        if canonical in UNIVERSAL_CATEGORY_WHITELIST:
            return True
        key = (name or "").strip().lower()
        if key in UNIVERSAL_CATEGORY_RAW:
            return True
    return False


def _decode_cb(value) -> List[str]:
    """Normalize a stored compatible_bikes value into a list of slugs."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(s) for s in value if s]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return [s.strip() for s in value.split(",") if s.strip()]
        if isinstance(parsed, list):
            return [str(s) for s in parsed if s]
    return []


class CompatibilityBuilder:
    """Core scan + write logic."""

    def __init__(self, session: Session, min_confidence: float = 0.7):
        self.session = session
        self.min_confidence = min_confidence
        self.bike_index = self._build_index()

    def _build_index(self) -> BikeIndex:
        bikes = [
            {
                "make": m.make or "",
                "model": m.model or "",
                "slug": m.slug or "",
            }
            for m in self.session.query(Motorcycle).all()
        ]
        return BikeIndex(bikes)

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def scan(
        self,
        overwrite: bool = False,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Scan every product.

        Returns (matched, universal, manual, skipped) record lists.
        """
        products = (
            self.session.query(Product)
            .options(joinedload(Product.categories), joinedload(Product.editorial_score))
            .all()
        )
        products_with_junction = {
            pid
            for (pid,) in self.session.query(ProductMotorcycle.product_id).distinct().all()
        }

        matched: List[Dict[str, Any]] = []
        universal: List[Dict[str, Any]] = []
        manual: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        for p in products:
            existing = self._has_existing(p, p.id in products_with_junction)
            if existing and not overwrite:
                skipped.append(self._record(p, "already has compatibility (skipped)"))
                continue

            text = _product_text(p)
            matches = self.bike_index.match(text)
            matches = [(b, s) for b, s in matches if s >= self.min_confidence]

            if matches:
                matched.append(self._record(p, [b["slug"] for b, _ in matches]))
                continue

            cat_names = _product_categories(p)
            if _category_in_universal_whitelist(cat_names):
                universal.append(self._record(p, "universal"))
                continue

            manual.append(self._record(p, "manual review"))

        return matched, universal, manual, skipped

    def _has_existing(self, product: Product, has_junction: bool) -> bool:
        if product.universal:
            return True
        if _decode_cb(product.compatible_bikes):
            return True
        return has_junction

    @staticmethod
    def _record(product: Product, note: Any) -> Dict[str, Any]:
        return {
            "asin": product.asin or "",
            "slug": product.slug or "",
            "title": (product.title or "")[:100],
            "category": (product.categories[0].name if product.categories else ""),
            "note": note,
        }

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def apply(self, matched, universal):
        """Persist matched slugs and universal flags to the database."""
        changed = 0
        for rec in matched:
            slugs = rec["note"]
            self._write_product(rec["asin"], universal=False, slugs=slugs)
            changed += 1
        for rec in universal:
            self._write_product(rec["asin"], universal=True, slugs=[])
            changed += 1
        self.session.commit()
        return changed

    def _write_product(self, asin: str, universal: bool, slugs: List[str]):
        product = self.session.query(Product).filter_by(asin=asin).first()
        if not product:
            return
        product.universal = universal
        product.compatible_bikes = slugs if (slugs and not universal) else None
        self.session.query(ProductMotorcycle).filter_by(product_id=product.id).delete()
        for slug in slugs:
            bike = self.session.query(Motorcycle).filter_by(slug=slug).first()
            if bike:
                self.session.add(ProductMotorcycle(
                    product_id=product.id,
                    motorcycle_id=bike.id,
                    match_strategy="compatibility_builder",
                ))


# ----------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------

def _fmt_records(records: List[Dict[str, Any]], limit: int = 50) -> List[str]:
    lines = []
    shown = records[:limit]
    for r in shown:
        note = r["note"]
        if isinstance(note, list):
            note = ", ".join(note)
        lines.append(f"  - {r['title']} [{r['category']}] -> {note}")
    if len(records) > limit:
        lines.append(f"  ... and {len(records) - limit} more")
    return lines


def render_report(matched, universal, manual, skipped, min_confidence) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("  Compatibility Builder Report")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  Products matched to bikes:  {len(matched)}")
    lines.append(f"  Products marked universal:  {len(universal)}")
    lines.append(f"  Products for manual review: {len(manual)}")
    lines.append(f"  Already had compatibility (skipped): {len(skipped)}")
    lines.append(f"  Min confidence threshold:   {min_confidence}")
    lines.append("")
    lines.append("  --- Matched to bikes ---")
    lines.extend(_fmt_records(matched))
    lines.append("")
    lines.append("  --- Marked universal ---")
    lines.extend(_fmt_records(universal))
    lines.append("")
    lines.append("  --- Manual review ---")
    lines.extend(_fmt_records(manual))
    if skipped:
        lines.append("")
        lines.append("  --- Skipped (existing compatibility preserved) ---")
        lines.extend(_fmt_records(skipped))
    lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(
        description="Scan products and auto-populate motorcycle compatibility.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--overwrite", action="store_true",
                        help="Recompute compatibility even for products that already have it.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only scan and report; do not write anything.")
    parser.add_argument("--min-confidence", type=float, default=0.7,
                        help="Minimum match confidence (0-1). Default 0.7.")
    parser.add_argument("--db", default=None, help="SQLAlchemy DB URL (default: %(default)s).")
    parser.add_argument("--report", default=None,
                        help="Optional path to write the full report.")
    args = parser.parse_args(argv)

    if args.min_confidence < 0 or args.min_confidence > 1:
        parser.error("--min-confidence must be between 0 and 1")

    db_url = args.db or DB_URL_DEFAULT
    from sqlalchemy import create_engine
    eng = create_engine(db_url, echo=False)

    print("  Loading motorcycles & products...")
    with Session(eng) as session:
        builder = CompatibilityBuilder(session, min_confidence=args.min_confidence)
        matched, universal, manual, skipped = builder.scan(overwrite=args.overwrite)

        report = render_report(
            matched, universal, manual, skipped, args.min_confidence
        )
        print(report)

        if not args.dry_run and (matched or universal):
            changed = builder.apply(matched, universal)
            print(f"\n  Wrote compatibility for {changed} product(s).")
        elif not args.dry_run:
            print("\n  Nothing to write.")
        else:
            print("\n  DRY RUN: no changes written.")

        if args.report:
            Path(args.report).write_text(report + "\n", encoding="utf-8")
            print(f"  Full report written to {args.report}")


if __name__ == "__main__":
    main()
