# Approved quote ka PDF (fpdf2)
import os
from fpdf import FPDF

VALID_DAYS = os.getenv("QUOTE_VALID_DAYS", "30")
safe = lambda s: str(s).encode("latin-1", "replace").decode("latin-1")      # PDF ke core font ke liye

def quote_pdf(q):
    d, cur = q["details"], q["currency"]
    pdf = FPDF()
    pdf.add_page()
    pdf.set_fill_color(13, 148, 136)                                       # teal header band
    pdf.rect(0, 0, 210, 30, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_xy(12, 8)
    pdf.cell(100, 10, "QUOTATION")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 10, safe(q["operator"]), align="R")
    pdf.set_text_color(55, 65, 81)
    pdf.set_xy(12, 40)
    pdf.set_font("Helvetica", "", 11)
    for k, v in [("Quote No", f"#{q['id']}"), ("Date", q["created"][:10]), ("Customer", q["customer"]),
                 ("Prepared by", q["created_by"]), ("Valid for", f"{VALID_DAYS} days")]:
        pdf.set_font("Helvetica", "B", 11); pdf.cell(35, 7, k)
        pdf.set_font("Helvetica", "", 11); pdf.cell(0, 7, safe(v), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    widths = [78, 16, 20, 24, 28, 24]
    heads = ["Item", "Qty", "Disc %", "Term (m)", "Setup fee", f"Total ({cur})"]
    pdf.set_fill_color(229, 231, 235); pdf.set_font("Helvetica", "B", 10)
    for w, h in zip(widths, heads):
        pdf.cell(w, 9, h, border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    for l in d["lines"]:
        row = [l["name"], l["qty"], l["discount"], l["term_months"] or "-", f"{l['setup_fee']:,.0f}", f"{l['total']:,.2f}"]
        for w, v in zip(widths, row):
            pdf.cell(w, 8, safe(v)[:38], border=1)
        pdf.ln()
        if l["includes"]:
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(sum(widths), 6, safe("   Includes: " + ", ".join(l["includes"])), border=1, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)

    pdf.ln(4)
    for k, v, bold in [("Subtotal", d["subtotal"], False), ("Tax", d["tax"], False), ("TOTAL", d["total"], True)]:
        pdf.set_font("Helvetica", "B" if bold else "", 12)
        pdf.cell(sum(widths) - 40, 8, k, align="R")
        pdf.cell(40, 8, f"{v:,.2f} {cur}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(107, 114, 128)
    pdf.multi_cell(0, 5, "This quotation is system generated. Prices are indicative and subject to contract terms.")
    return bytes(pdf.output())
