# SQLite database (v5): providers, products, quotes, users, sessions, audit log
import sqlite3, json, os, hashlib, hmac, secrets

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cpq.db")
LISTS = ("incompatible", "bundle_of", "requires", "tiers")        # JSON ke taur par store hoti hain
COLS = ["offering_id", "name", "description", "category", "price", "currency", "min_qty", "max_discount",
        "incompatible", "operator", "item_type", "status", "valid_until", "billing", "source",
        "bundle_of", "requires", "tiers", "term_months", "setup_fee"]
DEFAULTS = {"description": "", "category": "General", "currency": "PKR", "min_qty": 1, "max_discount": 0,
            "incompatible": [], "operator": "Default", "item_type": "Product", "status": "Active",
            "valid_until": "", "billing": "Monthly", "source": "Manual", "bundle_of": [], "requires": [],
            "tiers": [], "term_months": 0, "setup_fee": 0}

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row          # rows ko dict ki tarah use karne ke liye
    return c

def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS operators(name TEXT PRIMARY KEY, code TEXT, type TEXT, currency TEXT, tax_percent REAL);
        CREATE TABLE IF NOT EXISTS products(
            offering_id TEXT PRIMARY KEY, name TEXT, description TEXT, category TEXT, price REAL, currency TEXT,
            min_qty INTEGER, max_discount REAL, incompatible TEXT, operator TEXT, item_type TEXT, status TEXT,
            valid_until TEXT, billing TEXT, source TEXT, bundle_of TEXT, requires TEXT, tiers TEXT,
            term_months INTEGER, setup_fee REAL);
        CREATE TABLE IF NOT EXISTS quotes(
            id INTEGER PRIMARY KEY AUTOINCREMENT, operator TEXT, customer TEXT, status TEXT, total REAL,
            currency TEXT, created_by TEXT, details TEXT, leakage REAL DEFAULT 0,
            created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, password_hash TEXT, salt TEXT, role TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, username TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT DEFAULT CURRENT_TIMESTAMP, user TEXT, action TEXT, details TEXT);
        CREATE INDEX IF NOT EXISTS idx_prod ON products(operator, status);      -- tez search ke liye indexes
        CREATE INDEX IF NOT EXISTS idx_quote ON quotes(operator, status);
        """)

def _page(table, where, args, order, page, size, clean=dict):      # pagination ka ek hi function
    with conn() as c:
        total = c.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", args).fetchone()[0]
        rows = c.execute(f"SELECT * FROM {table} WHERE {where} {order} LIMIT ? OFFSET ?",
                         args + [size, (page - 1) * size]).fetchall()
    return {"items": [clean(r) for r in rows], "total": total, "page": page, "pages": max(1, -(-total // size))}

# ---- Providers (Operators + Vendors) ----
def save_operator(o):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO operators VALUES(?,?,?,?,?)",
                  (o["name"], o["code"], o.get("type", "Operator"), o["currency"], o["tax_percent"]))

def get_operator(name):
    with conn() as c:
        row = c.execute("SELECT * FROM operators WHERE name=?", (name,)).fetchone()
    return dict(row) if row else None

def all_operators():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM operators ORDER BY type DESC, name")]

# ---- Products ----
def _clean(row):
    d = dict(row)
    for k in LISTS:
        d[k] = json.loads(d[k] or "[]")
    return d

def save_product(p):
    d = {**DEFAULTS, **p}
    vals = [json.dumps(d[k]) if k in LISTS else d[k] for k in COLS]
    with conn() as c:
        c.execute(f"INSERT OR REPLACE INTO products({','.join(COLS)}) VALUES({','.join('?' * len(COLS))})", vals)

def get_product(oid):
    with conn() as c:
        row = c.execute("SELECT * FROM products WHERE offering_id=?", (oid,)).fetchone()
    return _clean(row) if row else None

def list_products(operator=None, q="", item_type="", status="", page=1, size=10):
    where, args = ["1=1"], []
    if operator:  where.append("operator=?");  args.append(operator)
    if item_type: where.append("item_type=?"); args.append(item_type)
    if status:    where.append("status=?");    args.append(status)
    if q:
        where.append("(name LIKE ? OR category LIKE ? OR description LIKE ?)")
        args += [f"%{q}%"] * 3
    return _page("products", " AND ".join(where), args, "ORDER BY item_type, category, name", page, size, _clean)

def set_product_status(oid, status):        # Active / Draft / Retired
    with conn() as c:
        return c.execute("UPDATE products SET status=? WHERE offering_id=?", (status, oid)).rowcount

def delete_product(oid):
    with conn() as c:
        c.execute("DELETE FROM products WHERE offering_id=?", (oid,))

# ---- Quotes ----
def save_quote(operator, customer, result, currency, user):
    with conn() as c:
        return c.execute("""INSERT INTO quotes(operator,customer,status,total,currency,created_by,details,leakage)
            VALUES(?,?,?,?,?,?,?,?)""", (operator, customer, result["status"], result["total"], currency,
            user, json.dumps(result), result["leakage"])).lastrowid

def get_quote(qid):
    with conn() as c:
        row = c.execute("SELECT * FROM quotes WHERE id=?", (qid,)).fetchone()
    return {**dict(row), "details": json.loads(row["details"])} if row else None

def set_status(qid, status):               # sirf NEEDS_APPROVAL wale quote badal sakte hain
    with conn() as c:
        return c.execute("UPDATE quotes SET status=? WHERE id=? AND status='NEEDS_APPROVAL'",
                         (status, qid)).rowcount

def list_quotes(operator=None, user=None, page=1, size=10):
    where, args = ["1=1"], []
    if operator: where.append("operator=?");   args.append(operator)
    if user:     where.append("created_by=?"); args.append(user)
    skip_details = lambda r: {k: r[k] for k in r.keys() if k != "details"}
    return _page("quotes", " AND ".join(where), args, "ORDER BY id DESC", page, size, skip_details)

def stats(operator=None):
    cond, args = ("operator=?", (operator,)) if operator else ("1=1", ())
    with conn() as c:
        q = lambda sql: c.execute(sql.format(cond), args).fetchone()[0]
        return {"products": q("SELECT COUNT(*) FROM products WHERE {}"),
                "quotes": q("SELECT COUNT(*) FROM quotes WHERE {}"),
                "approved": q("SELECT COUNT(*) FROM quotes WHERE {} AND status='APPROVED'"),
                "pending": q("SELECT COUNT(*) FROM quotes WHERE {} AND status='NEEDS_APPROVAL'"),
                "rejected": q("SELECT COUNT(*) FROM quotes WHERE {} AND status='REJECTED'"),
                "revenue": q("SELECT COALESCE(SUM(total),0) FROM quotes WHERE {} AND status='APPROVED'")}

def report():                              # Revenue leakage report: har provider ka hisaab
    with conn() as c:
        rows = c.execute("""SELECT operator, currency, COUNT(*) quotes,
            SUM(status='APPROVED') approved, SUM(status='NEEDS_APPROVAL') pending, SUM(status='REJECTED') rejected,
            ROUND(SUM(CASE WHEN status='REJECTED' THEN leakage ELSE 0 END), 2) prevented,
            ROUND(SUM(CASE WHEN status='NEEDS_APPROVAL' THEN leakage ELSE 0 END), 2) at_risk,
            ROUND(SUM(CASE WHEN status='APPROVED' THEN leakage ELSE 0 END), 2) approved_exceptions
            FROM quotes GROUP BY operator, currency ORDER BY operator""").fetchall()
    return [dict(r) for r in rows]

# ---- Users, login aur audit log ----
def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()

def create_user(username, password, role):
    salt = secrets.token_hex(8)
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO users VALUES(?,?,?,?)", (username, _hash(password, salt), salt, role))

def login(username, password):
    with conn() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row or not hmac.compare_digest(row["password_hash"], _hash(password, row["salt"])):
            return None
        token = secrets.token_hex(16)
        c.execute("INSERT INTO sessions VALUES(?,?,datetime('now'))", (token, username))
    return {"token": token, "username": username, "role": row["role"]}

def user_from_token(token):                # token 8 ghante tak chalta hai
    with conn() as c:
        row = c.execute("""SELECT u.username, u.role FROM sessions s JOIN users u ON u.username = s.username
            WHERE s.token=? AND s.created > datetime('now', '-8 hours')""", (token,)).fetchone()
    return dict(row) if row else None

def logout(token):
    with conn() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))

def log(user, action, details=""):
    with conn() as c:
        c.execute("INSERT INTO audit(user, action, details) VALUES(?,?,?)", (user, action, details))

def list_audit(page=1, size=10):
    return _page("audit", "1=1", [], "ORDER BY id DESC", page, size)
