import json
from pathlib import Path

print("=== SYSTEM PATH ANALYSIS ===\n")

print(f"Current working directory: {Path.cwd()}")
print(f"Script location: {Path(__file__).absolute()}")
print()

print(f"1. data/products/helmets.json:")
products_path = Path("data/products/helmets.json")
print(f"   Absolute path: {products_path.absolute()}")
print(f"   Exists: {products_path.exists()}")
if products_path.exists():
    print(f"   Size: {products_path.stat().st_size} bytes")

print(f"\n2. Current relative paths:")
print(f"   cwd/data/products/helmets.json: {Path('data/products/helmets.json').absolute()}")
print(f"   cwd/data/products/helmets.json.exists(): {Path('data/products/helmets.json').exists()}")

print(f"\n3. Check if any helmets.json exists:")
for p in Path("data/products").glob("*.json"):
    if p.name == "helmets.json":
        print(f"   Found: {p.name} ({p.stat().st_size} bytes)")

print(f"\n4. Listing ALL JSON files in data/products:")
for p in sorted(Path("data/products").glob("*.json")):
    size = p.stat().st_size
    print(f"   {p.name:25s} ({size:6d} bytes)")
