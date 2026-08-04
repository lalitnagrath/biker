"""
ProductImportService — writes Control Center selections straight into SQLite.

New products enter the system ONLY here (Phase 8.1). Existing products are
never modified: any ASIN already present in the products table is skipped and
reported. Images are downloaded to static/images/products/ using the same
convention as the curated catalog.

Usage:
    svc = ProductImportService()
    report = svc.import_products(flat_products, download_images=True)
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Product
from db.writer import DatabaseWriter

DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGE_DIR = PROJECT_ROOT / "static" / "images" / "products"


class ProductImportService:
    """Import flat product dicts into SQLite, skipping existing ASINs."""

    def __init__(self, db_url: Optional[str] = None,
                 image_dir: Optional[Path] = None):
        self.db_url = db_url or DB_URL
        self.image_dir = Path(image_dir) if image_dir else IMAGE_DIR
        self.project_root = PROJECT_ROOT

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def existing_asins(self) -> set:
        """Return the set of ASINs already present in the products table."""
        from db.base import Base
        engine = create_engine(self.db_url)
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            rows = session.query(Product.asin).all()
        return {r[0].upper() for r in rows if r[0]}

    def import_products(
        self,
        products: List[dict],
        download_images: bool = True,
    ) -> Dict[str, Any]:
        """Import new products only; never modify existing ones.

        Args:
            products: flat product dicts (typically from AmazonSearchService).
            download_images: download the product image to static/images/products.

        Returns a report dict:
            {
                "submitted": n,
                "imported": [flat dicts inserted],
                "skipped_existing": [flat dicts already in the library],
                "failed": [{"asin", "title", "error"}],
                "images": {"downloaded": n, "skipped": n, "failed": n},
            }
        """
        existing = self.existing_asins()

        to_import: List[dict] = []
        skipped: List[dict] = []
        for product in products:
            asin = (product.get("asin") or "").strip().upper()
            if not asin:
                continue
            if asin in existing:
                skipped.append(product)
                continue
            to_import.append(dict(product))

        imported: List[dict] = []
        failed: List[dict] = []
        image_stats = {"downloaded": 0, "skipped": 0, "failed": 0}

        if to_import:
            self.image_dir.mkdir(parents=True, exist_ok=True)
            with DatabaseWriter(self.db_url) as writer:
                for flat in to_import:
                    try:
                        writer.save_product(flat)
                        if download_images:
                            outcome = self._download_and_link_image(
                                flat, writer
                            )
                            image_stats[outcome] = image_stats.get(outcome, 0) + 1
                        imported.append(flat)
                    except Exception as exc:
                        failed.append({
                            "asin": flat.get("asin"),
                            "title": flat.get("title"),
                            "error": str(exc),
                        })

        return {
            "submitted": len(products),
            "imported": imported,
            "skipped_existing": skipped,
            "failed": failed,
            "images": image_stats,
        }

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------

    def _download_and_link_image(self, flat: dict,
                                 writer: DatabaseWriter) -> str:
        """Download the product image and link it to the DB row.

        Returns one of "downloaded", "skipped", "failed".
        """
        amazon_url = (flat.get("amazon_image_url") or flat.get("image") or "")
        if not amazon_url:
            return "skipped"

        asin = (flat.get("asin") or "").strip().upper()
        slug = (flat.get("slug") or "").strip() or asin.lower()
        filename = f"{_safe_filename(slug)}.jpg"
        dest = self.image_dir / filename
        local_path = f"static/images/products/{filename}"

        try:
            if not dest.exists() or dest.stat().st_size == 0:
                if amazon_url.startswith("http"):
                    if not _download_image(amazon_url, dest):
                        return "failed"
                else:
                    src = self.project_root / amazon_url
                    if src.exists():
                        import shutil
                        shutil.copy2(src, dest)
                    else:
                        return "skipped"
        except Exception:
            return "failed"

        from db.models import Image

        product = writer.session.query(Product).filter_by(asin=asin).first()
        if not product:
            return "failed"
        image = writer.session.query(Image).filter_by(
            product_id=product.id, is_primary=True
        ).first()
        if not image:
            image = Image(product_id=product.id, variant="full", is_primary=True)
            writer.session.add(image)
        image.url = local_path
        image.local_path = local_path
        writer.session.flush()
        return "downloaded"


def _safe_filename(slug: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    return cleaned or "product"


def _download_image(url: str, dest: Path) -> bool:
    """Download a remote image to dest. Returns True on success."""
    try:
        response = requests.get(url, timeout=15, stream=True)
        if response.status_code != 200:
            return False
        with open(dest, "wb") as fh:
            for chunk in response.iter_content(1024):
                fh.write(chunk)
        return dest.stat().st_size > 0
    except Exception:
        return False
