# AI Rules

This file is the source of truth for the project.

Always follow these rules unless explicitly told otherwise.

This is the primary instruction file.

Load this file for every task.

Additional instruction files:

- CONTENT_RULES.md → Content generation
- BUILD_RULES.md → Website generation
- IMAGE_RULES.md → Image acquisition & processing

Only load additional files when relevant.

---

# Project Goal

Build a fast, static motorcycle review and buying guide website for Indian riders.

The website should help riders make informed buying decisions.

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

Always use JSON or Markdown.

---

# Domain Model

Motorcycle != Product

Motorcycles are compatibility targets.

Products are accessories or maintenance items.

Always optimize pages for the PRODUCT.

Motorcycles provide context.

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

---

# Coding

Prefer reusable, modular code.

Never duplicate logic.

Never break existing functionality.

Refactor instead of patching.

Use type hints where appropriate.

Comment non-obvious logic.

---

# SEO

Generate automatically:

- title
- meta description
- canonical
- OpenGraph
- Twitter cards
- breadcrumbs
- sitemap
- robots
- RSS
- structured data

---

# Performance

Responsive

Lazy loading

WebP

Minimal JavaScript

Lighthouse 95+

---

# Never

Never invent products.

Never invent specifications.

Never invent prices.

Never hardcode data already in JSON.

Never output TODO text.

Never output Lorem Ipsum.

Never create duplicate URLs.

Never create broken links.

Never recommend unrelated products.

Never use double dashes (--).