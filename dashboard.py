#!/usr/bin/env python3
"""
Dashboard — KPI overview for BikeReview India.

Usage:
    python dashboard.py                 # Prints summary to console
    python dashboard.py --html          # Generates dashboard.html
    python dashboard.py --html --open   # Generates and opens in browser
"""

import argparse
import os
import subprocess
import sys
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent))

from db.models import (
    EditorialScore, Image, PriceHistory, Product,
)
from db.product_service import ProductService

DB_URL = os.getenv("DB_URL", "sqlite:///bikereview.db")
OUTPUT_FILE = Path(__file__).parent / "dashboard.html"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def collect_kpis():
    """Gather all KPI values from the database."""
    service = ProductService()
    products = service.load_all()
    dashboard = service.get_quality_dashboard()

    total = len(products)

    active = sum(1 for p in products if p.get("status") == "approved")
    hidden = sum(1 for p in products if p.get("status") == "hidden")
    review = sum(1 for p in products if p.get("status") in ("review",))
    rejected = sum(1 for p in products if p.get("status") == "rejected")
    draft = sum(1 for p in products if p.get("status") == "draft")

    editors_choice = sum(1 for p in products if p.get("editors_choice"))

    missing_images = sum(1 for p in products if not p.get("image"))

    engine = create_engine(DB_URL)
    with Session(engine) as session:
        # Price drops in last 7 days
        week_ago = datetime.now() - timedelta(days=7)
        recent = (
            session.query(PriceHistory.product_id, PriceHistory.price, PriceHistory.old_price)
            .filter(PriceHistory.timestamp >= week_ago)
            .all()
        )
        price_drops = sum(
            1 for r in recent
            if r.old_price is not None and r.price < r.old_price
        )

        # Count products with at least one Image row
        with_images = (
            session.query(Image.product_id)
            .distinct()
            .count()
        )
        total_products_db = session.query(Product).count()
        missing_images_db = total_products_db - with_images

        # Categories with products
        cat_counts = dashboard["by_category"] if dashboard else {}
        categories_with_products = sum(
            1 for v in cat_counts.values()
            if v.get("approved", 0) > 0 or v.get("review", 0) > 0
        )

    return {
        "total": total,
        "active": active,
        "hidden": hidden,
        "review": review,
        "rejected": rejected,
        "draft": draft,
        "editors_choice": editors_choice,
        "missing_images": max(missing_images, missing_images_db),
        "price_drops": price_drops,
        "categories_with_products": categories_with_products,
        "total_in_db": total_products_db,
    }


def print_summary(kpis):
    """Print a compact console summary."""
    sep = "=" * 52
    print(f"\n{sep}")
    print(f"  DASHBOARD — {datetime.now():%b %d, %Y %H:%M}")
    print(f"{sep}")
    print(f"  Total Products       {kpis['total']:>6d}")
    print(f"  Active (approved)    {kpis['active']:>6d}")
    print(f"  Hidden               {kpis['hidden']:>6d}")
    print(f"  Needs Review         {kpis['review']:>6d}")
    print(f"  Draft                {kpis['draft']:>6d}")
    print(f"  Rejected             {kpis['rejected']:>6d}")
    print(f"  Editor's Choice      {kpis['editors_choice']:>6d}")
    print(f"  Price Drops (7d)     {kpis['price_drops']:>6d}")
    print(f"  Missing Images       {kpis['missing_images']:>6d}")
    print(f"{sep}")
    print(f"  python dashboard.py --html   to generate dashboard.html")
    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def _card(icon, label, value, color, bg):
    return f"""\
          <div class="kpi-card" style="--card-color:{color};--card-bg:{bg}">
            <div class="kpi-icon">{icon}</div>
            <div class="kpi-body">
              <div class="kpi-value">{value}</div>
              <div class="kpi-label">{label}</div>
            </div>
          </div>"""


def _action(icon, title, desc, cmd, color):
    return f"""\
          <div class="action-card" style="--action-color:{color}">
            <div class="action-icon">{icon}</div>
            <div class="action-body">
              <div class="action-title">{title}</div>
              <div class="action-desc">{desc}</div>
            </div>
            <button class="action-btn" onclick="runAction('{cmd}')">Run</button>
          </div>"""


SVG = {
    "package": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>',
    "check": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    "eye-off": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>',
    "alert": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    "star": '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
    "trending-down": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/></svg>',
    "image": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
    "upload": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
    "globe": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
    "refresh": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>',
    "zap": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
}


