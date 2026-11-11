# Telecom CPQ Engine (V5): AI + TMF620 / TMF648

![tests](https://github.com/abdurrrauftahir/telecom-cpq-engine/actions/workflows/tests.yml/badge.svg)

AI-powered **Configure-Price-Quote** system for telecom operators (Jazz, Zong, Ufone, STC, Mobily, Ooredoo) and vendors (Ericsson, Qvantel).
Sales agents search products in plain language, build a quote, and the rules engine validates it instantly.

## Features
- AI semantic search (ChromaDB + HuggingFace `all-MiniLM-L6-v2`)
- 100% dynamic rules from the database: min quantity, max discount, incompatible products, **dependencies** and **real bundles**
- **Volume discount tiers**, **contract term** and **setup fees**
- **Login and roles**: Sales, Manager, Admin (token based, passwords hashed)
- Manager approval workflow, **audit log**, **quote PDF**
- **Revenue leakage report**: discount leakage prevented, exceptions approved, amount at risk
- Catalog Manager (Product / Service / Offer, lifecycle, CSV import/export), **pagination** and database **indexes**
- TMF620 (catalog) and TMF648 (quote) style endpoints, Swagger docs at `/docs`
- **GitHub Actions** runs the tests on every push

## Run locally (Windows)
```
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
python seed.py
python -m uvicorn main:app --reload
```
Open http://127.0.0.1:8000

Demo accounts (change them in `users.json` before real use): `admin/admin123`, `manager/manager123`, `sales/sales123`

| Role | Can do |
|---|---|
| Sales | search, create quotes, see own quotes, download PDF |
| Manager | + approve/reject quotes, leakage report |
| Admin | + edit catalog, add providers, audit log |

## Tests
```
python -m pytest -q
```

## Architecture
`catalog.json, operators.json, users.json -> seed.py -> SQLite (data, rules) + ChromaDB (AI search) -> FastAPI -> Dashboard`

Prices in the sample catalog are illustrative. Names and categories of Jazz, Zong, Ericsson and Qvantel come from public websites.
