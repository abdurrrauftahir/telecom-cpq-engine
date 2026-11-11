# operators.json, catalog.json aur users.json ko database + AI search mein load karta hai
import json, os, database as db, search

HERE = os.path.dirname(os.path.abspath(__file__))
load = lambda f: json.load(open(os.path.join(HERE, f), encoding="utf-8"))

db.init_db()
for o in load("operators.json"):
    db.save_operator(o)
for u in load("users.json"):                    # demo users (asli use mein password badlein)
    db.create_user(u["username"], u["password"], u["role"])
products = load("catalog.json")
for p in products:
    db.save_product(p)
    search.index_product(p)
print(f"✅ {len(products)} products aur {len(load('users.json'))} users load ho gaye")
