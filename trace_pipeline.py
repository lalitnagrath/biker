import json
from pathlib import Path

print("=== Product Pipeline Trace ===\n")

# Step 1: Show what generate.py loads
print("1. HELMETS.PY LOAD:")
products_path = Path("data/products/helmets.json")
if products_path.exists():
    with open(products_path, "r", encoding="utf-8") as f:
        helmets = json.load(f)
    print(f"   Loaded {len(helmets)} products from helmets.json")
else:
    print("   helmets.json NOT FOUND")
    exit(1)

# Step 2: Show product details
print("\n2. HELMET PRODUCT ANALYSIS:")
approved = [p for p in helmets if p.get("status") == "approved"]
draft = [p for p in helmets if p.get("status") == "draft"]
print(f"   Approved helmets: {len(approved)}")
print(f"   Draft helmets: {len(draft)}")

# Step 3: Check recommendations
print("\n3. RECOMMENDATION ENGINE:")
try:
    from product_engine import rank_products
    ranked = rank_products(helmets, "")
    print(f"   rank_products returned {len(ranked)} helmets")
    
    # Show first product details
    if ranked:
        sample = ranked[0]
        print(f"   Sample top product: {sample.get('title', 'NO TITLE')} ({sample.get('asin', 'NO ASIN')})")
        print(f"   Status: {sample.get('status')}")
        print(f"   Image: {'YES' if sample.get('image') else 'NO'}")
        print(f"   Affiliate: {'YES' if sample.get('affiliate_url') else 'NO'}")
except Exception as e:
    print(f"   rank_products failed: {e}")

print("\n4. HEADING GUIDE CONTEXT (SIMULATION):")
# Simulate what best-of.html context would receive

# Get bike page context
from generate import load_motorcycles, build_motorcycle_articles

motorcycles_data = load_motorcycles()
all_articles = load_all_articles()
articles_by_category = build_motorcycle_articles(all_articles)

helmet_motorcycles = motorcycles_data
if helmet_motorcycles:
    sample_bike = helmet_motorcycles[0]
    
    # Get products for this bike
    from product_engine import match_products_to_motorcycle
    bike_products = match_products_to_motorcycle(sample_bike, helmets)
    
    print(f"   Bike selection context (for {sample_bike.get('model', 'unknown bike')}):")
    print(f"     Compatible products found: {len(bike_products)}")
    
    # Show product details
    if bike_products:
        print(f"     First compatible product: {bike_products[0].get('title', 'NO TITLE')} ({bike_products[0].get('category')})")
        print(f"     Status: {bike_products[0].get('status')}")
        print(f"     Image: {'YES' if bike_products[0].get('image') else 'NO'}")

print("\n5. CHECK PAGE CONTEXT:")
print("   The helmet guide page would receive:")
print("     - helmet_motorcycles: [array of motorcycle models]")
print("     - articles_by_category: {category: [articles]}")
print("     - guide_content: {category: {guide: {...}}}")
print("     - helmet_products: [all helmet products]")
print(f"   Total helmet products available: {len(helmets)}")

# Check recommendation engine directly
print("\n6. RECOMMENDATION ENGINE DIRECT CALL:")
try:
    from product_engine import recommend_products
    
    # This is what bestof.html:6 would call
    recommended = recommend_products(helmets, 'helmet')
    print(f"   recommend_products(helmets, 'helmet') returned {len(recommended)} products")
    
    if recommended:
        print(f"   Top product: {recommended[0].get('title', 'NO TITLE')}")
        print(f"   Status: {recommended[0].get('status')}")
        print(f"   Rating: {recommended[0].get('editor_rating', 0)}")
    else:
        print("   WARNING: No products returned!")
except Exception as e:
    print(f"   Error calling recommend_products: {e}")

print("\n=== ANALYSIS COMPLETE ===")
print("If the helmet guide page shows no products, the issue is likely:")
print("1. Products missing image/affiliate URL validation")
print("2. recommend_products returning empty array")
print("3. Template rendering issue with the products variable")

# Final check
print("\n=== FINAL VALIDATION ===")
print("Generated HTML pages would only show products that:")
print("1. Have valid image files in static/images/products/")
print("2. Have affiliate URLs")
print("3. Pass all validation checks")
print(f"Current helmet products: {len(helmets)}")
print(f"Products with images: {sum(1 for p in helmets if p.get('image'))}")
print(f"Products with affiliate URLs: {sum(1 for p in helmets if p.get('affiliate_url'))}")
print(f"Approved products: {len([p for p in helmets if p.get('status') == 'approved'])}")
