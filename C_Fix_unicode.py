import json
import re

print("Fixing unicode issues in bike-deals.json...")

# Read the original file
with open('bike-deals.json', 'r', encoding='utf-8') as f:
    deals = json.load(f)

issues_found = 0
for i, deal in enumerate(deals):
    title = deal.get('itemInfo', {}).get('title', {}).get('displayValue', '')
    if not title:
        continue
    
    # Check for ZWNJ (U+200E)
    if '\u200e' in title:
        issues_found += 1
        print(f"Fixing ZWNJ in deal {i}: {repr(title[:60])}")
        # Remove ZWNJ and other problematic characters
        fixed_title = re.sub(r'[\u200e\u200f\u2028\u2029]', '', title)
        deal['itemInfo']['title']['displayValue'] = fixed_title
        print(f"  Fixed: {repr(fixed_title[:60])}")

if issues_found > 0:
    with open('bike-deals.json', 'w', encoding='utf-8') as f:
        json.dump(deals, f, indent=2, ensure_ascii=False)
    print(f"Successfully fixed {issues_found} issues")
else:
    print("No issues found")

print("Done!")