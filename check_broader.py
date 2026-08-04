import os
import re
import urllib.request
import urllib.error
import json
from urllib.parse import urljoin

BASE_URL = "http://localhost:8080"

def fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace"), resp.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception as e:
        return None, str(e)

# Get top-level motorcycle pages only (not maintenance subpages)
site_dir = r'C:\Users\deepika\Desktop\test\biker\site\motorcycles'
pages = []
for item in os.listdir(site_dir):
    full = os.path.join(site_dir, item, 'index.html')
    if os.path.isfile(full):
        rel = f"/motorcycles/{item}/index.html"
        pages.append(rel)

print(f"Checking {len(pages)} top-level motorcycle pages")

all_broken = {}
total_checked = 0

for page in pages:
    html, status = fetch(f"{BASE_URL}{page}")
    if html is None:
        continue

    m = re.search(r'window\.PIMP_MY_RIDE_DATA\s*=\s*({.*?});', html, re.DOTALL)
    if not m:
        continue

    total_checked += 1
    data = json.loads(m.group(1))
    broken = []
    for coll in data.get("collections", []):
        for prod in coll.get("compatibleProducts", []):
            img = prod.get("image", "")
            if not img:
                continue
            full_url = urljoin(f"{BASE_URL}{page}", img)
            try:
                req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status != 200:
                        broken.append((img, full_url, resp.status))
            except urllib.error.HTTPError as e:
                broken.append((img, full_url, e.code))
            except Exception as e:
                broken.append((img, full_url, str(e)))

    if broken:
        all_broken[page] = broken
        print(f"BROKEN in {page}: {len(broken)} images")
        for img, url, code in broken:
            print(f"  [{code}] {img}")

print(f"\n=== Checked {total_checked} pages with Pimp My Ride ===")
print(f"Pages with broken images: {len(all_broken)}")
print(f"Total broken images: {sum(len(v) for v in all_broken.values())}")
