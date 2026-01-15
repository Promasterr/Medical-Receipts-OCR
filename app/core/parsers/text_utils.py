"""
Text normalization and utility functions for parsers.
"""
import re
from datetime import datetime


def clean_field(s: str) -> str:
    """Remove leading/trailing asterisks and whitespace"""
    if s is None:
        return None
    s = re.sub(r'^\s*\*+\s*', '', s)
    s = re.sub(r'\s*\*+\s*$', '', s)
    return s.strip()


def extract_field_from_text(text: str, pattern: str, default=None):
    """Extract field using regex pattern"""
    m = re.search(pattern, text, re.MULTILINE)
    return clean_field(m.group(1)) if m else default


def extract_field_from_text_massara(text: str, pattern: str):
    """Extract field for massara documents"""
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else None


def extract_date_default(text: str, pattern: str, default=None):
    """Extract and normalize date"""
    m = re.search(pattern, text)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%d.%m.%Y")
            return dt.strftime("%Y-%m-%d")
        except:
            return m.group(1)
    return default


def normalize(text: str) -> str:
    """Remove invisible Unicode characters"""
    return re.sub(r'[\u200f\u200e\u202a\u202b\u202c\u202d\u202e]', '', text)


def normalize_jz_date(raw: str) -> str:
    """Normalize Janzour date formats"""
    if not raw:
        return None
    raw = raw.strip()
    formats = [
        "%m/%d/%y %I:%M%p",
        "%m/%d/%Y %I:%M%p",
        "%m/%d/%y",
        "%m/%d/%Y",
        "%d/%m/%y",
        "%d/%m/%Y"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%d/%m/%Y %H:%M") if "%I:%M" in fmt else dt.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return raw


def is_arabic(text: str) -> bool:
    """Check if text contains Arabic characters"""
    return bool(re.search(r'[\u0600-\u06FF]', text))


def header_missing_core_fields(text: str) -> bool:
    """Check if header is missing required fields"""
    required = ["رقم الدخول", "الرقم الطبي", "المريض"]
    return not any(field in text for field in required)


def remove_consecutive_duplicates(text: str) -> str:
    """
    Remove consecutive duplicate words or phrases from text.
    Used for cleaning OCR output.
    """
    if not text:
        return text
    
    # Split by newlines
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        words = line.split()
        if not words:
            cleaned_lines.append(line)
            continue
        
        # Remove consecutive duplicate words
        result = [words[0]]
        for word in words[1:]:
            if word != result[-1]:
                result.append(word)
        
        cleaned_lines.append(' '.join(result))
    
    return '\n'.join(cleaned_lines)
