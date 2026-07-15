import json, os, glob

# Load motorcycle data
motorcycles = []
for f in sorted(glob.glob('data/motorcycles/*.json')):
    with open(f, 'r', encoding='utf-8') as fh:
        motorcycles.append(json.load(fh))

# Load bike deals
with open('bike-deals.json', 'r', encoding='utf-8') as f:
    deals = json.load(f)

# Load motorcycle images source mapping
with open('data/all-motorcycles-india.json', 'r', encoding='utf-8') as f:
    all_bikes = json.load(f)

print(f"Motorcycles in DB: {len(motorcycles)}")
print(f"Bike deals available: {len(deals)}")
print(f"All motorcycles catalog: {len(all_bikes)}")

# Check existing images
img_dir = 'site/static/images/motorcycles'
existing = set()
if os.path.exists(img_dir):
    existing = {os.path.splitext(f)[0] for f in os.listdir(img_dir) if f.endswith('.jpg')}

missing = [b['slug'] for b in motorcycles if b['slug'] not in existing]
print(f"Existing images: {len(existing)}")
print(f"Missing images: {len(missing)}")

# Check all-motorcycles-india.json for image URLs
sample = all_bikes[0] if all_bikes else {}
print(f"\nSample all-motorcycles-india entry keys: {list(sample.keys()) if sample else 'empty'}")
if sample:
    for k, v in sample.items():
        if isinstance(v, str) and len(v) < 100:
            print(f"  {k}: {v}")
        elif isinstance(v, str):
            print(f"  {k}: {v[:80]}...")
        else:
            print(f"  {k}: {type(v).__name__}")

# Search deals for motorcycle matches
print("\n--- Searching deals for motorcycle keywords ---")
for slug in missing[:5]:
    keywords = slug.replace('-', ' ').split()
    # Remove brand names, keep model names
    model_words = [w for w in keywords if w not in ['bajaj','honda','hero','tvs','yamaha','ktm','suzuki','royal','enfield','harley','davidson','triumph']]
    
    for deal in deals:
        title = deal.get('itemInfo', {}).get('title', {}).get('displayValue', '').lower()
        score = sum(10 for w in model_words if w in title)
        if score >= 10:
            img = deal.get('images', {}).get('primary', {}).get('large', {}).get('url', '')
            if img:
                print(f"  {slug}: {title[:60]} -> {img[:60]}")
                break
