from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session
from db.models import UpgradeCollection, Product

eng = create_engine("sqlite:///bikereview.db")
with Session(eng) as s:
    rows = s.query(func.count()).select_from(UpgradeCollection.products).scalar()
    print("junction rows:", rows)
    dist = s.query(func.count(func.distinct(Product.asin))).join(Product.upgrade_collections).scalar()
    print("distinct products:", dist)
    print("per collection:")
    for slug, n in s.query(UpgradeCollection.slug, func.count(Product.asin)).join(UpgradeCollection.products).group_by(UpgradeCollection.slug).order_by(func.count(Product.asin).desc()):
        print("  %-14s %d" % (slug, n))