def generate_html(kpis):
    now = datetime.now().strftime("%b %d, %Y %H:%M")

    cards = "".join([
        _card(SVG["package"], "Total Products", kpis["total"], "#2563eb", "#eff6ff"),
        _card(SVG["check"], "Active (approved)", kpis["active"], "#16a34a", "#f0fdf4"),
        _card(SVG["eye-off"], "Hidden", kpis["hidden"], "#6b7280", "#f9fafb"),
        _card(SVG["alert"], "Needs Review", kpis["review"], "#ea580c", "#fff7ed"),
        _card(SVG["star"], "Editor's Choice", kpis["editors_choice"], "#ca8a04", "#fefce8"),
        _card(SVG["trending-down"], "Price Drops (7d)", kpis["price_drops"], "#dc2626", "#fef2f2"),
        _card(SVG["image"], "Missing Images", kpis["missing_images"], "#7c3aed", "#faf5ff"),
    ])

    actions = "".join([
        _action(SVG["upload"], "Import Products",
                "Import from bike-deals.json into the product library",
                "python products.py import", "#2563eb"),
        _action(SVG["globe"], "Generate Website",
                "Build the complete static site with all pages",
                "python generate.py", "#16a34a"),
        _action(SVG["zap"], "Deploy",
                "Deploy the generated site to production",
                "deploy", "#7c3aed"),
        _action(SVG["refresh"], "Sync Amazon",
                "Sync latest prices, ratings & availability from Amazon",
                "python products.py sync", "#ea580c"),
    ])

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dashboard — BikeReview India</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#f4f5f7;--surface:#fff;--border:#e0e3e8;--text:#1a1a2e;--text2:#6b7280;
  --accent:#2563eb;--radius:10px;--radius-sm:6px;--shadow:0 1px 3px rgba(0,0,0,.08);
}}
body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);font-size:14px;line-height:1.5;padding:24px}}

/* Header */
.header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}}
.header h1{{font-size:20px;font-weight:700;letter-spacing:-.3px}}
.header .meta{{font-size:12px;color:var(--text2)}}
.header .badge{{font-size:11px;background:#e0e7ff;color:var(--accent);padding:3px 10px;border-radius:99px;font-weight:600}}

/* KPI Grid */
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px;margin-bottom:28px}}
.kpi-card{{background:var(--surface);border-radius:var(--radius);border:1px solid var(--border);padding:16px;display:flex;align-items:center;gap:14px;transition:box-shadow .15s}}
.kpi-card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.08)}}
.kpi-icon{{width:38px;height:38px;border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0;background:var(--card-bg);color:var(--card-color)}}
.kpi-icon svg{{width:20px;height:20px}}
.kpi-value{{font-size:22px;font-weight:700;letter-spacing:-.5px;line-height:1.1}}
.kpi-label{{font-size:12px;color:var(--text2);margin-top:2px}}

/* Actions */
h2{{font-size:16px;font-weight:600;margin-bottom:12px}}
.actions-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;margin-bottom:28px}}
.action-card{{background:var(--surface);border-radius:var(--radius);border:1px solid var(--border);padding:16px;display:flex;align-items:center;gap:12px;transition:box-shadow .15s}}
.action-card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.08)}}
.action-icon{{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0;background:color-mix(in srgb,var(--action-color) 12%,transparent);color:var(--action-color)}}
.action-icon svg{{width:18px;height:18px}}
.action-body{{flex:1;min-width:0}}
.action-title{{font-size:13px;font-weight:600}}
.action-desc{{font-size:11px;color:var(--text2);margin-top:1px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.action-btn{{flex-shrink:0;font-size:12px;font-weight:600;padding:6px 14px;border-radius:var(--radius-sm);border:none;cursor:pointer;background:var(--action-color);color:#fff;transition:opacity .15s;font-family:inherit}}
.action-btn:hover{{opacity:.85}}
.action-btn:active{{opacity:.7}}

/* Footer */
.footer{{font-size:11px;color:var(--text2);text-align:center;padding:16px 0 8px;border-top:1px solid var(--border)}}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>Dashboard</h1>
    <div class="meta">BikeReview India &middot; {now}</div>
  </div>
  <span class="badge">{kpis['categories_with_products']} categories</span>
</div>

<div class="kpi-grid">
{cards}
</div>

<h2>Quick Actions</h2>
<div class="actions-grid">
{actions}
</div>

<div class="footer">
  Data from SQLite &middot; <a href="#" onclick="location.reload()">Refresh</a>
</div>

<script>
function runAction(cmd){{
  if(cmd==='deploy'){{alert('Deploy: configure your deploy script in dashboard.py and set a keyboard shortcut or CI job.');return}}
  var cmds={{'python products.py import':'Import from bike-deals.json into the product library.','python generate.py':'Build the complete static site to the output directory.','python products.py sync':'Sync latest Amazon prices, ratings & availability.'}}
  if(confirm('Run:\\n\\n  '+cmd+'\\n\\nOpen a terminal in the biker/ directory and paste the command above.')){{
    var btn=event.target;btn.textContent='Copied';btn.disabled=true
    navigator.clipboard.writeText(cmd).then(function(){{setTimeout(function(){{btn.textContent='Run';btn.disabled=false}},2000)}})
  }}
}}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Dashboard — BikeReview India KPIs")
    parser.add_argument("--html", action="store_true", help="Generate dashboard.html")
    parser.add_argument("--open", action="store_true", help="Open dashboard.html in browser")
    args = parser.parse_args()

    kpis = collect_kpis()

    if args.html or args.open:
        html = generate_html(kpis)
        OUTPUT_FILE.write_text(html, encoding="utf-8")
        print(f"  Dashboard written to {OUTPUT_FILE}")
        if args.open:
            webbrowser.open(OUTPUT_FILE.resolve().as_uri())
    else:
        print_summary(kpis)


if __name__ == "__main__":
    main()
