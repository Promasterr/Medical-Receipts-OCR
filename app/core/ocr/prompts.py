"""
OCR prompt templates for different document types.
"""


def get_prompt_by_keyword(keyword: str) -> str:
    """
    Return the correct prompt for a job keyword.
    Uses substring checks for flexible matching.
    
    Args:
        keyword: Document type or keyword identifier
        
    Returns:
        Appropriate prompt string for the document type
    """
    keyword = keyword.lower()
    
    if "أدوية ومستلزمات" in keyword:
        return (
            "Extract all text from the document exactly as it appears. "
            "Preserve line breaks and formatting. Convert any tables to plain text format, "
            "preserving headers and structure. Ignore logos, stamps, watermarks, and any "
            "decorative elements that are not part of the main text. Read the document "
            "naturally as if a human is reading it. Do not omit any visible text. "
            "Preserve formatting, spacing, and symbols. Ignore the rows which have only single column."
        )
    
    elif "janzour" in keyword:
        return (
            "Extract all text from the document. Transcribe Arabic labels exactly and provide values accurately.\n\n"
            "STRICT FORMATTING RULES:\n"
            "1. Ignore watermarks, QR codes, and logos.\n"
            "2. DATE CONVERSION: The document uses DD/MM/YY and YYYY-MM-DD formats. "
            "Convert ALL dates to the DD/MM/YYYY standard. Crucially, ensure the year is always 4 digits (e.g., 2025, not 25).\n"
            "3. TABLE EXTRACTION: Extract data from each table (Cash, Stay, Supervision, Analysis) row by row.\n"
            "4. COLUMN MAPPING: When transcribing data rows, map the Arabic column names "
            "(الجهة, المريض, صافي السعر, إلخ) to their corresponding values precisely, "
            "even if the value is zero or an empty cell.\n"
            "5. GENERAL DETAILS: For the header section (التاريخ, المريض, الجهة, الإقامة), "
            "extract all text pairs verbatim.\n\n"
            "Note: For fields with dates like 'الإقامة: من 24/04/2025 18:48 إلى 26/04/2025 12:32', "
            "extract them exactly as they appear without reordering the dates within the range.\n"
            "*FINAL OUTPUT INSTRUCTION:*\n"
            "Present the extracted data (General Details and all table data) structured "
            "*ENTIRELY in JSON format*. Use separate JSON objects or arrays for each section "
            "(General Details, Cash, Stay, etc.). Only return HTML table within <table></table>."
        )
    
    elif keyword == "massara":
        return (
            "Extract all text from the document exactly as it appears. "
            "Preserve line breaks and formatting. Convert any tables to plain text format, "
            "preserving headers and structure. Return all mathematical expressions in LaTeX format. "
            "For any images, if a caption exists, write it as plain text; if no caption exists, "
            "write a brief description of the image. Ignore logos, stamps, watermarks, and any "
            "decorative elements that are not part of the main text. Include page numbers if visible, "
            "formatted as plain text. Read the document naturally as if a human is reading it. "
            "Do not omit any visible text. Preserve formatting, spacing, and symbols. "
            "Only return HTML table within <table></table>."
        )
    
    elif keyword == "idcard":
        return (
            "Extract all text from the document, preserving the Arabic labels.\n"
            "STRICT FORMATTING RULES:\n"
            "1. Ignore watermarks, QR codes, and logos.\n"
            "2. DATE CONVERSION: The document uses YYYY-MM-DD format (e.g., 2026-02-16). "
            "You must convert ALL dates to DD-MM-YYYY format.\n"
            "3. PRESERVE YEARS: When converting, ensure the year remains 4 digits (e.g., \"2026\", NOT \"16\").\n"
            "4. VALIDITY LINE SPECIFIC: The validity line contains two dates (Start and End). "
            "Treat them as separate values. Do not merge them.\n"
            "   - Input Example: \"2026-02-16 - 2025-02-17\"\n"
            "   - Required Output: \"16-02-2026 - 17-02-2025\""
        )
    
    elif "إيصال رقم" in keyword:
        return (
            "Extract all text from the document exactly as it appears. "
            "Preserve line breaks and formatting. preserve headers and structure. "
            "Ignore logos, stamps, watermarks, and any decorative elements that are not part of the main text. "
            "Read the document naturally as if a human is reading it. Do not omit any visible text. "
            "Preserve formatting, spacing, and symbols. Only return HTML table within <table></table>."
        )
    
    else:
        # Default prompt
        return "Extract the arabic text."


# Prompt constants
DEFAULT_PROMPT = "Extract the arabic text."

MEDICINE_PROMPT = get_prompt_by_keyword("أدوية ومستلزمات")
JANZOUR_PROMPT = get_prompt_by_keyword("janzour")
MASSARA_PROMPT = get_prompt_by_keyword("massara")
IDCARD_PROMPT = get_prompt_by_keyword("idcard")
RECEIPT_PROMPT = get_prompt_by_keyword("إيصال رقم")
