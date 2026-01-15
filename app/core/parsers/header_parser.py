"""
Header parsing for different document formats.
Extracts patient and invoice information from document headers.
"""
import re
from typing import Dict
from collections import OrderedDict
from app.core.parsers.text_utils import (
    clean_field, extract_field_from_text, extract_field_from_text_massara,
    extract_date_default, normalize_jz_date
)


def parse_header(text: str, mode: str = "") -> dict:
    """
    Parses patient header information and returns structured data.
    Leading/trailing asterisks are removed from values.
    
    Args:
        text: Document text to parse
        mode: Parsing mode - "", "invoice", or "janzour"
        
    Returns:
        Dictionary with header (and optionally footer) data
    """
    if mode == "":
        # Massara/default parser
        header = {
            "invoice_number": extract_field_from_text_massara(text, r"إيصال\s*رقم[:：]?\s*(\d+)"),
            "file_number": extract_field_from_text_massara(text, r"رقم\s*الملف[:：]?\s*([0-9]+)"),
            "patient_name": extract_field_from_text_massara(text, r"اسم\s*المريض[:：]?\s*([^\n\r]+)"),
            "admission_date": extract_date_default(text, r"ت\s*الدخول[:：]?\s*(\d{2}\.\d{2}\.\d{4})"),
            "discharge_date": extract_date_default(text, r"ت\s*الخروج[:：]?\s*(\d{2}\.\d{2}\.\d{4})"),
            "company_name": extract_field_from_text_massara(text, r"الشركة[:：]?\s*([^\n\r]+)")
        }
        
        # Footer extraction
        footer = {}
        footer_map = {
            "الاجمالي": "total_price",
            "المدفوع": "price_paid",
            "المتبقي": "price_due"
        }
        
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        
        for line in lines:
            for ar, key in footer_map.items():
                if ar in line:
                    m = re.search(r"([-+\d\.,]+)", line)
                    if m:
                        num = m.group(1).replace(",", "").strip()
                        try:
                            footer[key] = float(num)
                        except:
                            footer[key] = num
        
        return {
            "header": header,
            "footer": footer if footer else None
        }
    
    elif mode == "invoice":
        # Invoice mode parser
        raw_lines = re.split(r'[\r\n]+', text)
        lines = [ln.strip() for ln in raw_lines]
        
        keyword_map = OrderedDict([
            ("invoice_number", ["إيصال رقم", "رقم الإيصال", "إيصال", "إيصال تفصيلي رقم"]),
            ("file_number", ["الرقم الطبي", "رقم الملف"]),
            ("patient_name", ["اسم المريض", "إسم المريض", "المريض"]),
            ("admission_number", ["رقم الدخول", "رقم المدخول"]),
            ("doctor_name", ["اسم الطبيب", "إسم الطبيب", "الطبيب"]),
            ("doctor_speciality", ["تخصص الطبيب", "التخصص"]),
            ("clinic_category", ["العيادة", "قسم"]),
            ("visit_type", ["و القيمة تتمثل", "القيمة تمثل"]),
            ("date", ["التاريخ", "تاريخ"]),
            ("time", ["الساعة", "الوقت"]),
            ("company_name", ["الجهة", "شركة", "المؤسسة"]),
            ("agreement", ["الاتفاقية", "الإتفاقيه", "الإتفاقية"]),
            ("sequence", ["المسلسل", "السيريال", "التسلسل"]),
            ("employee_number", ["الرقم الوظيفي", "الرقم الوظيفى"]),
        ])
        
        all_label_tokens = [tok for labels in keyword_map.values() for tok in labels]
        
        def line_is_label_candidate(ln):
            if not ln:
                return False
            lnl = ln.lower()
            for tok in all_label_tokens:
                if tok.lower() in lnl:
                    return True
            return False
        
        def extract_after_label(line, label):
            pattern = rf"{re.escape(label)}\s*[:\-]?\s*(.+)"
            m = re.search(pattern, line, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()
            return None
        
        def extract_before_label(line, label):
            pattern = rf"([^\s:،\-–]+)\s+{re.escape(label)}"
            m = re.search(pattern, line, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()
            return None
        
        def clean_value(val):
            if not val:
                return None
            val = val.strip(" \t:.-،")
            val = re.sub(r'\s*\([^)]+\)\s*$', "", val).strip()
            if val in ["", ":", "-", "–"]:
                return None
            return val
        
        result = {k: None for k in keyword_map.keys()}
        
        for idx, ln in enumerate(lines):
            if not ln:
                continue
            
            for key, arabic_labels in keyword_map.items():
                if result[key] is not None:
                    continue
                
                for lab in sorted(arabic_labels, key=len, reverse=True):
                    if lab.lower() in ln.lower():
                        val = extract_after_label(ln, lab)
                        
                        if not val:
                            val_before = extract_before_label(ln, lab)
                            if val_before:
                                val = val_before
                        
                        if not val and key == "invoice_number":
                            if idx > 0:
                                prev_line = lines[idx - 1].strip()
                                if prev_line and not line_is_label_candidate(prev_line):
                                    val = prev_line
                        
                        if not val:
                            look = None
                            for j in range(idx + 1, min(idx + 4, len(lines))):
                                cand = lines[j].strip()
                                if not cand:
                                    continue
                                if line_is_label_candidate(cand):
                                    break
                                look = cand
                                break
                            if look:
                                val = look
                        
                        val = clean_value(val)
                        if val:
                            result[key] = val
                        break
                
                if result[key] is not None:
                    break
        
        if result["date"]:
            date_only = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", result["date"])
            if date_only:
                result["date"] = date_only.group(1)
        
        if not result["time"]:
            m = re.search(r"(\d{1,2}[:\.][\d]{2})", text)
            if m:
                result["time"] = m.group(1).replace(".", ":")
        
        return result
    
    elif mode == "janzour":
        # Janzour mode parser
        DATE = r"([0-9]{1,2}/[0-9]{1,2}/(?:[0-9]{2}|[0-9]{4}))"
        TIME = r"([0-9]{1,2}:[0-9]{2}\s*(?:AM|PM|am|pm)?)"
        
        DATE_TIME_JZ = r"([0-9]{1,2}/[0-9]{1,2}/(?:[0-9]{2}|[0-9]{4})(?:\s+[0-9]{1,2}:[0-9]{2}\s*(?:AM|PM|am|pm)?)?)"
        report_date_raw = extract_field_from_text(text, rf"التاريخ\s*[:：]?\s*{DATE_TIME_JZ}", "")
        report_date = normalize_jz_date(report_date_raw) if report_date_raw else None
        
        stay_pattern = rf"الإقامة\s*[:\s]*(?:.*?)(?:من\s*{DATE}\s*{TIME}\s*(?:إلى|الى)\s*{DATE}\s*{TIME})?"
        stay = re.search(stay_pattern, text)
        
        if stay and stay.groups() and len(stay.groups()) >= 4:
            admission_date = normalize_jz_date(clean_field(stay.group(1)))
            admission_time = clean_field(stay.group(2))
            discharge_date = normalize_jz_date(clean_field(stay.group(3)))
            discharge_time = clean_field(stay.group(4))
        else:
            admission_date = admission_time = discharge_date = discharge_time = None
        
        header = {
            "report_date": report_date,
            "patient_name": extract_field_from_text(text, r"المريض\s*[:\s]*(.+)"),
            "entry_number": extract_field_from_text(text, r"رقم الدخول\s*[:\s]*(.+)"),
            "medical_number": extract_field_from_text(text, r"الرقم الطبي\s*[:\s]*(.+)"),
            "company_name": extract_field_from_text(text, r"الجهة\s*[:\s]*(.+)"),
            "agreement": extract_field_from_text(text, r"الإتفاقية\s*[:\s]*(.+)"),
            "room": extract_field_from_text(text, r"الغرفة\s*[:\s]*(.*)"),
            "room_type": extract_field_from_text(text, r"نوع الغرفة\s*[:\s]*(.+)"),
            "doctor_name": extract_field_from_text(text, r"(?:اسم|إسم) الطبيب\s*[:\s]*(.+)"),
            "specialty": extract_field_from_text(text, r"التخصص\s*[:\s]*(.+)"),
            "admission_date": admission_date,
            "admission_time": admission_time,
            "discharge_date": discharge_date,
            "discharge_time": discharge_time,
        }
        
        return {"header": header}
    
    return {}


def parse_idcard_text(text: str) -> Dict:
    """
    Parse ID card style text into JSON.
    Supports both 'اسم الموظف' and 'اسم الموصول' as patient_name.
    
    Args:
        text: ID card text
        
    Returns:
        Dictionary with ID card fields
    """
    result = {}
    
    # Extract various fields
    patterns = {
        "name": r"(?:اسم الموظف|اسم الموصول|الاسم)[:\s]*([^\n]+)",
        "id_number": r"الرقم الوطني[:\s]*(\d+)",
        "validity": r"صلاحية[:\s]*([^\n]+)",
        "company": r"المؤسسة[:\s]*([^\n]+)",
    }
    
    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if m:
            result[key] = m.group(1).strip()
    
    return result
