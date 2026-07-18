import json, re

files = ['product_importer_final.json','honda-cb350-deals.json','helmets_new.json','bike-deals.json']
for fn in files:
    try:
        raw = json.load(open(fn))
    except Exception as e:
        print(fn, 'ERR', e); continue
    print('===', fn, type(raw).__name__, (len(raw) if hasattr(raw,'__len__') else ''))
    if isinstance(raw, list) and raw:
        d = raw[0]
        print('  keys:', list(d.keys()) if isinstance(d,dict) else type(d))
        s = json.dumps(d)
        for kw in ['rating','starRating','customerReviews','reviewsGlobal','ratingCount','reviewCount','aggregateRating']:
            m = re.search(r'"%s[^"]*"\s*:\s*(\{[^{}]*\}|[0-9.]+|null)' % re.escape(kw), s)
            if m:
                print('  ', kw, '=>', m.group(0)[:90])
