# AI Rules

## Session Startup (Read First)

Before making any code changes:

1. Read instructions/START_HERE.md and follow the file order it lists.
2. Read docs/CURRENT_STATE.md.
3. Read instructions/ROADMAP.md.
4. Read the current milestone document at the repository root (MILESTONE_8.md).
5. Review uncommitted git changes.
6. Read docs/ARCHITECTURE.md only when modifying architecture, database models, services, or generators.
7. Read only the files needed for the current milestone.
8. Continue from the current milestone.
9. Do not explore unrelated parts of the project.
10. Never rewrite working architecture without explicit instruction.
11. Prefer extending existing code over creating duplicate systems.
12. Before creating a new file, search the project to ensure an equivalent implementation does not already exist.

## Milestone Rules

- Always continue from the current milestone in instructions/ROADMAP.md.
- Finish the current milestone before starting another.
- Never implement future milestones unless explicitly instructed.
- Update docs/CURRENT_STATE.md after completing a milestone.

---

## Project Principles

- Database is the single source of truth.
- UI never accesses the database directly.
- All business logic belongs in Service classes.
- Repositories only perform database operations.
- Generate static HTML only through GeneratorEngine.
- Never duplicate existing functionality.
- Keep modules small and focused.
- Write tests for new business logic.
- Update docs/CURRENT_STATE.md when completing significant work.

---

This file is the source of truth for the project.

Always follow these rules unless explicitly told otherwise.

This is the primary instruction file.

Load this file before every coding task.

Additional instruction files:

* instructions/START_HERE.md → Session startup sequence
* instructions/PROJECT.md → Project overview
* instructions/ROADMAP.md → Versioned roadmap + milestone documents
* instructions/CODING_RULES.md → Coding standards
* instructions/PRODUCT_RULES.md → Product data rules
* instructions/CONTENT_RULES.md → Content generation
* instructions/BUILD_RULES.md → Website generation
* instructions/IMAGE_RULES.md → Image acquisition & processing
* docs/ARCHITECTURE.md → System architecture
* docs/CURRENT_STATE.md → Current implementation state
* MILESTONE_8.md → Current milestone (at repository root)

Only load additional instruction files when relevant.

---

# Project Goal

Build a fast, static motorcycle ownership, accessories and buying guide website for Indian riders.

The website should become the most useful motorcycle ownership resource in India.

Help riders choose compatible accessories, maintain their motorcycles, solve common ownership problems and make informed buying decisions.

The motorcycle provides context.

The products solve rider problems.

Affiliate products should support the content, never dominate it.

---

# Tech Stack

* Python 3
* Jinja2
* Markdown
* JSON
* HTML
* CSS
* Vanilla JavaScript

Generate static HTML only.

Never use Django, Flask or any backend framework.

---

# Architecture

Everything must be data-driven.

Never hardcode:

* Motorcycles
* Products
* Brands
* Categories
* Recommendations
* Compatibility

Always use JSON or Markdown.

Keep business logic inside reusable Python modules.

Templates should remain presentation-only.

---

# Product Recommendation Architecture

There must be exactly ONE product recommendation engine in the project.

Every page must use the same recommendation engine.

This includes:

* Homepage
* Motorcycle pages
* Buying guides
* Category pages
* Sidebar
* Related products
* Product placeholders
* Editor's Picks
* Recommended setups
* Related accessories

The recommendation engine is responsible for:

* Product matching
* Compatibility filtering
* Category normalization
* Category aliases
* Product ranking
* Brand diversity
* Universal fallback
* Product limits

No templates or page generators should implement their own recommendation logic.

generate.py should request products from the recommendation engine.

It should never filter, rank or manually select products.

---

# Domain Model

Motorcycle != Product

Motorcycles are ownership hubs.

Motorcycles provide:

* Compatibility
* Ownership context
* Maintenance information
* Riding guidance

Products solve rider problems.

Always optimise pages for the user's search intent.

Motorcycle pages should answer ownership questions before recommending products.

---

# Website Philosophy

The website is an editorial resource.

Every page should answer the rider's question first.

Products should naturally support the content.

Never sacrifice user trust for affiliate revenue.

Content should educate first.

Products should help users make better buying decisions.

---

# Motorcycle Ownership Philosophy

Motorcycle pages are ownership hubs, not review pages.

Do not compete with motorcycle review websites.

Instead, help riders own, maintain and accessorize their motorcycles.

Every motorcycle page should answer practical ownership questions such as:

* Which accessories are compatible?
* Which accessories are worth buying?
* What maintenance is required?
* What common problems should owners know?
* Which upgrades are worthwhile?
* Which accessories should a new owner buy first?
* Which buying guides should I read next?

Motorcycle pages should educate first.

Products should naturally support the content.

Motorcycle pages should guide users to accessory buying guides, maintenance guides and compatibility pages instead of trying to contain everything.

---

# UI Philosophy

The website should feel like a premium editorial motorcycle resource.

Every page should be easy to scan.

Prioritize:

* Clean layouts
* Cards
* Comparison tables
* Quick summaries
* Buying advice
* Internal linking
* Mobile usability
* Fast loading

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

## Motorcycle Page Structure

Every motorcycle page should be generated as an ownership hub.

Recommended structure:

* Hero
* Quick Overview
* Must Have Accessories
* Ownership Guide
* Maintenance Guide
* Common Problems
* Compatible Accessories
* Related Buying Guides
* Related Motorcycles
* Frequently Asked Questions

Avoid specification-heavy review pages.

Focus on helping owners.

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

* Title
* Meta Description
* Canonical
* OpenGraph
* Twitter Cards
* Breadcrumbs
* Sitemap
* robots.txt
* RSS
* Structured Data

Generate clean URLs.

Avoid duplicate content.

---

# Performance

* Responsive
* Lazy loading
* WebP
* Minimal JavaScript
* Optimized Core Web Vitals

Target Lighthouse score above 95.

---

# Future Scalability

The architecture should support:

* Thousands of motorcycle pages
* Thousands of products
* Hundreds of brands
* Multiple article types
* New accessory categories

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

Never recommend incompatible accessories.

Never repeat the same product multiple times on one page.

Never create article-specific Python code when a reusable solution is possible.

Never build motorcycle pages as specification dumps.

Never compete with dedicated motorcycle review websites.

Never let affiliate products dominate editorial content.

Always educate first and recommend second.

Never use double dashes (--).
