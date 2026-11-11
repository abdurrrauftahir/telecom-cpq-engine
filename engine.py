# Business Rules Engine (v5): saare rules database se aate hain, kuch bhi hardcoded nahi
from datetime import date
from database import get_product

def validate_quote(items, tax_percent=0, extra_discount=0, operator=None):
    errors, soft, lines, seen, leak = [], [], [], set(), 0
    prods = {i["offering_id"]: get_product(i["offering_id"]) for i in items}
    have = set(prods)                                   # quote mein jo ids hain
    for p in prods.values():
        if p:
            have |= set(p["bundle_of"])                 # bundle ke andar wali cheezein bhi "maujood" hain

    for it in items:
        oid, p = it["offering_id"], prods[it["offering_id"]]
        if not p:
            errors.append(f"❌ {oid}: product catalog mein nahi hai")
            continue
        if p["status"] != "Active":
            errors.append(f"❌ {p['name']}: product {p['status']} hai, bech nahi sakte")
        if p["valid_until"] and p["valid_until"] < date.today().isoformat():
            errors.append(f"❌ {p['name']}: offer {p['valid_until']} ko expire ho chuka hai")
        if operator and p["operator"] != operator:
            errors.append(f"❌ {p['name']}: yeh {operator} ka product nahi hai")
        if it["qty"] < p["min_qty"]:
            errors.append(f"❌ {p['name']}: kam az kam {p['min_qty']} quantity chahiye")

        # Discount: limit tak OK | limit + extra tak manager approval | us se zyada reject
        limit = p["max_discount"]
        if it["discount"] > limit:
            msg = f"{p['name']}: discount {limit}% se zyada hai"
            if it["discount"] <= limit + extra_discount:
                soft.append(f"🟣 {msg} (manager approval chahiye)")
            else:
                errors.append(f"❌ {msg}, {limit + extra_discount}% se zyada kabhi allowed nahi")

        for need in p["requires"]:                      # dependency rule
            if need not in have:
                errors.append(f"❌ {p['name']} ke sath {need} bhi lena lazmi hai")
        for part in p["bundle_of"]:                     # bundle ke sath uska hissa alag nahi
            if part in prods:
                errors.append(f"❌ {part} pehle se {oid} bundle mein shamil hai")
        for bad in p["incompatible"]:
            pair = frozenset([oid, bad])                # A-B aur B-A ek hi pair hai
            if bad in prods and pair not in seen:
                seen.add(pair)
                errors.append(f"❌ {oid} aur {bad} ek saath nahi ho sakte")

        # Qeemat: volume tier (khud lagta hai), contract term aur one-time setup fee
        auto = max([t["discount"] for t in p["tiers"] if it["qty"] >= t["min_qty"]], default=0)
        disc = max(it["discount"], auto)
        gross = p["price"] * it["qty"]
        months = p["term_months"]
        if p["billing"] == "Monthly":                   # contract ke kitne billing periods
            periods = months or 1
        elif p["billing"] == "Yearly":
            periods = months / 12 if months else 1
        else:
            periods = 1
        setup = p["setup_fee"] * it["qty"]
        total = gross * (1 - disc / 100) * periods + setup
        if it["discount"] > limit:                      # jo discount limit se bahar tha (leakage)
            leak += gross * (it["discount"] - limit) / 100 * periods
        lines.append({"name": p["name"], "qty": it["qty"], "discount": disc, "tier_discount": auto,
                      "term_months": months, "setup_fee": round(setup, 2), "total": round(total, 2),
                      "includes": p["bundle_of"]})

    subtotal = sum(l["total"] for l in lines)
    tax = subtotal * tax_percent / 100
    status = "REJECTED" if errors else ("NEEDS_APPROVAL" if soft else "APPROVED")
    return {"status": status, "reasons": errors + soft, "lines": lines, "subtotal": round(subtotal, 2),
            "tax": round(tax, 2), "total": round(subtotal + tax, 2), "leakage": round(leak, 2)}
