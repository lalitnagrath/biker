import sys; sys.path.insert(0, '.')
from product_engine import compatibility_priority, normalize_category
from generate import load_all_data, load_bike_deals, merge_bike_deals

data = load_all_data()
deals = load_bike_deals()
merge_bike_deals(data['products'], deals)

bike = next(b for b in data['motorcycles'] if b['slug'] == 'bajaj-ct-110x')
print(f"Bike: {bike['brand']} {bike['model']}")
print(f"Type: {bike.get('type', '')}")
print(f"Slug: {bike['slug']}")
print()

# Show ALL products and their compatibility with this bike
print("=== All products with compatibility score for Bajaj CT 110X ===")
scored = []
for p in data['products']:
    cp = compatibility_priority(p, bike)
    if cp > 0:
        scored.append((cp, p))

scored.sort(key=lambda x: x[0])
for cp, p in scored:
    cat = normalize_category(p.get('category', ''))
    compat = p.get('compatible_bikes', [])
    print(f"  cp={cp} [{cat:15s}] {p['brand']:15s} {p['title'][:45]:45s} compat={compat}")

print()
print(f"Total compatible products: {len(scored)}")

# Check what the bike type matches
print()
print("=== Products matching by type ===")
bike_type = bike.get('type', '').lower()
for p in data['products']:
    compat = p.get('compatible_bikes', [])
    for c in compat:
        if c.lower().startswith('type:') and c.lower().endswith(bike_type):
            cat = normalize_category(p.get('category', ''))
            print(f"  [{cat:15s}] {p['brand']:15s} {p['title'][:45]:45s} compat={compat}")

print()
print("=== Products matching by brand ===")
bike_brand = bike.get('brand_slug', '').lower()
for p in data['products']:
    compat = p.get('compatible_bikes', [])
    for c in compat:
        if c.lower().startswith('brand:') and bike_brand in c.lower():
            cat = normalize_category(p.get('category', ''))
            print(f"  [{cat:15s}] {p['brand']:15s} {p['title'][:45]:45s} compat={compat}")
