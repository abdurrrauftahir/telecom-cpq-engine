import sys, types, pytest
fake = types.ModuleType("search")                               # AI model ke baghair test (CI tez rahe)
fake.index_product = lambda p: None
fake.remove_product = lambda oid: None
fake.search = lambda q, operator=None, n=3: [{"offering_id": "A", "score": 0.9}]
sys.modules["search"] = fake

import database as db
from fastapi.testclient import TestClient
import main

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB", str(tmp_path / "t.db"))
    db.init_db()
    for name, role in [("admin", "Admin"), ("manager", "Manager"), ("sales", "Sales")]:
        db.create_user(name, name + "123", role)
    db.save_operator({"name": "Jazz", "code": "JAZZ", "currency": "PKR", "tax_percent": 10})
    db.save_product({"offering_id": "A", "name": "Ent", "price": 2500, "min_qty": 5, "max_discount": 20, "operator": "Jazz"})
    return TestClient(main.app)

def auth(client, user):
    token = client.post("/api/login", json={"username": user, "password": user + "123"}).json()["token"]
    return {"Authorization": "Bearer " + token}

def new_quote(client, headers, discount):
    return client.post("/api/quote", headers=headers, json={"operator": "Jazz", "customer": "ACME",
                       "items": [{"offering_id": "A", "qty": 10, "discount": discount}]}).json()

def test_login_required_and_wrong_password(client):
    assert client.get("/api/products").status_code == 401
    assert client.post("/api/login", json={"username": "admin", "password": "bad"}).status_code == 401

def test_roles(client):
    sales, manager, admin = auth(client, "sales"), auth(client, "manager"), auth(client, "admin")
    assert client.get("/api/products", headers=sales).status_code == 200
    assert client.get("/api/report", headers=sales).status_code == 403
    assert client.get("/api/report", headers=manager).status_code == 200
    assert client.get("/api/audit", headers=manager).status_code == 403
    assert client.get("/api/audit", headers=admin).status_code == 200
    body = [{"offering_id": "Z", "name": "Z", "operator": "Jazz", "price": 5}]
    assert client.post("/api/products", headers=sales, json=body).status_code == 403
    assert client.post("/api/products", headers=admin, json=body).status_code == 200

def test_pagination(client):
    admin = auth(client, "admin")
    client.post("/api/products", headers=admin, json=[{"offering_id": f"P{i}", "name": f"Prod {i}", "operator": "Jazz", "price": 5} for i in range(25)])
    page = client.get("/api/products?size=10&page=3", headers=admin).json()
    assert page["total"] == 26 and page["pages"] == 3 and len(page["items"]) == 6
    assert client.get("/api/products?q=Prod 7", headers=admin).json()["total"] == 1

def test_approval_pdf_and_report(client):
    sales, manager = auth(client, "sales"), auth(client, "manager")
    q = new_quote(client, sales, 25)                                  # limit 20%, maang 25%
    assert q["status"] == "NEEDS_APPROVAL"
    assert client.post(f"/api/quotes/{q['quote_id']}/decision", headers=sales, json={"decision": "APPROVED"}).status_code == 403
    assert client.get(f"/api/quotes/{q['quote_id']}/pdf", headers=sales).status_code == 400    # abhi approved nahi
    assert client.post(f"/api/quotes/{q['quote_id']}/decision", headers=manager, json={"decision": "APPROVED"}).status_code == 200
    pdf = client.get(f"/api/quotes/{q['quote_id']}/pdf", headers=sales)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    new_quote(client, sales, 60)                                       # bohat zyada discount: reject
    row = client.get("/api/report", headers=manager).json()[0]
    assert row["rejected"] == 1 and row["prevented"] > 0 and row["approved_exceptions"] > 0

def test_sales_sees_only_own_quotes_and_audit(client):
    sales, manager, admin = auth(client, "sales"), auth(client, "manager"), auth(client, "admin")
    new_quote(client, manager, 0)
    new_quote(client, sales, 0)
    assert client.get("/api/quotes", headers=sales).json()["total"] == 1
    assert client.get("/api/quotes", headers=manager).json()["total"] == 2
    actions = [a["action"] for a in client.get("/api/audit", headers=admin).json()["items"]]
    assert "Quote" in actions and "Login" in actions
