print("=== HELMET PRODUCT PIPELINE DEBUG ===\n")

# Step 1: Check data/products/helmets.json
print("1. Checking data/products/helmets.json:")
try:
    with open("data/products/helmets.json", "r", encoding="utf-8") as f:
        helmets = json.load(f)
    print(f"   SUCCESS: Loaded {len(helmets)} helmet products")
    
    # Check status distribution
    approved = [h for h in helmets if h.get("status") == "approved"]
    draft = [h for h in helmets if h.get("status") == "draft"]
    print(f"   Approved: {len(approved)}, Draft: {len(draft)}")
    
    # Check image/affiliate
    with_image = [h for h in helmets if h.get("image")]
    with_affiliate = [h for h in helmets if h.get("affiliate_url")]
    print(f"   With image: {len(with_image)}, With affiliate: {len(with_affiliate)}")
    
except Exception as e:
    print(f"   ERROR: {e}")

print("\n2. Calling recommend_for_category from product_engine:")
try:
    from product_engine import recommend_for_category
    
    recommended = recommend_for_category(helmets, "Helmet")
    print(f"   SUCCESS: recommend_for_category returned")
    print(f"   Count: {recommended['count']}")
    print(f"   Most Popular: {'YES' if recommended.get('most_popular') else 'NO'}")
    print(f"   Editors Choice: {'YES' if recommended.get('editors_choice') else 'NO'}")
    print(f"   Best Value: {'YES' if recommended.get('best_value') else 'NO'}")
    print(f"   Premium Pick: {'YES' if recommended.get('premium_pick') else 'NO'}")
    
    if recommended.get('most_popular'):
        mp = recommended['most_popular']
        print(f"   Most Popular product: {mp.get('title', 'NO TITLE')} ({mp.get('asin', 'NO ASIN')})")
        print(f"   Status: {mp.get('status')}")
        print(f"   Image: {'YES' if mp.get('image') else 'NO'}")
        print(f"   Affiliate: {'YES' if mp.get('affiliate_url') else 'NO'}")
    
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n3. Context passed to bestof.html template:")
print("   The guide context (line ~1219 in generate.py) would include:")
print("     context['guide_products'] = recommended['products']  # Array from recommend_for_category")
print(f"   Total products in template context: {len(recommended.get('products', []))}")

if recommended.get('products'):
    first = recommended['products'][0]
    print(f"   First product details in template:")
    print(f"     Title: {first.get('title', 'NO TITLE')}")
    print(f"     Category: {first.get('category')}")
    print(f"     Status: {first.get('status')}")
    print(f"     Image: {first.get('image', 'NO IMAGE')}")
    print(f"     Affiliate: {first.get('affiliate_url', 'NO AFFILIATE')}")
else:
    print("   WARNING: No products in template context!")

print("\n4. TEMPLATE ANALYSIS (bestof.html):")
print("   Looking at the template engine loops and conditionals...")
print("   The issue is likely in:")
print("   - recommend_for_category returning empty 'products' array")
print("   - Or products being filtered out by validation")
print("   - Or template syntax issues")

print("\n=== SUMMARY ===")
print("If the helmet buying guide page shows 0 products, the failure point is likely:")
print("1. recommend_for_category() returning empty 'products' array")
print("2. The template receiving no product data")
print("3. OR products being filtered out earlier in the pipeline")
print(f"\nCurrent state:")
print(f"- Total helmets.json: {len(helmets)}")
print(f"- Recommended products: {len(recommended.get('products', []))}")
print(f"- Context products for template: {len(recommended.get('products', []))}")

if len(recommended.get('products', [])) == 0:
    print("\n*** DIAGNOSIS: recommend_for_category is returning empty products array ***")
    print("This means the recommendation engine is filtering out ALL helmet products")
else:
    print("\n*** Products ARE being recommended - check template rendering ***")
