import pytest, database as db, engine

@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB", str(tmp_path / "t.db"))
    db.init_db()
    db.save_product({"offering_id": "A", "name": "Ent", "price": 2500, "min_qty": 5, "max_discount": 20, "incompatible": ["B"], "operator": "Jazz"})
    db.save_product({"offering_id": "B", "name": "Basic", "price": 900, "min_qty": 2, "max_discount": 10, "incompatible": ["A"], "operator": "Jazz"})

def quote(items, **kw):
    return engine.validate_quote(items, **kw)

def item(oid, qty=5, discount=0):
    return {"offering_id": oid, "qty": qty, "discount": discount}

def test_approved_price():
    r = quote([item("A", 10, 15)])
    assert r["status"] == "APPROVED" and r["total"] == 21250

def test_min_qty():
    assert quote([item("A", 2)])["status"] == "REJECTED"

def test_discount_needs_approval():
    assert quote([item("A", 5, 25)], extra_discount=10)["status"] == "NEEDS_APPROVAL"

def test_discount_too_high_rejected():
    assert quote([item("A", 5, 35)], extra_discount=10)["status"] == "REJECTED"

def test_incompatible():
    r = quote([item("A"), item("B")])
    assert r["status"] == "REJECTED" and len(r["reasons"]) == 1

def test_wrong_operator():
    assert quote([item("A")], operator="Zong")["status"] == "REJECTED"

def test_unknown_product():
    assert quote([item("X", 1)])["status"] == "REJECTED"

def test_tax():
    assert quote([item("B", 10)], tax_percent=18)["total"] == 10620

def test_retired_product_rejected():
    db.set_product_status("B", "Retired")
    assert quote([item("B")])["status"] == "REJECTED"

def test_expired_offer_rejected():
    db.save_product({"offering_id": "O", "name": "Old Offer", "price": 100, "item_type": "Offer", "valid_until": "2020-01-01"})
    r = quote([item("O", 1)])
    assert r["status"] == "REJECTED" and "expire" in r["reasons"][0]

# ---- v5: bundles, dependencies, tiers, contract, leakage ----
def test_volume_tier_discount():
    db.save_product({"offering_id": "T", "name": "Tiered", "price": 100, "max_discount": 10, "tiers": [{"min_qty": 50, "discount": 5}, {"min_qty": 200, "discount": 10}]})
    assert quote([item("T", 10)])["total"] == 1000
    assert quote([item("T", 50)])["total"] == 4750
    assert quote([item("T", 200)])["total"] == 18000

def test_contract_term_and_setup_fee():
    db.save_product({"offering_id": "C", "name": "Contract", "price": 1000, "term_months": 12, "setup_fee": 500})
    assert quote([item("C", 2)])["total"] == 1000 * 2 * 12 + 500 * 2

def test_dependency_required():
    db.save_product({"offering_id": "D", "name": "Needs A", "price": 100, "requires": ["A"]})
    assert quote([item("D", 1)])["status"] == "REJECTED"
    assert quote([item("D", 1), item("A")])["status"] == "APPROVED"

def test_bundle_includes_parts():
    db.save_product({"offering_id": "BUN", "name": "Bundle", "price": 3000, "item_type": "Offer", "bundle_of": ["A"]})
    db.save_product({"offering_id": "D", "name": "Needs A", "price": 100, "requires": ["A"]})
    assert quote([item("BUN", 1), item("D", 1)])["status"] == "APPROVED"      # bundle ne A de diya
    r = quote([item("BUN", 1), item("A")])
    assert r["status"] == "REJECTED" and "shamil" in r["reasons"][0]

def test_leakage_amount():
    r = quote([item("A", 10, 35)], extra_discount=10)          # limit 20%, maang 35%
    assert r["status"] == "REJECTED" and r["leakage"] == 2500 * 10 * 15 / 100
