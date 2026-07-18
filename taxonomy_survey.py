import json, os
from collections import Counter

cat_counter = Counter()
type_counter = Counter()
file_cats = {}

for f in sorted(os.listdir('data/products')):
    if not f.endswith('.json'): continue
    with open(f'data/products/{f}') as fh:
        products = json.load(fh)
    cats = set()
    types = set()
    for p in products:
        cat = p.get('category', '')
        typ = p.get('type', '')
        cat_counter[cat] += 1
        types.add(typ)
        cats.add(cat)
    file_cats[f] = {'count': len(products), 'categories': cats, 'types': types}

print('=== FILES ===')
for f, info in sorted(file_cats.items()):
    print(f'{f:40s} {info["count"]:3d} products  cats={info["categories"]}  types={info["types"]}')

print()
print('=== ALL CATEGORIES ===')
for cat, cnt in cat_counter.most_common():
    print(f'  {cat or "(empty)":30s} {cnt:3d}')

print()
print('=== ALL TYPES ===')
for typ, cnt in sorted(type_counter.items()):
    print(f'  {typ or "(empty)":30s} {cnt:3d}')

# Show helmets with bluetooth/headset/visor/camera/speaker in title
print()
print('=== HELMETS WITH ACCESSORY KEYWORDS ===')
with open('data/products/helmets.json') as fh:
    helmets = json.load(fh)
accessory_kw = ['bluetooth', 'headset', 'visor', 'camera', 'speaker', 'earphone', 'intercom', 'mic', 'communication']
for p in helmets:
    title = p.get('title', '').lower()
    if any(kw in title for kw in accessory_kw):
        print(f'  [{p.get("category")}/{p.get("type")}] {p["title"][:80]}')
        print(f'    brand={p.get("brand")} price={p.get("amazon",{}).get("price")} rating={p.get("amazon",{}).get("rating")}')

# Show cameras.json
print()
print('=== CAMERAS.JSON ===')
with open('data/products/cameras.json') as fh:
    cameras = json.load(fh)
for p in cameras:
    print(f'  [{p.get("category")}/{p.get("type")}] {p["title"][:80]}')
