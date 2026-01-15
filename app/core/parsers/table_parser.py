"""
HTML table parsing for different document formats.
Extracts tables from OCR HTML output and converts to structured JSON.
"""
from bs4 import BeautifulSoup
from typing import Dict, List, Any
import re


def is_section_row(cells: List[str]) -> bool:
    """
    Detect rows that represent category names.
    - Only one cell with content
    - No numbers in it
    - Contains Arabic characters
    """
    non_empty = [c for c in cells if c.strip()]
    if len(non_empty) == 1:
        txt = non_empty[0]
        txt_plain = re.sub(r"<.*?>", "", txt).strip()
        if re.search(r"[ء-ي]", txt_plain) and not re.search(r"\d", txt_plain):
            return True
    return False


def find_section_for_table(html: str, table_html: str) -> str:
    """Find section name above a table in HTML"""
    lines = html.splitlines()
    target = table_html.strip()
    
    table_index = -1
    for i, line in enumerate(lines):
        if target in line:
            table_index = i
            break
    
    if table_index == -1:
        return None
    
    for j in range(table_index - 1, -1, -1):
        line = BeautifulSoup(lines[j], "html.parser").get_text(strip=True)
        if not line:
            continue
        if "المبلغ الإجمالي" in line:
            continue
        return line
    
    return None


def extract_plain_from_header_table(table_html: str) -> str:
    """Extract plain text from header table"""
    soup = BeautifulSoup(table_html, "html.parser")
    table = soup.find("table")
    if not table:
        return ""
    
    text_parts = []
    for row in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        text_parts.append(" ".join(cells))
    
    return "\n".join(text_parts)


def html_table_to_json(html: str, mode: str = "") -> Dict[str, Any]:
    """
    Convert HTML table to JSON based on document mode.
    
    Args:
        html: HTML string containing table
        mode: Document mode - "", "invoice", or "janzour"
        
    Returns:
        Dictionary with table data
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    
    if not table:
        return {"entries": []}
    
    # Detect section name
    section = None
    lines = html.splitlines()
    for line in lines:
        if "<table" in line:
            break
        if "المبلغ الإجمالي" in line:
            continue
        stripped = BeautifulSoup(line, "html.parser").get_text(strip=True)
        if stripped:
            section = stripped
    section = section or ""
    
    # Get headers and rows
    header_cells = table.find("thead").find("tr").find_all("th") if table.find("thead") else []
    headers = [h.get_text(strip=True) for h in header_cells]
    rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")
    
    # Invoice mode
    if mode == "invoice":
        header_map = {
            "القيمة": "price",
            "البيان": "service_name",
            "الرمز": "code",
            "ت": "qty",
            "أجل": "due_amount",
            "تقدي": "paid_amount"
        }
        
        entries = []
        for row in rows:
            tds = row.find_all("td")
            if not tds:
                continue
            
            txt = tds[0].get_text(strip=True)
            if any(td.has_attr("colspan") for td in tds) or "الإجمالي" in txt or "المجموع" in txt:
                continue
            
            if len(tds) != len(headers):
                continue
            
            row_obj = {}
            for i, td in enumerate(tds):
                raw = td.get_text(strip=True)
                col_name = header_map.get(headers[i], headers[i])
                
                if col_name.lower() in ("price", "القيمة"):
                    try:
                        num = float(raw.replace(",", ""))
                        raw = "{:,.3f}".format(num)
                    except:
                        pass
                
                row_obj[col_name] = raw
            
            entries.append(row_obj)
        
        return {
            "category": section or None,
            "entries": entries
        }
    
    # Janzour mode - 4 column footer
    if len(headers) == 4 and mode == "janzour":
        footer = {}
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            
            if len(cells) != 4:
                continue
            
            v1, v2, v3, label = cells
            
            if label.strip() == "الصافي":
                try:
                    total = float(v1.replace(" ", "").replace(",", ""))
                except:
                    total = 0.0
                
                try:
                    paid = float(v2.replace(" ", "").replace(",", ""))
                except:
                    paid = 0.0
                
                try:
                    amount_due = float(v3.replace(" ", "").replace(",", ""))
                except:
                    amount_due = 0.0
                
                footer = {
                    "total": total,
                    "paid": paid,
                    "amount_due": amount_due
                }
                
                return {"footer": footer}
        
        return {"footer": {}}
    
    # Janzour mode - service tables
    if mode == "janzour":
        num_cols = len(headers)
        
        KEYS_8 = [
            "company_price", "patient_price", "net_price", "time",
            "date", "qty", "service_name", "code"
        ]
        
        KEYS_10 = [
            "company_price", "patient_price", "net_price", "time",
            "date", "unit_price", "qty", "unit", "service_name", "code"
        ]
        
        KEYS_11 = [
            "company_price", "patient_price", "net_price", "time_to",
            "date_to", "time_from", "date_from", "operation_type",
            "qty", "service_name", "code"
        ]
        
        if num_cols == 8:
            mapped_headers = KEYS_8
        elif num_cols == 10:
            mapped_headers = KEYS_10
        elif num_cols == 11:
            mapped_headers = KEYS_11
        else:
            mapped_headers = headers
        
        entries = []
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            
            if not cells or all(c == "" for c in cells):
                continue
            if "المبلغ الإجمالي" in "".join(cells):
                continue
            
            if len(cells) < len(mapped_headers):
                cells += [""] * (len(mapped_headers) - len(cells))
            elif len(cells) > len(mapped_headers):
                cells = cells[:len(mapped_headers)]
            
            entry = {}
            for key, val in zip(mapped_headers, cells):
                if key in ("company_price", "patient_price", "net_price", "unit_price"):
                    clean = val.replace(",", "").replace(" ", "").replace("/", "")
                    try:
                        entry[key] = float(clean) if clean else 0.0
                    except:
                        entry[key] = 0.0
                    continue
                
                if key == "qty":
                    try:
                        entry[key] = int(val) if val else 0
                    except:
                        entry[key] = 0
                    continue
                
                entry[key] = val
            
            entries.append(entry)
        
        entries = [e for e in entries if e.get("code", "").strip() != ""]
        return {
            "section": section,
            "columns": mapped_headers,
            "entries": entries
        }
    
    # Default mode - treat as massara
    return {"entries": []}
