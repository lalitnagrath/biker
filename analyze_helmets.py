#!/usr/bin/env python3
import sys

print("=== COMPREHENSIVE HELMET PIPELINE ANALYSIS ===\n")

# Step 1: Load product data
print("1. Loading product library...")

try:
    from generate import load_all_data
    data = load_all_data()
    print(f"   ✓ Successfully loaded {len(data['products'])} total products")
    
    # Find helmet products
    helmet_products = [p for p in data['products'] if p.get('category') == 'Helmet']
    print(f"   ✓ Found {len(helmet_products)} helmet products")
    
    if helmet_products:
        print(f"   ✓ First helmet product has keys: {list(helmet_products[0].keys())}")
        print(f"   ✓ First helmet product status: {helmet_products[0].get('status')}")
        print(f"   ✓ First helmet product image: {bool(helmet_products[0].get('image'))}")
        print(f"   ✓ First helmet product affiliate: {bool(helmet_products[0].get('affiliate_url'))}")
        
        # Count by status
        status_counts = {}
        for h in helmet_products:
            status = h.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        print(f"   ✓ Helmet products by status: {status_counts}")
    
except Exception as e:
    print(f"   ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 2: Test recommendation engine
print("\n2. Testing recommend_for_category...")

try:
    from product_engine import recommend_for_category
    
    recommended = recommend_for_category(data['products'], 'Helmet')
    print(f"   ✓ recommend_for_category('Helmet') returned:")
    print(f"     Count: {recommended.get('count', 'UNKNOWN')}")
    print(f"     Most Popular: {'YES' if recommended.get('most_popular') else 'NO'}")
    print(f"     Products array length: {len(recommended.get('products', []))}")
    
    if recommended.get('products'):
        first = recommended['products'][0]
        print(f"   ✓ First product details:")
        print(f"     Title: {first.get('title', 'MISSING')[:60]}...")
        print(f"     Status: {first.get('status')}")
        print(f"     Image: {'✓' if first.get('image') else '✗'}")
        print(f"     Affiliate: {'✓' if first.get('affiliate_url') else '✗'}")
    else:
        print(f"   ⚠️  No products returned!")
        
except Exception as e:
    print(f"   ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()

# Step 3: Template context analysis
print("\n3. Template context analysis...")
context_products = recommended.get('products', [])
print(f"   Template context products: {len(context_products)}")

if context_products:
    print(f"   ✓ Products available for template")
    valid = [p for p in context_products if p.get('image') and p.get('affiliate_url')]
    print(f"   ✓ Valid products for display: {len(valid)}")
else:
    print(f"   ✗ No products - template will show empty")

# Step 4: Recommendation engine breakdown
print("\n4. Recommendation engine breakdown...")
try:
    from product_engine import recommend_products
    
    ranked = recommend_products(data['products'], 'helmet')
    print(f"   ✓ recommend_products('helmet') returned: {len(ranked)} products")
    
    if ranked:
        print(f"   ✓ First ranked product status: {ranked[0].get('status')}")
        print(f"   ✓ First ranked product image: {'✓' if ranked[0].get('image') else '✗'}")
        print(f"   ✓ First ranked product affiliate: {'✓' if ranked[0].get('affiliate_url') else '✗'}")
        
        # Find approved products
        approved = [p for p in ranked if p.get('status') == 'approved']
        print(f"   ✓ Approved products in ranked list: {len(approved)}")
        
        # Find products with image and affiliate
        complete = [p for p in ranked if p.get('image') and p.get('affiliate_url')]
        print(f"   ✓ Products with image + affiliate: {len(complete)}")
        
except Exception as e:
    print(f"   ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("DIAGNOSIS:")

if not context_products:
    print("🚨 PROBLEM: The helmet guide page will show NO products")
    print("   Reasons:")
    print("   1. All helmet products missing image or affiliate URL")
    print("   2. All helmet products have status != 'approved'")
    print("   3. All helmet products filtered out by recommendation engine")
    print("   4. Template context receives empty array")
    
    # Check helmet products in data
    print(f"\n   Actual helmet products in data: {len(helmet_products)}")
    approved_helmets = [h for h in helmet_products if h.get('status') == 'approved']
    print(f"   Approved helmet products: {len(approved_helmets)}")
    
    image_helmets = [h for h in helmet_products if h.get('image') and h.get('affiliate_url')]
    print(f"   Helmets with image + affiliate: {len(image_helmets)}")
    
    if len(image_helmets) == 0:
        print(f"   🚨 CRITICAL: NO helmet products with both image AND affiliate URL!")
        print(f"   This means ALL helmets will be filtered out.")
    else:
        print(f"   ⚠️  Some helmets have image + affiliate but are still filtered.")

else:
    print("✅ Product pipeline is working - products are available for templates")
    print(f"   If helmets still not displayed, issue is in template logic or validation")

print("="*60)