import hashlib
import re
from datetime import datetime
from io import BytesIO

import pdfplumber


SUPPLIER_CATEGORIES = {
    "DELIVERY HERO": "Comisiones plataformas",
    "RAPPIEC": "Comisiones plataformas",
    "TECHNOLOGY SUPPORT": "Comisiones plataformas",
    "AC BEBIDAS": "Bebidas",
    "PRONACA": "Carnes",
    "NOVA MEATS": "Carnes",
    "DATAFAST": "Datafast",
    "CORPORACION FAVORITA": "Insumos",
    "GERARDO ORTIZ": "Insumos",
    "KYWI": "Suministros",
}


def _last_amount(text, label):
    matches = re.findall(rf"{label}\s+([0-9]+(?:[.,][0-9]{{1,2}})?)", text, re.I)
    return float(matches[-1].replace(",", ".")) if matches else 0.0


def parse_invoice_pdf(file_bytes, filename="factura.pdf"):
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        text = "\n".join(page.extract_text(x_tolerance=2, y_tolerance=3) or "" for page in pdf.pages)
    if not text.strip():
        return {
            "document_hash": hashlib.sha256(file_bytes).hexdigest(),
            "original_filename": filename,
            "invoice_date": None,
            "supplier_name": "Documento sin texto",
            "supplier_tax_id": "",
            "invoice_number": "",
            "subtotal": 0.0,
            "tax": 0.0,
            "total": 0.0,
            "expense_category": "Por clasificar",
            "description": "Requiere revisión manual",
            "review_status": "Pendiente",
        }

    ruc = re.search(r"R\.U\.C\.?:\s*(\d{13})", text, re.I)
    number = re.search(r"FACTURA\s*\nNo\.\s*([0-9-]+)", text, re.I)
    date = re.search(r"\bFecha\s+(\d{2}/\d{2}/\d{4})", text, re.I)
    if not date:
        date = re.search(r"\b(\d{2}/\d{2}/\d{4})\s+\d{2}:\d{2}", text)
    invoice_date = None
    if date:
        invoice_date = datetime.strptime(date.group(1), "%d/%m/%Y").date().isoformat()

    supplier = "Proveedor por revisar"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for idx, line in enumerate(lines):
        if line == "NÚMERO DE AUTORIZACIÓN" and idx + 2 < len(lines):
            candidate = lines[idx + 2].split(" FECHA Y HORA DE")[0].strip()
            if candidate and not candidate.isdigit():
                supplier = candidate
            break
    subtotal = _last_amount(text, "SUBTOTAL SIN IMPUESTOS")
    tax = _last_amount(text, "IVA 15%") or _last_amount(text, "IVA 12%")
    total = _last_amount(text, "VALOR TOTAL")
    upper_supplier = supplier.upper()
    category = next((value for key, value in SUPPLIER_CATEGORIES.items() if key in upper_supplier), "Por clasificar")
    status = "Revisado" if invoice_date and number and total > 0 and category != "Por clasificar" else "Pendiente"
    return {
        "document_hash": hashlib.sha256(file_bytes).hexdigest(),
        "original_filename": filename,
        "invoice_date": invoice_date,
        "supplier_name": supplier,
        "supplier_tax_id": ruc.group(1) if ruc else "",
        "invoice_number": number.group(1) if number else "",
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "expense_category": category,
        "description": "Factura electrónica",
        "review_status": status,
    }
