#!/usr/bin/env python3
"""
Fix unicode issues in bike-deals.json
"""
import json
import sys
from pathlib import Path

def fix_zwnj_in_title(title):
    """Remove ZWNJ and surrogate characters from title."""
    if not title:
        return title
    # Remove U+200E Zero Width Non-Joiner
    fixed = title.replace('\u200e', '')
    # Remove any surrogate characters (should not appear in valid JSON)
    fixed = ''.join(c for c in fixed if ord(c) >= 32 and ord(c) <= 0x10FFFF)
    return fixed

def main():
    deals_path = Path('bike-deals.json')
    
    if not deals_path.exists():
        print("ERROR: bike-deals.json not found")
        sys.exit(1)
    
    with open(deals_path, 'r', encoding='utf-8', errors='ignore') as f:
        deals = json.load(f)
    
    print(f"Loaded {len(deals)} deals")
    
    # Check for issues
    issues_found = 0
    for i, deal in enumerate(deals):
        title = deal.get('itemInfo', {}).get('title', {}).get('displayValue', '')
        if not title:
            continue
            
        has_zwnj = any(c == '\u200e' for c in title)
        has_surrogate = any(0xD800 <= ord(c) <= 0xDFFF for c in title)
        
        if has_zwnj or has_surrogate:
            issues_found += 1
            print(f"Issue at index {i}: ZWNJ={has_zwnj}, surrogate={has_surrogate}")
            print(f"  Original: {repr(title[:60])}")
            fixed_title = fix_zwnj_in_title(title)
            deal['itemInfo']['title']['displayValue'] = fixed_title
            print(f"  Fixed:    {repr(fixed_title[:60])}")
            print()
    
    if issues_found > 0:
        # Save the fixed data
        with open(deals_path, 'w', encoding='utf-8') as f:
            json.dump(deals, f, indent=2, ensure_ascii=False)
        print(f"Fixed {issues_found} issues in bike-deals.json")
    else:
        print("No unicode issues found")
    
    print("Done")

if __name__ == '__main__':
    main()