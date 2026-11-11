# FastAPI server (v5): login, roles, pagination, PDF, report, audit
import os
from typing import List, Literal
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
import database as db, search, engine, pdf

EXTRA_DISCOUNT = float(os.getenv("MANAGER_EXTRA_DISCOUNT", 10))   # settings environment se aati hain
ROLES = {"Sales": 1, "Manager": 2, "Admin": 3}
HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Telecom CPQ Engine", version="5.0")
db.init_db()

# ---- Login check: har endpoint ke liye minimum role ----
token_of = lambda authorization: authorization.replace("Bearer ", "")

def need(role):
    def check(authorization: str = Header("")):
        user = db.user_from_token(token_of(authorization))
        if not user:
            raise HTTPException(401, "Pehle login karein")
        if ROLES[user["role"]] < ROLES[role]:
            raise HTTPException(403, f"{role} ya us se bara role chahiye")
        return user
    return check

sales, manager, admin = Depends(need("Sales")), Depends(need("Manager")), Depends(need("Admin"))

# ---- Data models ----
class Tier(BaseModel):
    min_qty: int = Field(ge=1)
    discount: float = Field(ge=0, le=100)

class Product(BaseModel):
    offering_id: str
    name: str
    operator: str
    description: str = ""
    category: str = "General"
    price: float = Field(gt=0)
    currency: str = "PKR"
    min_qty: int = Field(1, ge=1)
    max_discount: float = Field(0, ge=0, le=100)
    incompatible: List[str] = []
    requires: List[str] = []             # in ke baghair yeh product nahi bik sakta
    bundle_of: List[str] = []            # offer ke andar shamil items
    tiers: List[Tier] = []               # volume discount
    term_months: int = Field(0, ge=0)    # contract ki muddat
    setup_fee: float = Field(0, ge=0)    # ek dafa ki fee (per unit)
    item_type: Literal["Product", "Service", "Offer"] = "Product"
    status: Literal["Active", "Draft", "Retired"] = "Active"
    valid_until: str = ""
    billing: Literal["Monthly", "Yearly", "One-time", "Usage"] = "Monthly"
    source: str = "Manual"

class Provider(BaseModel):
    name: str
    code: str
    type: Literal["Operator", "Vendor"] = "Operator"
    currency: str
    tax_percent: float = Field(0, ge=0, le=100)

class Login(BaseModel):
    username: str
    password: str

class StatusBody(BaseModel):
    status: Literal["Active", "Draft", "Retired"]

class Item(BaseModel):
    offering_id: str
    qty: int = Field(gt=0)
    discount: float = Field(0, ge=0, le=100)

class Quote(BaseModel):
    operator: str
    customer: str
    items: List[Item] = Field(min_length=1)

class Decision(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]

page_q = Query(1, ge=1)
size_q = Query(10, ge=1, le=100000)

# ---- Login / Logout ----
@app.get("/", include_in_schema=False)
def home():
    return FileResponse(os.path.join(HERE, "static", "index.html"))

@app.post("/api/login")
def login(body: Login):
    session = db.login(body.username, body.password)
    if not session:
        raise HTTPException(401, "Username ya password ghalat hai")
    db.log(body.username, "Login")
    return session

@app.post("/api/logout")
def logout(authorization: str = Header("")):
    db.logout(token_of(authorization))
    return {"ok": True}

# ---- Providers ----
@app.get("/api/operators")
def operators(user=sales):
    return db.all_operators()

@app.post("/api/operators")
def add_provider(p: Provider, user=admin):
    db.save_operator(p.model_dump())
    db.log(user["username"], "Provider add", p.name)
    return {"added": p.name}

# ---- Catalog (sirf Admin badal sakta hai) ----
@app.get("/api/products")
def products(operator: str = None, q: str = "", item_type: str = "", status: str = "",
             page: int = page_q, size: int = size_q, user=sales):
    return db.list_products(operator, q, item_type, status, page, size)

@app.post("/api/products")
def add_products(items: List[Product], user=admin):          # 1 ya hazaron items ek saath
    for p in items:
        data = p.model_dump()
        db.save_product(data)
        search.index_product(data)
    db.log(user["username"], "Catalog save", f"{len(items)} item(s): {items[0].offering_id}...")
    return {"added": len(items)}

