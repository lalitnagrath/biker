import json
from pathlib import Path

def fix_title(title):
    if not title:
        return title
    # Remove ZWNJ and other problematic unicode
    import re
    # Remove zero-width non-joiner and other problematic characters
    fixed = re.sub(r'[\u200e\u200f\u2028\u2029]', '', title)
    return fixed

def main():
    deals_path = Path('bike-deals.json')
    
    if not deals_path.exists():
        print('ERROR: bike-deals.json not found')
        return
    
    with open(deals_path, 'r', encoding='utf-8', errors='ignore') as f:
        deals = json.load(f)
    
    print(f'Loaded {len(deals)} deals')
    
    # Check for issues
    issues_found = 0
    for deal in deals:
        title = deal.get('itemInfo', {}).get('title', {}).get('displayValue', '')
        if not title:
            continue
            
        if '\u200e' in title:
            issues_found += 1
            print(f'Issue: ZWNJ in title')
            print(f'  Original: {repr(title[:60])}')
            fixed_title = fix_title(title)
            deal['itemInfo']['title']['displayValue'] = fixed_title
            print(f'  Fixed:    {repr(fixed_title[:60])}')
    
    if issues_found > 0:
        with open(deals_path, 'w', encoding='utf-8') as f:
            json.dump(deals, f, indent=2, ensure_ascii=False)
        print(f'Fixed {issues_found} issues and saved to bike-deals.json')
    else:
        print('No ZWNJ issues found')

if __name__ == '__main__':
    main()