"""
Trace why helmet products don't appear in generated HTML
"""
import sys
from pathlib import Path

print("=== HELMET PRODUCT PIPELINE TRACE ===\n")

# Step 1: Verify product library exists
products_path = Path("C:/Users/deepika/Desktop/test/biker/data/products/helmets.json")
print(f"1. Checking product library:")
print(f"   Path: {products_path}")
print(f"   Exists: {products_path.exists()}")

# Step 2: Load helmet products
try:
    with open(products_path, "r", encoding="utf-8") as f:
        helmets = []
        headers = []
        for i, line in enumerate(f):
            if i < 3:
                headers.append(line.rstrip())
            else:
                break
        print(f"   First few lines of helmets.json:")
        for header in headers:
            print(f"   {header}")
except Exception as e:
    print(f"   ERROR loading products: {e}")
    sys.exit(1)

# Step 3: Find actual products
if products_path.exists():
    with open(products_path, "r", encoding="utf-8") as f:
        import json
        full_data = json.load(f)
        print(f"\n2. Helmet products loaded:")
        print(f"   Total products in file: {len(full_data)}")
        
        # Analyze first product
        if full_data:
            sample = full_data[0]
            print(f"   First product keys: {list(sample.keys())}")
            print(f"   Sample product: {json.dumps(sample, indent=2)[:200]}...")
        
        # Check for empty array issue
        if len(full_data) == 0:
            print(f"   WARNING: helmets.json is empty!")
else:
    print(f"   ERROR: Product file not found!")

# Step 4: Simulate product engine recommendation
print(f"\n3. Simulating recommend_for_category:")
try:
    from product_engine import recommend_for_category
    
    # Generate test data if file is empty
    if products_path.exists():
        with open(products_path, "r", encoding="utf-8") as f:
            products = json.load(f)
    else:
        print(f"   Cannot test recommend_for_category - file not found")
        sys.exit(1)
    
    recommended = recommend_for_category(products, "Helmet")
    print(f"   RECOMMEND_FOR_CATEGORY('Helmet') returned:")
    print(f"     Count: {recommended.get('count', 'NO COUNT')}")
    print(f"     Most Popular: {'YES' if recommended.get('most_popular') else 'NO'}")
    print(f"     Products array: {len(recommended.get('products', []))} items")
    
    if recommended.get('most_popular'):
        mp = recommended['most_popular']
        print(f"     Most Popular details:")
        print(f"       Title: {mp.get('title', 'NO TITLE')}")
        print(f"       Slug: {mp.get('slug', 'NO SLUG')}")
        print(f"       ASIN: {mp.get('asin', 'NO ASIN')}")
        print(f"       Status: {mp.get('status', 'NO STATUS')}")
        print(f"       Image: {mp.get('image', 'NO IMAGE')}")
        print(f"       Affiliate: {mp.get('affiliate_url', 'NO AFFILIATE')}")
    
    # Check template context simulation
    print(f"\n4. Template context simulation:")
    context_products = recommended.get('products', [])
    print(f"   Context products for template: {len(context_products)}")
    
    if context_products:
        sample_product = context_products[0]
        print(f"   Sample product for template:")
        print(f"     Keys: {list(sample_product.keys())}")
    else:
        print(f"   WARNING: No products in template context!")
        
except Exception as e:
    print(f"   ERROR in recommend_for_category: {e}")
    import traceback
    traceback.print_exc()

print(f"\n=== DIAGNOSIS ===")
print(f"If helmet buying guide pages show 0 products, the failure point is likely:")
print(f"1. helmets.json file is empty or not found")
print(f"2. recommend_for_category returns empty 'products' array")
print(f"3. Template context doesn't receive product data")
print(f"4. Template rendering fails to iterate over products")

print(f"\n=== CURRENT STATUS ===")
print(f"helmets.json exists: {products_path.exists()}")
if products_path.exists():
    with open(products_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"Total products in file: {len(data)}")
else:
    print(f"Total products: 0 (file not found)")