@app.delete("/api/products/{oid}")
def remove(oid: str, user=admin):
    db.delete_product(oid)
    search.remove_product(oid)
    db.log(user["username"], "Catalog delete", oid)
    return {"deleted": oid}

@app.post("/api/products/{oid}/status")
def change_status(oid: str, body: StatusBody, user=admin):
    if not db.set_product_status(oid, body.status):
        raise HTTPException(404, "Product nahi mila")
    db.log(user["username"], "Catalog status", f"{oid} -> {body.status}")
    return {"id": oid, "status": body.status}

@app.get("/api/search")
def smart_search(q: str, operator: str = None, user=sales):
    found = [(db.get_product(h["offering_id"]), h["score"]) for h in search.search(q, operator)]
    return [{**p, "score": s} for p, s in found if p and p["status"] == "Active"]

# ---- Quotes ----
@app.post("/api/quote")
def make_quote(quote: Quote, user=sales):
    op = db.get_operator(quote.operator)
    if not op:
        raise HTTPException(404, "Operator nahi mila")
    result = engine.validate_quote([i.model_dump() for i in quote.items], op["tax_percent"],
                                   EXTRA_DISCOUNT, quote.operator)
    result["currency"] = op["currency"]
    result["quote_id"] = db.save_quote(quote.operator, quote.customer, result, op["currency"], user["username"])
    db.log(user["username"], "Quote", f"#{result['quote_id']} {quote.operator} {result['status']}")
    return result

@app.get("/api/quotes")
def quote_history(operator: str = None, page: int = page_q, size: int = size_q, user=sales):
    only_mine = user["username"] if user["role"] == "Sales" else None       # Sales sirf apne quotes dekhta hai
    return db.list_quotes(operator, only_mine, page, size)

@app.post("/api/quotes/{qid}/decision")
def decide(qid: int, body: Decision, user=manager):
    if not db.set_status(qid, body.decision):
        raise HTTPException(404, "Quote nahi mila ya approval ka wait nahi kar raha")
    db.log(user["username"], "Decision", f"#{qid} {body.decision}")
    return {"quote_id": qid, "status": body.decision}

@app.get("/api/quotes/{qid}/pdf")
def quote_pdf(qid: int, user=sales):
    q = db.get_quote(qid)
    if not q or (user["role"] == "Sales" and q["created_by"] != user["username"]):
        raise HTTPException(404, "Quote nahi mila")
    if q["status"] != "APPROVED":
        raise HTTPException(400, "PDF sirf Approved quote ka banta hai")
    return Response(pdf.quote_pdf(q), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=quote-{qid}.pdf"})

# ---- Dashboard, report, audit ----
@app.get("/api/stats")
def get_stats(operator: str = None, user=sales):
    return db.stats(operator)

@app.get("/api/report")
def leakage_report(user=manager):
    return db.report()

@app.get("/api/audit")
def audit_log(page: int = page_q, size: int = size_q, user=admin):
    return db.list_audit(page, size)

# ---- TM Forum style endpoints (industry standard format) ----
@app.get("/tmf-api/productCatalogManagement/v4/productOffering")      # TMF620
def tmf620(operator: str = None, user=sales):
    return [{"id": p["offering_id"], "name": p["name"], "description": p["description"],
             "lifecycleStatus": p["status"], "isBundle": p["item_type"] == "Offer",
             "bundledProductOffering": [{"id": i} for i in p["bundle_of"]], "category": [{"name": p["category"]}],
             "productOfferingPrice": [{"priceType": "recurring",
                 "price": {"taxIncludedAmount": {"unit": p["currency"], "value": p["price"]}}}],
             "@type": "ProductOffering"} for p in db.list_products(operator, size=100000)["items"]]

@app.get("/tmf-api/quoteManagement/v4/quote")                         # TMF648
def tmf648(operator: str = None, user=manager):
    state = {"APPROVED": "approved", "NEEDS_APPROVAL": "pending", "REJECTED": "rejected"}
    return [{"id": str(q["id"]), "state": state[q["status"]], "description": q["customer"],
             "quoteDate": q["created"], "@type": "Quote"} for q in db.list_quotes(operator, size=100000)["items"]]
