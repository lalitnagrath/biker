"""Canonical URL builders for the BikeReview India static site.

Every internal link in the generated site must resolve to a real HTML file.
These helpers are the SINGLE source of truth for internal URL construction so
that link targets never drift from where pages are actually written.

Convention: every builder returns a relative path that points at the actual
generated ``index.html`` file (e.g. ``categories/chain-lube/index.html``),
optionally prefixed with ``base_path``. Callers must NOT append ``/index.html``
or build paths by string concatenation.
"""

from product_library import category_slug, normalize_category
from product_engine import CATEGORY_GUIDE_SLUGS


def category_url(slug, base_path=""):
    """URL of an individual category listing page.

    Accepts either a canonical snake_case category or a display name
    (e.g. 'Chain Lube') and always normalizes before slugifying so the
    resulting path matches the generated page.
    """
    canonical = normalize_category(slug)
    return f"{base_path}categories/{category_slug(canonical)}/index.html"


def category_index_url(base_path=""):
    """URL of the all-products / categories index page."""
    return f"{base_path}categories/index.html"


def guide_url(category, base_path="", bike_slug=""):
    """URL of a buying-guide ('best of') page for a product category.

    Delegates to the canonical guide-slug mapping. Returns '#' when the
    category has no guide so broken links are never emitted.
    """
    normalized = normalize_category(category).lower()
    slug = CATEGORY_GUIDE_SLUGS.get(normalized, "")
    if not slug:
        return "#"
    url = f"{base_path}guides/{slug}/index.html"
    if bike_slug:
        url += f"?bike={bike_slug}"
    return url


def guide_index_url(base_path=""):
    return f"{base_path}guides/index.html"


def bestof_url(slug, base_path=""):
    """Best-of pages are written to guides/<slug>/index.html."""
    return f"{base_path}guides/{slug}/index.html"


def motorcycle_url(slug, base_path=""):
    return f"{base_path}motorcycles/{slug}/index.html"


def motorcycle_index_url(base_path=""):
    return f"{base_path}motorcycles/index.html"


def brand_url(slug, base_path=""):
    return f"{base_path}brands/{slug}/index.html"


def brand_index_url(base_path=""):
    return f"{base_path}brands/index.html"


def product_url(slug, base_path=""):
    return f"{base_path}products/{slug}/index.html"


def article_url(slug, base_path=""):
    return f"{base_path}articles/{slug}/index.html"


def article_index_url(base_path=""):
    return f"{base_path}articles/index.html"


def article_category_url(slug, base_path=""):
    """Article category index pages (maintenance, buying-guides, ...)."""
    return f"{base_path}articles/{slug}/index.html"


def maintenance_topic_url(bike_slug, topic_slug, base_path=""):
    return f"{base_path}motorcycles/{bike_slug}/maintenance/{topic_slug}/index.html"


def static_page_url(name, base_path=""):
    """Generic static page under the site root (about, contact, ...)."""
    return f"{base_path}{name}/index.html"


# Convenience names used by templates
def about_url(base_path=""):
    return static_page_url("about", base_path)


def contact_url(base_path=""):
    return static_page_url("contact", base_path)


def privacy_url(base_path=""):
    return static_page_url("privacy", base_path)


def affiliate_disclosure_url(base_path=""):
    return static_page_url("affiliate-disclosure", base_path)


class URL:
    """Namespace exposed to Jinja so templates call URL.category(slug) etc."""

    category = staticmethod(category_url)
    category_index = staticmethod(category_index_url)
    guide = staticmethod(guide_url)
    guide_index = staticmethod(guide_index_url)
    bestof = staticmethod(bestof_url)
    motorcycle = staticmethod(motorcycle_url)
    motorcycle_index = staticmethod(motorcycle_index_url)
    brand = staticmethod(brand_url)
    brand_index = staticmethod(brand_index_url)
    product = staticmethod(product_url)
    article = staticmethod(article_url)
    article_index = staticmethod(article_index_url)
    article_category = staticmethod(article_category_url)
    maintenance_topic = staticmethod(maintenance_topic_url)
    static_page = staticmethod(static_page_url)
    about = staticmethod(about_url)
    contact = staticmethod(contact_url)
    privacy = staticmethod(privacy_url)
    affiliate_disclosure = staticmethod(affiliate_disclosure_url)
