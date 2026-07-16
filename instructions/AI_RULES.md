# AI Rules

This file is the source of truth for the project.

Always follow these rules unless explicitly told otherwise.

This is the primary instruction file.

Load this file before every coding task.

Additional instruction files:

- CONTENT_RULES.md → Content generation
- BUILD_RULES.md → Website generation
- IMAGE_RULES.md → Image acquisition & processing

Only load additional instruction files when relevant.

---

# Project Goal

Build a fast, static motorcycle review and buying guide website for Indian riders.

The website should become the most useful motorcycle knowledge base in India.

Help riders make informed buying decisions through honest editorial content.

Affiliate products should support the content, never dominate it.

---

# Tech Stack

- Python 3
- Jinja2
- Markdown
- JSON
- HTML
- CSS
- Vanilla JavaScript

Generate static HTML only.

Never use Django, Flask or any backend framework.

---

# Architecture

Everything must be data-driven.

Never hardcode:

- motorcycles
- products
- brands
- categories
- recommendations
- compatibility

Always use JSON or Markdown.

Keep business logic inside reusable Python modules.

Templates should remain presentation-only.

---

# Product Recommendation Architecture

There must be exactly ONE product recommendation engine in the project.

Every page must use the same recommendation engine.

This includes:

- Homepage
- Motorcycle pages
- Buying guides
- Category pages
- Sidebar
- Related products
- Product placeholders
- Editor's Picks
- Recommended setups
- Related accessories

The recommendation engine is responsible for:

- Product matching
- Compatibility filtering
- Category normalization
- Category aliases
- Product ranking
- Brand diversity
- Universal fallback
- Product limits

No templates or page generators should implement their own recommendation logic.

generate.py should request products from the recommendation engine.

It should never filter, rank or manually select products.

---

# Domain Model

Motorcycle != Product

Motorcycles provide compatibility and context.

Products solve rider problems.

Always optimize pages for the user's search intent.

Example

Correct

Best Helmet for Honda CB350

Wrong

Honda CB350 Helmet

---

# Website Philosophy

The website is an editorial resource.

Every page should answer the rider's question first.

Products should naturally support the content.

Never sacrifice user trust for affiliate revenue.

Content should educate first.

Products should help users make better buying decisions.

---

# UI Philosophy

The website should feel like a premium editorial buying guide.

Every page should be easy to scan.

Prioritize:

- Clean layouts
- Cards
- Comparison tables
- Quick summaries
- Buying advice
- Internal linking
- Mobile usability
- Fast loading

Avoid long walls of text.

Every page should help users quickly find the information they need.

---

# Generator Rules

All pages must be generated from reusable templates.

Never build one-off layouts.

Every improvement should automatically benefit all future pages.

Prefer reusable Python functions over duplicated template logic.

Keep templates generic.

Keep business logic inside Python.

---

# Coding

Prefer reusable, modular code.

Never duplicate logic.

Never break existing functionality.

Refactor instead of patching.

Use type hints where appropriate.

Comment non-obvious logic.

Prefer composition over duplication.

If multiple files perform similar work, consolidate the logic.

---

# Data Rules

All products must come from JSON.

All motorcycles must come from JSON.

Articles must remain content-focused.

Products should be inserted dynamically.

Never hardcode affiliate products inside templates or articles.

---

# SEO

Generate automatically:

- Title
- Meta Description
- Canonical
- OpenGraph
- Twitter Cards
- Breadcrumbs
- Sitemap
- robots.txt
- RSS
- Structured Data

Generate clean URLs.

Avoid duplicate content.

---

# Performance

Responsive

Lazy loading

WebP

Minimal JavaScript

Optimize Core Web Vitals.

Target Lighthouse score above 95.

---

# Future Scalability

The architecture should support:

- Thousands of motorcycle pages
- Thousands of products
- Hundreds of brands
- Multiple article types
- New accessory categories

New motorcycles should require only data additions, not code changes.

---

# Never

Never invent products.

Never invent specifications.

Never invent prices.

Never invent compatibility.

Never hardcode products.

Never hardcode recommendations.

Never hardcode motorcycles.

Never hardcode brands.

Never hardcode categories.

Never duplicate recommendation logic.

Never duplicate business logic.

Never display empty product sections.

Never leave empty placeholders.

Never output TODO text.

Never output Lorem Ipsum.

Never create duplicate URLs.

Never create broken links.

Never recommend unrelated products.

Never create article-specific Python code when a reusable solution is possible.

Never use double dashes (--).