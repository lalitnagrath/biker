# AI Instructions


This file is the source of truth for the project.

Always read this file before making any code changes.

Assume every future request must follow these rules unless the user explicitly says otherwise.

## Project Goal

Build a fast, static motorcycle review and buying guide website using Python.

The website helps Indian bikers choose motorcycles, riding gear, accessories and maintenance products.

Amazon affiliate products should support the content, not dominate it.

---

## Tech Stack

Python 3

Jinja2

Markdown

JSON

HTML

CSS

Vanilla JavaScript

Generate static HTML only.

Do NOT use Django or Flask.

---

## Project Structure

articles/
templates/
static/
output/

bike.json
motorcycles.json

generate.py

---

## Data

Products come from bike.json.

Motorcycles come from motorcycles.json.

Articles come from Markdown.

Never hardcode products or motorcycles.

Everything must be data-driven.

---

## Product Insertion

Articles should contain placeholders like

{{ products:Helmet limit=5 }}

{{ products:Phone Mount limit=3 }}

{{ products:Chain Lube limit=3 }}

Python replaces placeholders with product cards.

---

## Motorcycle Pages

Automatically generate

Bike Overview

Accessories

Maintenance

FAQs

Service Schedule

Engine Oil

Tyre Pressure

Common Problems

Buying Guide

Related Articles

Related Products

---

## SEO

Generate automatically

Title

Description

Canonical

OpenGraph

Twitter Cards

Breadcrumbs

Article Schema

Product Schema

FAQ Schema

Sitemap

robots.txt

RSS

---

## Performance

Responsive

Lazy Loading

WebP

Minified CSS

Minimal JavaScript

Lighthouse 95+

---

## Coding Rules

Write modular code.

No duplicate code.

Reusable templates.

Keep functions small.

Comment important logic.

Use type hints where appropriate.

Never break existing functionality.

If architecture needs improvement, refactor instead of patching.

## Website Philosophy

This website is an editorial resource, not a product catalog.

Every page should answer the rider's question first and recommend products only when they genuinely help solve the problem.

The goal is to become the most useful motorcycle buying and maintenance resource for Indian riders.

Content quality, trust, and user experience take priority over affiliate revenue.


# Asset Validation Rules

Before generating any HTML page, validate every asset referenced by the page.

This includes:

- Product images
- Motorcycle images
- Brand logos
- Category images
- Icons
# Motorcycle Image Acquisition

Motorcycle images are mandatory.

Never use placeholder motorcycle images in production.

## Image Source Priority

For every motorcycle:

1. Check if a verified local image already exists.
2. If not, download the official motorcycle image from the manufacturer's official website or official media/press resources.
3. Store the downloaded image locally using the project's naming convention.
4. Validate the image before using it.

Do not repeatedly download images that already exist locally.

## Validation

Every motorcycle image must:

- Match the correct motorcycle model.
- Be free of watermarks.
- Have good resolution (minimum 800px wide preferred).
- Be suitable for website display.
- Be stored inside the local motorcycle image directory.

## Fallback

If an official manufacturer image cannot be found:

1. Try other approved image sources configured by the project.
2. If no suitable image can be obtained, record the motorcycle in `reports/missing_motorcycle_images.json`.
3. Do not generate placeholder motorcycle images.

## Build Rule

Motorcycle images should be acquired and validated before HTML generation.

The build should generate a report showing:

- Images found locally
- Images downloaded
- Images missing
- Images skipped