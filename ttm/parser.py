import re
from datetime import datetime
from io import BytesIO

import pdfplumber


MONEY = r"([0-9]+(?:\.[0-9]+)?)"


def _amount(text, label):
    matches = re.findall(rf"{label}\s+{MONEY}", text, re.IGNORECASE)
    return float(matches[-1]) if matches else 0.0


def normalize_product(name):
    raw = " ".join(name.upper().split())
    channel = "delivery" if raw.endswith(" APP") else "local"
    clean = re.sub(r"\s+APP$", "", raw).strip()
    return clean.title(), channel


def parse_smartcorp_pdf(file_bytes, filename):
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        pages = [page.extract_text(x_tolerance=2, y_tolerance=3) or "" for page in pdf.pages]
    text = "\n".join(pages)
    date_match = re.search(r"FECHA:\s*(\d{4}-\d{2}-\d{2})", text)
    if not date_match:
        raise ValueError("No se encontró la fecha del cuadre SMARTCORP.")
    sale_date = date_match.group(1)
    total_match = re.search(r"CUADRE DE CAJA.*?\nSaldo inicial en caja.*?\nVentas\s+" + MONEY, text, re.S | re.I)
    total = float(total_match.group(1)) if total_match else 0.0
    pedidos = _amount(text, "Pedidos Ya")
    uber = _amount(text, "Uber eats")
    rappi = _amount(text, "Rappi")
    delivery = pedidos + uber + rappi + _amount(text, "Togo")
    order_section = re.search(r"PEDIDOS A DOMICILIO(.*?)ANTICIPOS", text, re.S | re.I)
    delivery_tickets = len(re.findall(r"\bF\.V\s+\d+", order_section.group(1))) if order_section else 0
    local_section = text.split("PEDIDOS A DOMICILIO", 1)[0]
    local_tickets = len(re.findall(r"\bF\.V\s+\d+", local_section))
    products = []
    prod_match = re.search(r"PRODUCTOS VENDIDOS(.*?)(?:Reporte generado automáticamente|$)", text, re.S | re.I)
    if prod_match:
        for name, qty in re.findall(r"^(.+?)\s+(\d+(?:\.\d+)?)\s*$", prod_match.group(1), re.M):
            if name.strip().lower() in {"about:blank", "producto cantidad"}:
                continue
            clean, channel = normalize_product(name)
            products.append({"product_raw": name.strip(), "product_name": clean, "channel": channel, "quantity": float(qty)})
    return {
        "sale_date": sale_date, "total_sales": total, "local_sales": round(total-delivery, 2),
        "delivery_sales": round(delivery, 2), "tickets": local_tickets+delivery_tickets,
        "local_tickets": local_tickets, "delivery_tickets": delivery_tickets,
        "cash": _amount(text, "Efectivo"), "card": _amount(text, "Tarjeta"),
        "transfer": _amount(text, "Transferencia"), "pedidos_ya": pedidos,
        "uber_eats": uber, "rappi": rappi, "other_delivery": _amount(text, "Togo"),
        "source_file": filename, "products": products,
    }
