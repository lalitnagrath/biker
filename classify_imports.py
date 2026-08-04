"""
Classify every imported Amazon product.

Runs the heuristic ProductClassifier over the products database and persists:

    category   -> products.accessory_type_id   (24 predefined types)
    collections-> product_upgrade_collections  (17 predefined collections)
    type       -> products.universal / products.compatibility_type
    bikes      -> products.compatible_bikes + product_motorcycle links
    confidence -> products.classification_confidence

The taxonomy (24 accessory types + 17 upgrade collections) is created on
first run if missing.  Classification fields are overwritten by default; use
--dry-run to preview without writing.

Usage:
    python classify_imports.py                # apply
    python classify_imports.py --dry-run      # preview only
    python classify_imports.py --report out.txt
    python classify_imports.py --product B0H726T5WZ --verbose
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

DB_URL_DEFAULT = os.getenv("DB_URL", "sqlite:///bikereview.db")
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bikereview.db")

_NEW_COLUMNS = {
    "compatibility_type": "VARCHAR(10)",
    "classification_confidence": "VARCHAR(10)",
}


def ensure_columns(engine) -> List[str]:
    """Add the classification columns to products if the DB predates them."""
    added = []
    with engine.connect() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(products)")).fetchall()
        }
        for col, ddl in _NEW_COLUMNS.items():
            if col not in existing:
                conn.execute(text(
                    f"ALTER TABLE products ADD COLUMN {col} {ddl}"
                ))
                added.append(col)
        conn.commit()
    return added


def render_report(report: Dict[str, Any], records: List[Dict[str, Any]],
                  verbose: bool = False) -> str:
    L = []
    L.append("=" * 66)
    L.append("  AI Product Classification Report")
    L.append("=" * 66)
    L.append("")
    L.append(f"  Products classified:        {report['total']}")
    L.append("")

    L.append("  --- Category ---")
    for name in sorted(report["by_category"],
                       key=lambda n: (-report["by_category"][n], n)):
        L.append(f"    {name:<22} {report['by_category'][name]}")
    L.append("")

    L.append("  --- Compatibility type ---")
    for name in sorted(report["by_type"],
                       key=lambda n: (-report["by_type"][n], n)):
        L.append(f"    {name:<22} {report['by_type'][name]}")
    L.append("")

    L.append("  --- Confidence ---")
    for name in sorted(report["by_confidence"],
                       key=lambda n: (-report["by_confidence"][n], n)):
        L.append(f"    {name:<22} {report['by_confidence'][name]}")
    L.append("")

    L.append("  --- Upgrade Collections (product assignments) ---")
    for name in sorted(report["by_collection"],
                       key=lambda n: (-report["by_collection"][n], n)):
        L.append(f"    {name:<26} {report['by_collection'][name]}")
    L.append("")

    L.append("  --- No category detected ---")
    if report["no_category"]:
        for r in report["no_category"][:25]:
            L.append(f"    - {r['asin']} {r['title'][:80]}")
        if len(report["no_category"]) > 25:
            L.append(f"    ... and {len(report['no_category']) - 25} more")
    else:
        L.append("    (none)")
    L.append("")

    L.append("  --- Unknown compatibility (no bike, not universal) ---")
    if report["unknown"]:
        for r in report["unknown"][:25]:
            L.append(f"    - {r['asin']} {r['title'][:80]} [{r['category'] or '?'}]")
        if len(report["unknown"]) > 25:
            L.append(f"    ... and {len(report['unknown']) - 25} more")
    else:
        L.append("    (none)")

    if verbose:
        L.append("")
        L.append("  --- Per-product ---")
        for r in records:
            colls = ", ".join(r["collections"]) or "-"
            L.append(f"    - {r['asin']} {r['title'][:60]}")
            L.append(f"        category={r['category'] or '-'} "
                     f"type={r['type']} conf={r['confidence']} "
                     f"bikes={','.join(r['compatible_motorcycles']) or '-'}")
            L.append(f"        collections: {colls}")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Classify every imported Amazon product "
                    "(category, collections, compatibility, confidence).")
    parser.add_argument("--dry-run", action="store_true",
                        help="preview only, never write")
    parser.add_argument("--report", default=None, metavar="PATH",
                        help="write the full report to PATH (UTF-8)")
    parser.add_argument("--product", dest="asins", action="append", default=[],
                        metavar="ASIN", help="restrict to a product (repeatable)")
    parser.add_argument("--verbose", action="store_true",
                        help="print a per-product line for every product")
    parser.add_argument("--db", default=None, help="SQLAlchemy DB URL")
    args = parser.parse_args(argv)

    engine = create_engine(args.db or DB_URL_DEFAULT, echo=False)
    added = ensure_columns(engine)
    if added:
        print(f"  Added column(s) to products: {', '.join(added)}")

    from sqlalchemy.orm import Session
    from db.classification_service import ClassificationService

    with Session(engine) as session:
        svc = ClassificationService(session)
        created = svc.ensure_taxonomy()
        if created["accessory_types_created"] or created["collections_created"]:
            print(f"  Created {created['accessory_types_created']} accessory "
                  f"type(s), {created['collections_created']} collection(s).")
        session.commit()

        report = svc.classify_all(
            asins=args.asins or None, dry_run=args.dry_run
        )

    text_report = render_report(report, report["records"], verbose=args.verbose)
    print(text_report)
    if not args.dry_run:
        print(f"\n  Applied classification to {report['total']} product(s).")
    else:
        print("\n  DRY RUN: no changes written.")

    if args.report:
        Path(args.report).write_text(text_report + "\n", encoding="utf-8")
        print(f"  Full report written to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
