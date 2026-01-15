"""
PDF processing pipeline for document OCR.
Integrated from the original monolithic main.py implementation.
"""
import os
import json
import tempfile
import io
import base64
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import fitz  # PyMuPDF
import cv2
import numpy as np
from PIL import Image, ImageDraw
from openai import OpenAI
from dotenv import load_dotenv
from app.models.ml_models import model_manager
from app.config import settings
from app.core.layout.detector import process_layout


load_dotenv()


DEFAULT_MASSARA_PROMPT = """You are an information extraction engine.

Your task is to extract structured JSON from hospital billing and medical documents.

This is a medical and insurance document.
Accuracy and data integrity are critical.

ABSOLUTE CORE PRINCIPLES (NO EXCEPTIONS)
1. NO CALCULATIONS (EXCEPT WHERE EXPLICITLY ALLOWED)
DO NOT calculate, infer, derive, or estimate totals.
Copy totals ONLY if explicitly written.
If a value is missing → use null.
Never fabricate values.

2. ZERO VALUES ARE VALID
0, 0.00, "0.00" are valid ONLY if explicitly present.
Never replace missing values with zero.

3. PRESERVE ORIGINAL VALUES
Keep prices exactly as written (string format).
Do not normalize, round, or reformat numbers.
Do not add derived fields.

4. LANGUAGE PRESERVATION
DO NOT translate unless explicitly requested.
Arabic stays Arabic.
English fields are filled only if English text exists.

MULTI-INVOICE & DOCUMENT CONTROL (CRITICAL)
DOCUMENT GROUPING RULE

The unique document key is invoice_number.
Before creating a new document:
CHECK all previously created documents.
If the invoice_number already exists:
REUSE that document
APPEND sections to it
DO NOT create a new header
Create a new document ONLY if the invoice number has NEVER appeared before.
FILE NUMBER IMMUTABILITY
file_number (medical number) is extracted ONCE per invoice.
If multiple file numbers appear:
Use the first occurrence only
Ignore all others
Never assign multiple file numbers to one invoice.

DOCUMENT LOCKING RULE (CRITICAL):
• Once a document for an invoice_number is created:
  - The header becomes READ-ONLY.
  - DO NOT re-extract, overwrite, or modify header fields.
  - DO NOT change invoice_number, file_number, or patient_name.
• All subsequent pages with the same invoice_number:
  - MAY ONLY append sections.
  - MAY NOT create a new document.

CONTINUATION RULE (MANDATORY):

• A document continues across ALL pages until a NEW invoice_number is found.
• NEVER assume a document is complete before end of input.
• Do NOT stop extraction early even if totals appear.

SECTION ACCUMULATION RULE:

• Sections with the SAME section_name MAY appear multiple times.
• When a section_name repeats:
  - APPEND all rows to the existing section.
  - DO NOT overwrite or skip.
• A section ends ONLY when a new section header is detected.

TABLE ROBUSTNESS RULE:

• Table column structure may vary.
• Always extract rows if:
  - service description
  - code
  - date or time
  - any price field
  are present.
Column names can be wrong. look at the table content to determine the correct column names.
• Do NOT skip tables due to unfamiliar columns.
• Every <tr> containing a service description and code MUST produce an item.


PAGE & TABLE HANDLING
PAGE RULE

Each physical page may contain headers, tables, or continuations.
Page breaks DO NOT automatically create new sections or documents.

TABLE COMPLETENESS RULE
EVERY table must be extracted.
Never skip a table.
If a table header is visible → a section MUST be created.
Page breaks do not end a table unless a new table header appears.

SECTION IDENTITY RULE
A section is defined a row with only one data cell(<td>).
every row with only one data cell(<td>) is a section name.
The same section_name may appear multiple times.

Each table can have multiple sections.

Do not merge or split tables unless rows clearly continue.

SECTION SUBTOTAL RULE
Copy section subtotals ONLY if explicitly written.
If the table’s last row has no code, treat it as a subtotal row.
If the last row has a code, the table has NO subtotal → set section_subtotal to null.

HEADER & IDENTITY RULES
Extract header fields only if present.
invoice_number and file_number cannot be empty.
Do not infer doctor names, specialties, room types, or identity fields.
patient_identity data appears only under the “ID Card” section.
id_card_number must match format: ACA-xxxx-xxxxx-xxx.
If multiple ID numbers exist → use the one that matches this format.

FOOTER TOTAL RULES (STRICT)
FOOTER SAFETY

DO NOT write 0 or 0.00 unless explicitly printed in the document.

If no grand total exists:

net_total_amount MUST be null

amount_due MUST be null

TOTAL PRICE RULE (ONLY ALLOWED CALCULATION)

If NO single grand total exists

BUT multiple section totals are explicitly labeled (e.g. المبلغ الإجمالي)

amount_due MUST be null unless explicitly printed.

tables column names are not always correct, look at the table content to determine the correct column names.

THEN:

net_total_amount = SUM of those explicit section totals

This rule applies ONLY to section totals and nothing else.

FOOTER TABLE DETECTION & MAPPING RULE (MANDATORY):
If subtotal is not in the text then calculate it.
Some tables represent DOCUMENT TOTALS, not service items.


MAPPING RULE
if a table contains these columns then:
دينار is ammount
القيمة is code
الكود is service_name_en
الخدمة is service_name_ar and date time.

row with only one data cell(<td>) is a section name.
footer total is usually after the table like this:

**الاجمالي:** 25,985.000 دينار
**المدفوع:** 985.000 دينار
**قيمة التعطية:** 25,000.000 دينار
الاجمالي is net_total_amount
المدفوع is amount_paid
قيمة التعطية is amount_due
Note that total can also be written in english if arabic is not present.

IGNORE THESE TITLES (NEVER SECTIONS)

فاتورة إيواء


These are document titles, not section names.



REQUIRED OUTPUT FORMAT

Output ONLY valid JSON.
No explanations. No comments. No extra text.

JSON STRUCTURE
{
  "documents": [
    {
      "header": {
        "invoice_number": "String",
        "file_number": "String",
        "patient_name": "String",
        "date": "ISO String or null",
        "admission_date": "ISO String or null",
        "discharge_date": "ISO String or null",
        "company_name": "String or null",
        "doctor_name_en": "String or null",
        "doctor_name_ar": "String or null",
        "specialty": "String or null",
        "insurer_name": "String or null",
        "ward": "String or null",
        "room_type": "String or null"
      },
      "patient_identity": {
        "id_employee_name": "String or null",
        "id_card_number": "String or null",
        "id_date_of_birth": "ISO String or null",
        "id_validity_period": "ISO String-ISO String or null"
      },
      "sections": [
        {
          "section_name": "String or null",
          "section_subtotal": "String or null",
          "items": [
            {
              "service_description_en": "String or null",
              "service_description_ar": "String or null",
              "code": "String or null",
              "date": "String",
              "time": "String or null",
              "unit_price": "String or null",
              "company_price": "String or null",
              "patient_price": "String or null",
              "net_price": "Number or null",
              "quantity": "String or null",
              "amount": "Number or null"
            }
          ]
        }
      ],
      "footer": {
        "net_total_amount": "Number or null",
        "paid": "String or null",
        "amount_due": "Number or null"
      }
    }
  ]
}"""
DEFAULT_JANZOUR_PROMPT = """
You are an information extraction engine.

Your task is to extract structured JSON from hospital billing and medical documents.

This is a medical and insurance document.
Accuracy and data integrity are critical.

ABSOLUTE CORE PRINCIPLES (NO EXCEPTIONS)
1. NO CALCULATIONS (EXCEPT WHERE EXPLICITLY ALLOWED)

DO NOT calculate, infer, derive, or estimate totals.

Copy totals ONLY if explicitly written.

If a value is missing → use null.

Never fabricate values.

2. ZERO VALUES ARE VALID

0, 0.00, "0.00" are valid ONLY if explicitly present.

Never replace missing values with zero.

3. PRESERVE ORIGINAL VALUES

Keep prices exactly as written (string format).

Do not normalize, round, or reformat numbers.

Do not add derived fields.

4. LANGUAGE PRESERVATION

DO NOT translate unless explicitly requested.

Arabic stays Arabic.

English fields are filled only if English text exists.

MULTI-INVOICE & DOCUMENT CONTROL (CRITICAL)
DOCUMENT GROUPING RULE

The unique document key is invoice_number.

Before creating a new document:

CHECK all previously created documents.

If the invoice_number already exists:

REUSE that document

APPEND sections to it

DO NOT create a new header

Create a new document ONLY if the invoice number has NEVER appeared before.

FILE NUMBER IMMUTABILITY

file_number is extracted ONCE per invoice.

If multiple file numbers appear:

Use the FIRST occurrence only

Ignore all others

Never assign multiple file numbers to one invoice.

DOCUMENT LOCKING RULE (CRITICAL)

Once a document for an invoice_number is created:

The header becomes READ-ONLY.

DO NOT overwrite or modify header fields.

Subsequent pages with the same invoice_number:

MAY ONLY append sections

MAY NOT create a new document

CONTINUATION RULE (MANDATORY)

A document continues across ALL pages until a NEW invoice_number is found.

NEVER assume a document is complete before end of input.

Do NOT stop extraction early even if totals appear.

SECTION & TABLE HANDLING
SECTION ACCUMULATION RULE

Sections with the SAME section_name MAY appear multiple times.

Each physical table = one section object.

DO NOT merge tables unless rows clearly continue.

TABLE ROBUSTNESS RULE

Table column structure may vary.

Always extract rows if ANY of the following exist:

service description

service code

date or time

any price field

Do NOT skip tables due to unfamiliar columns.

Every <tr> containing a service description AND code MUST produce an item.

TABLE COMPLETENESS RULE

EVERY table must be interpreted.

Tables without service_description AND code are NEVER service tables.

SECTION SUBTOTAL RULE

Copy section subtotals ONLY if explicitly written.

If the last row has no code → treat as subtotal row.

If the last row has a code → section_subtotal = null.

HEADER & IDENTITY RULES

Extract header fields only if present.

invoice_number and file_number must NOT be empty.

Do NOT infer:

doctor names

specialties

room types

identity fields

patient_identity appears ONLY under an ID Card section.

id_card_number must match format: ACA-xxxx-xxxxx-xxx.

If multiple IDs exist → use the matching format only.

FOOTER TOTAL RULES (STRICT)
FOOTER SAFETY

DO NOT write 0 or 0.00 unless explicitly printed.

If no grand total exists:

net_total_amount = null

amount_due = null

TOTAL PRICE RULE (ONLY ALLOWED CALCULATION)

If NO single grand total exists

BUT multiple section totals are explicitly labeled:

net_total_amount = SUM of explicit section totals

amount_due remains null unless explicitly printed.

FOOTER SUMMARY TABLE TEMPLATE (CRITICAL)
FOOTER TABLE DETECTION RULE

A table MUST be treated as a FOOTER SUMMARY TABLE if ALL apply:

Exactly 5 columns

Column headers include (Arabic):

القيمة

الجهة

المريض

الإجمالي

الخدمة الطبية

Rows contain numeric totals only

"الخدمة الطبية" column is empty or null

No service code exists anywhere in the table

FOOTER TABLE HANDLING (MANDATORY)

DO NOT create sections from this table

DO NOT create items from this table

Use the table ONLY to populate footer fields

FOOTER VALUE MAPPING

net_total_amount → value under الإجمالي

paid → value under الجهة

amount_due → value under المريض

MULTI-ROW FOOTER RULE

If multiple rows exist:

Use the LAST row where at least one value ≠ 0.00

Ignore rows where ALL values are 0.00

IGNORE THESE TITLES (NEVER SECTIONS)

فاتورة إيواء

حالة مستشفى

كشف تفاصيل الخدمات

These are document titles only.

REQUIRED OUTPUT FORMAT

Output ONLY valid JSON

No explanations

No comments

No extra text

JSON STRUCTURE
{
  "documents": [
    {
      "header": {
        "invoice_number": "String",
        "file_number": "String",
        "patient_name": "String",
        "date": "ISO String or null",
        "admission_date": "ISO String or null",
        "discharge_date": "ISO String or null",
        "company_name": "String or null",
        "doctor_name_en": "String or null",
        "doctor_name_ar": "String or null",
        "specialty": "String or null",
        "insurer_name": "String or null",
        "ward": "String or null",
        "room_type": "String or null"
      },
      "patient_identity": {
        "id_employee_name": "String or null",
        "id_card_number": "String or null",
        "id_date_of_birth": "ISO String or null",
        "id_validity_period": "ISO String-ISO String or null"
      },
      "sections": [
        {
          "section_name": "String or null",
          "section_subtotal": "String or null",
          "items": [
            {
              "service_description_en": "String or null",
              "service_description_ar": "String or null",
              "code": "String or null",
              "date": "String",
              "time": "String or null",
              "unit_price": "String or null",
              "company_price": "String or null",
              "patient_price": "String or null",
              "net_price": "Number or null",
              "quantity": "String or null",
              "amount": "Number or null"
            }
          ]
        }
      ],
      "footer": {
        "net_total_amount": "Number or null",
        "paid": "String or null",
        "amount_due": "Number or null"
      }
    }
  ]
}
"""

def sse(event: str, data):
    """Format Server-Sent Events"""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

async def default_progress_callback(event, data):
    pass



def extract_images_from_pdf(pdf_path: str, output_dir: str) -> List[str]:
    """
    Extract all pages from a PDF as images.
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save extracted images
        
    Returns:
        List of paths to extracted page images
    """
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    image_paths = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        # Render page to pixmap with high DPI
        pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
        
        # Save as PNG
        image_path = os.path.join(output_dir, f"page_{page_num + 1}.png")
        pix.save(image_path)
        image_paths.append(image_path)
    
    doc.close()
    return image_paths


def remove_consecutive_duplicates(text: str) -> str:
    """Remove consecutive duplicate lines from text"""
    lines = text.split('\n')
    result = []
    prev = None
    
    for line in lines:
        if line != prev:
            result.append(line)
            prev = line
    
    return '\n'.join(result)



# -----------------------------
# Helper Functions (Integrated from main.py)
# -----------------------------

def image_to_base64(image: Image.Image) -> str:
    """Converts a PIL Image object to a base64 encoded string."""
    buffered = io.BytesIO()
    # Save as JPEG for compression and size efficiency
    image.save(buffered, format="JPEG") 
    return base64.b64encode(buffered.getvalue()).decode()


def get_prompt_by_keyword(keyword: str) -> str:
    """Return the correct prompt for a job keyword."""
    kw = (keyword or "").lower()

    if "janzour" in kw:
        return (
            """Extract all text from the document. Transcribe Arabic labels exactly and provide values accurately.

            STRICT FORMATTING RULES:
            1. Ignore watermarks, QR codes, and logos.
            2. DATE CONVERSION: The document uses DD/MM/YY and YYYY-MM-DD formats. Convert ALL dates to the DD/MM/YYYY standard. Crucially, ensure the year is always 4 digits (e.g., 2025, not 25).
            3. TABLE EXTRACTION: Extract data from each table (Cash, Stay, Supervision, Analysis) row by row.
            4. COLUMN MAPPING: When transcribing data rows, map the Arabic column names (الجهة, المريض, صافي السعر, إلخ) to their corresponding values precisely, even if the value is zero or an empty cell.
            5. GENERAL DETAILS: For the header section (التاريخ, المريض, الجهة, الإقامة), extract all text pairs verbatim.
            
            Note: For fields with dates like 'الإقامة: من 24/04/2025 18:48 إلى 26/04/2025 12:32', extract them exactly as they appear without reordering the dates within the range.
             *FINAL OUTPUT INSTRUCTION:*
             Present the extracted data (General Details and all table data) structured *ENTIRELY in HTML format*.Only return HTML table within <table></table>. Ignore images, Stamps, Seals"""
        )

    if "massara" in kw:
        return ("""### ROLE
Precision Medical Data Extractor.

### RULES
1. NUMBERS: Use Western/English digits only (e.g., 10,762.500). 
2. NO ROWSPAN: Never use the 'rowspan' attribute. Every single line in the image must be its own <tr>.
3. COLUMN STRUCTURE: The table MUST have exactly 4 columns: [دينار | القيمة | الكود | الخدمة].
4. COLSPAN: Only use 'colspan="3"' for the 'الخدمة' column when it is a section header or contains the full service description.
5. DATA INTEGRITY:
    - Capture the Date (DD.MM.YYYY) and Time (HH:MM) and keep them inside the 'الخدمة' (Service) cell.
    - If a row is a section header (e.g., "عمليات جراحية"), include it as a <tr> with the text in the 'الخدمة' cell and leave 'الكود' and 'القيمة' empty.
    - Do not repeat text from previous rows into new rows.

### TABLE MAPPING
- Column 1 (Rightmost in image, Leftmost in HTML): Currency (دينار)
- Column 2: Value (القيمة)
- Column 3: Code (الكود)
- Column 4 (Leftmost in image, Rightmost in HTML): Service Description (الخدمة) - This cell must contain English Name + Date/Time + Arabic Name.

### OUTPUT
- Return ONLY the HTML table.
- Use <br> to separate lines within a single <td>.""")

    if kw == "idcard" or "idcard" in kw:
        return ("""STRICT FORMATTING RULES:
1. IGNORE ARTIFACTS: Ignore watermarks, QR codes, and logos.

2. DATE CONVERSION: 
   - The document uses YYYY-MM-DD format (e.g., 2026-02-16).
   - You must convert ALL dates to DD-MM-YYYY format.
   - VALIDITY LINE: The validity line contains two dates (Start and End). Treat them as separate values. Do not merge them.
     Input: "2026-02-16 - 2025-02-17" -> Output: "16-02-2026 - 17-02-2025"

3. ID NUMBER (CRITICAL):
   - The field labeled "رقم البطاقة" contains Latin/English characters.
   - READING DIRECTION: You MUST read this specific value LEFT-TO-RIGHT, even though the rest of the document is Right-to-Left.
   - STRUCTURE ENFORCEMENT: The ID strictly follows this pattern: [3 Letters]-[4 Digits]-[5 Digits]-[3 Characters].
   - ZERO PRESERVATION: Ensure you capture all zeros in the middle sequence. Look closely for '00080', not '0080'.
   - Example format: ACA-xxxx-xxxxx-xxx.
   - If the text appears as "P02-ACA...", you are reading it backwards. Reverse it to start with "ACA".

4. ARABIC ACCURACY:
   - Ensure the label "اسم المستفيد" is read correctly (do not confuse with "المستلم").
   - Read the names carefully.

Read the document naturally, but apply these formatting constraints strictly.""")

    if "إيصال رقم" in keyword or "receipt" in kw:
        return ("""Extract all text from the document exactly as it appears. Preserve line breaks and formatting. preserve headers and structure. Ignore logos, stamps, watermarks, and any decorative elements that are not part of the main text. Read the document naturally as if a human is reading it. Do not omit any visible text. Preserve formatting, spacing, and symbols. Only return HTML table within <table></table>."""
        )

    # default
    return "Extract the arabic text."


# --- Cropping Helpers ---

def crop_region_from_image(image_path, bbox):
    """Crop a region from an image using bbox = [x1, y1, x2, y2]"""
    if isinstance(image_path, Image.Image):
        img = image_path
    else:
        img = Image.open(image_path)
    x1, y1, x2, y2 = bbox
    return img.crop((x1, y1, x2, y2))

def crop_below_bbox(image_path, bbox, save_path=None):
    """Crop the image to remove everything above the bbox."""
    if isinstance(image_path, Image.Image):
        img = image_path
    else:
        img = Image.open(image_path)
    x1, y1, x2, y2 = map(float, bbox)
    crop_box = (0, int(y1), img.width, img.height)
    cropped = img.crop(crop_box)
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        cropped.save(save_path)
    return cropped

def crop_from_lower(image_path, bbox, offset=50, save_path=None):
    """Crop the image starting from the bottom of the bbox to the bottom of the image."""
    if isinstance(image_path, Image.Image):
        img = image_path
    else:
        img = Image.open(image_path)
    x1, y1, x2, y2 = map(float, bbox)
    start_y = int(y2) + offset
    crop_box = (0, int(start_y), img.width, img.height)
    cropped = img.crop(crop_box)
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        cropped.save(save_path)
    return cropped

def crop_from_upper(image_path, bbox, offset=50, save_path=None):
    """Crop the image starting from the top of the image to the top of the bbox."""
    if isinstance(image_path, Image.Image):
        img = image_path
    else:
        img = Image.open(image_path)
    x1, y1, x2, y2 = map(float, bbox)
    end_y = int(y1) - offset
    end_y = max(0, end_y)
    crop_box = (0, 0, img.width, end_y)
    cropped = img.crop(crop_box)
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        cropped.save(save_path)
    return cropped

# --- QR & Barcode Helpers ---

def remove_barcode(img, expand_w=0.1, expand_h=0.4):
    """Detect barcode → expand bounding box → whiten pixels."""
    barcode_model = model_manager.initialize_barcode_model()
    
    np_img = np.array(img)
    h, w = np_img.shape[:2]
    
    # Run YOLO detection
    results = barcode_model.predict(np_img, verbose=False)
    
    if len(results[0].boxes) == 0:
        return img
    
    output_img = img.copy()
    draw = ImageDraw.Draw(output_img)
    
    for box in results[0].boxes:
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        
        box_w = x2 - x1
        box_h = y2 - y1
        
        new_x1 = max(0, int(x1 - box_w * expand_w))
        new_y1 = max(0, int(y1 - box_h * expand_h))
        new_x2 = min(w - 1, int(x2 + box_w * expand_w))
        new_y2 = min(h - 1, int(y2 + box_h * expand_h))
        
        draw.rectangle([new_x1, new_y1, new_x2, new_y2], fill="white")
        
    return output_img

def get_finder_patterns(cropped_qr_image):
    if cropped_qr_image.size == 0:
        return []
    gray = cv2.cvtColor(cropped_qr_image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    pattern_centers = []
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)
        area = cv2.contourArea(contour)
        if len(approx) == 4 and area > 100:
            x, y, w, h = cv2.boundingRect(contour)
            if 0.8 < w/h < 1.2:
                M = cv2.moments(contour)
                if M["m00"] != 0:
                    cX = int(M["m10"] / M["m00"])
                    cY = int(M["m01"] / M["m00"])
                    pattern_centers.append((cX, cY))
    return pattern_centers

def determine_orientation(pattern_centers):
    if len(pattern_centers) < 3:
        return 0
    y_coords = sorted([p[1] for p in pattern_centers])
    
    # Robust logic: Find the largest vertical gap to separate "top" and "bottom" groups
    max_gap = 0
    split_index = 0
    for i in range(len(y_coords) - 1):
        gap = y_coords[i+1] - y_coords[i]
        if gap > max_gap:
            max_gap = gap
            split_index = i
            
    # Points with smaller Y (above gap) are "top" group
    # Points with larger Y (below gap) are "bottom" group
    count_top = split_index + 1
    count_bottom = len(y_coords) - (split_index + 1)
    
    print(f"DEBUG: determine_orientation: y_coords={y_coords}, max_gap={max_gap}, top={count_top}, bottom={count_bottom}")
    
    # 0 degrees: 2 finders at top, 1 at bottom (more at top)
    # 180 degrees: 1 finder at top, 2 at bottom (more at bottom)
    return 0 if count_top > count_bottom else 180

def predict_qr_detection(image):
    qr_detector = model_manager.initialize_qr_detector()
    return qr_detector.detect(image=image, is_bgr=True)

def process_and_crop_qr_region(image, detections, image_bboxes, expansion_factor_up=4, expansion_factor_right=5.8):
    if not detections:
        return None
    
    h_orig, w_orig, _ = image.shape
    orientation_angle = 0
    target_detection = detections[0]
    x1, y1, x2, y2 = map(int, target_detection['bbox_xyxy'])
    
    cropped_image_qr = image[y1:y2, x1:x2]
    if cropped_image_qr.size > 0:
        pattern_centers_local = get_finder_patterns(cropped_image_qr)
        if len(pattern_centers_local) >= 3:
            orientation_angle = determine_orientation(pattern_centers_local)
           
    # Apply rotation
    rotated_image = image.copy()
    
    if orientation_angle == 180:
        print("rotating image")
        rotated_image = cv2.rotate(rotated_image, cv2.ROTATE_180)
        
    h_rot, w_rot = rotated_image.shape[:2]
    
    # Transform QR bbox for cropping (in rotated coordinates)
    if orientation_angle == 180:
        x1r = w_orig - x2
        y1r = h_orig - y2
        x2r = w_orig - x1
        y2r = h_orig - y1
        x1, x2 = min(x1r, x2r), max(x1r, x2r)
        y1, y2 = min(y1r, y2r), max(y1r, y2r)
        
    w_box = x2 - x1
    h_box = y2 - y1
    
    y1_final = max(0, int(y2 - h_box * expansion_factor_up))
    x2_final = min(w_rot, int(x1 + w_box * expansion_factor_right))
    x1_final = max(0, x1)
    y2_final = min(h_rot, y2)
    
    expanded_area = (x2_final - x1_final) * (y2_final - y1_final)

    # Whiten image bboxes
    for item in image_bboxes:
        bx1, by1, bx2, by2 = map(int, item["bbox"])
        if orientation_angle == 180:
            bx1r = w_orig - bx2
            by1r = h_orig - by2
            bx2r = w_orig - bx1
            by2r = h_orig - by1
            bx1, bx2 = min(bx1r, bx2r), max(bx1r, bx2r)
            by1, by2 = min(by1r, by2r), max(by1r, by2r)
        
        bx1 = max(0, bx1)
        by1 = max(0, by1)
        bx2 = min(w_rot, bx2)
        by2 = min(h_rot, by2)
        
        item_area = (bx2 - bx1) * (by2 - by1)
        # Check size before whitening: skip if item is larger than half the expanded region
        if item_area < 0.3 * expanded_area:
            rotated_image[by1:by2, bx1:bx2] = 255
    
    cropped_final = rotated_image[y1_final:y2_final, x1_final:x2_final]
    cv2.imwrite('idcard.png', cropped_final)
    if cropped_final.size == 0:
        return None
    return cropped_final




async def prepare_page_input(image_path: str) -> Optional[Dict]:
    """
    Prepare input for a single page by analyzing layout and determining processing mode.
    Fully implemented using logic from main.py.
    """
    # Load raw (cv2) for layout/qr detectors
    input_image_cv = cv2.imread(image_path)
    if input_image_cv is None:
        print(f"Error loading image: {image_path}")
        return None

    try:
        results = process_layout(image_path)
    except Exception as e:
        print(f"prepare_page_input: layout error for {image_path}: {e}")
        return None

    # Flags and items
    doc_title = next((item for item in results if item["label"] == "doc_title"), None)
    figure_title = next((item for item in results if item["label"] == "figure_title"), None)
    footer = next((item for item in results if item["label"] == "footer"), None)
    paragraph_title = next((item for item in results if item["label"] == "paragraph_title"), None)
    header_image = next((item for item in results if item["label"] == "header_image"), None)
    header = next((item for item in results if item["label"] == "header"), None)
    has_table = any(item["label"] == "table" for item in results)
    has_header = any(item["label"] in ("header", "header_image") for item in results)

    # Skip rule: header exists but no table (unless it's an ID card check later)
    # Replicating main.py logic exactly:
    if (not has_table) and has_header:
        # Check if ID card before skipping? Use main.py logic structure
        pass 

    final_image = None
    keyword = "default"
    mode = "default"

    # Janzour: doc_title + table
    if doc_title is not None and has_table:
        print(f"prepare_page_input: janzour detected for {image_path}")
        
        # Crop the doc_title and check if it should be skipped
        crop = crop_region_from_image(image_path, doc_title["bbox"])
        
        # Perform OCR on the cropped doc_title
        ocr_job = {
            "image": crop,
            "prompt": "extract the arabic text"
        }
        
        try:
            # Run OCR to check the title
            ocr_result = await _run_single_inference_task(ocr_job, max_new_tokens=512)
            print(f"prepare_page_input: ocr_result: {ocr_result}")
            # Check if result contains the skip phrase
            if isinstance(ocr_result, str) and "أدوية ومستلزمات من الايواء" in ocr_result:
                print(f"prepare_page_input: skipping page - contains 'أدوية ومستلزمات من الايواء'")
                return None
        except Exception as e:
            print(f"prepare_page_input: OCR error on doc_title: {e}")
            # Continue processing even if OCR fails
        
        cropped = crop_below_bbox(image_path, doc_title["bbox"])
        cropped = remove_barcode(cropped)
        final_image = cropped
        if footer is not None:
             final_image = crop_from_upper(final_image, footer["bbox"])
        
        keyword = "janzour"
        mode = "janzour"

    # ID Card: fallback path when no header+table
    elif not (has_header and has_table):
        qr_detections = predict_qr_detection(input_image_cv)
        if len(qr_detections) > 0:
            print(f"prepare_page_input: idcard detected for {image_path}")
            image_bboxes = [
                {
                    "label": item["label"],
                    "bbox": item["bbox"],
                }
                for item in results if item["label"] == "image"
            ]
            cropped_cv = process_and_crop_qr_region(
                input_image_cv, qr_detections, image_bboxes,
                expansion_factor_up=4.0, expansion_factor_right=5.8,
            )
            if cropped_cv is not None:
                final_image = Image.fromarray(cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB))
                keyword = "idcard"
                mode = "idcard"
            else:
                return None
        else:
            print(f"prepare_page_input: skip (no qr and not header+table) — {image_path}")
            return None

    # Massara: no doc_title and no figure_title
    elif doc_title is None and paragraph_title is None:
        print(f"prepare_page_input: massara detected for {image_path}")
        target_header = header_image if header_image else header
        if target_header:
            final_image = crop_from_lower(image_path, target_header["bbox"])
        else:
            final_image = Image.open(image_path).convert("RGB")
            
        final_image = remove_barcode(final_image)
        if footer is not None:
            final_image = crop_from_upper(final_image, footer["bbox"])
            
        keyword = "massara"
        mode = "massara"

    # Massara medicine case: doc_title None and figure_title present
    elif doc_title is None and paragraph_title is not None:
        print(f"prepare_page_input: massara medicine for {image_path}")
        
        # Crop the figure title and check if it should be skipped
        crop = crop_region_from_image(image_path, paragraph_title["bbox"])
        
        # Perform OCR on the cropped figure title
        ocr_job = {
            "image": crop,
            "prompt": "extract the arabic text"
        }
        
        try:
            # Run OCR to check the title
            ocr_result = await _run_single_inference_task(ocr_job, max_new_tokens=512)
            print(f"prepare_page_input: ocr_result: {ocr_result}")
            # Check if result contains the skip phrase
            if isinstance(ocr_result, str) and "أدوية ومستلزمات من الايواء" in ocr_result:
                print(f"prepare_page_input: skipping page - contains 'أدوية ومستلزمات من الايواء'")
                return None
        except Exception as e:
            print(f"prepare_page_input: OCR error on figure_title: {e}")
            # Continue processing even if OCR fails
        
        keyword = "massara medicine"
        final_image = Image.open(image_path).convert("RGB")
        final_image = remove_barcode(final_image)
        mode = "massara"

    # Default fallback
    else:
        final_image = Image.open(image_path).convert("RGB")
        keyword = "default"
        mode = "default"

    prompt = get_prompt_by_keyword(keyword)

    return {
        "image": final_image,
        "prompt": prompt,
        "mode": mode,
        "original_path": image_path,
    }


import time
import asyncio

async def _run_single_inference_task(job: Dict, max_new_tokens: int) -> Union[str, Exception]:
    """
    Performs a single, non-blocking OCR API call.
    Returns the generated content or the Exception object if an error occurs.
    """
    try:
        prompt = job["prompt"]
        image = job["image"]
        
        base64_img = image_to_base64(image)
        
        client = model_manager.initialize_vllm_client()
        
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=settings.VLLM_MODEL_NAME,
            messages=[
                {
                    "role": "user", 
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}},
                        {"type": "text", "text": prompt}
                    ]
                }
            ],
            temperature=0.0,
            max_tokens=max_new_tokens,
            extra_body={
                "repetition_penalty": 1.1, 
                "top_p": 1.0   
            }
        )
        print(f"Finish Reason: {response.choices[0].finish_reason}")
        if response.choices and response.choices[0].message:
            return response.choices[0].message.content
        else:
            return "Error: No generation returned."
            
    except Exception as e:
        # Return the exception object instead of raising it,
        # allowing other tasks to complete.
        return e


async def run_batch_inference(batch_jobs: List[Dict], max_new_tokens: int = 8192) -> List[str]:
    """
    Run batch OCR inference using vLLM client CONCURRENTLY.
    """
    if not batch_jobs:
        return []
    
    num_pages = len(batch_jobs)
    
    start_time = time.perf_counter()
    
    # Create a list of coroutines (tasks) for each item in the batch
    tasks = [
        _run_single_inference_task(job, max_new_tokens)
        for job in batch_jobs
    ]
    
    # Run all tasks concurrently and wait for all of them to complete.
    # We use return_exceptions=True to ensure that a failure in one page 
    # does not cancel the entire batch.
    concurrent_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = time.perf_counter()
    total_time = end_time - start_time
    avg_time = total_time / num_pages if num_pages > 0 else 0
    
    print("-" * 50)
    print(f"✅ BATCH INFERENCE COMPLETE ({num_pages} pages)")
    print(f"⏱️ Total Wall-Clock Time: {total_time:.2f} seconds")
    print(f"⚡ Time Per Page (Avg): {avg_time:.2f} seconds/page")
    print("-" * 50)
    
    # Process results, handling potential exceptions
    results = []
    for result in concurrent_results:
        if isinstance(result, Exception):
            print(f"Error processing job: {result}")
            results.append(f"API Error: {result.__class__.__name__}: {result}")
        else:
            results.append(result)
    
    return results


async def process_single_pdf_batched(pdf_path: str, temp_dir: str, max_new_tokens: int = 8192):
    """
    Complete async generator for processing a single PDF with streaming progress.
    
    Args:
        pdf_path: Path to PDF file
        temp_dir: Temporary directory for intermediate files
        max_new_tokens: Maximum tokens for OCR generation
        
    Yields:
        Server-sent events with progress updates and final results
    """
    pdf_name = Path(pdf_path).stem
    pdf_images_dir = os.path.join(temp_dir, f"{pdf_name}_images")
    os.makedirs(pdf_images_dir, exist_ok=True)

    # STEP 1 — Extract images
    yield sse("progress", {
        "step": "extract_images",
        "message": "Extracting images from PDF"
    })

    extracted_images = extract_images_from_pdf(pdf_path, pdf_images_dir)

    yield sse("progress", {
        "step": "extract_images",
        "pages": len(extracted_images),
        "status": "done"
    })

    # STEP 2 — Preprocessing
    batch_jobs = []
    skipped_pages = []

    for idx, image_path in enumerate(extracted_images):
        try:
            job = await prepare_page_input(image_path)
            if job:
                job["page_index"] = idx
                batch_jobs.append(job)
            else:
                skipped_pages.append({"page_index": idx, "status": "skipped"})
        except Exception as e:
            skipped_pages.append({"page_index": idx, "error": str(e)})

    yield sse("progress", {
        "step": "preprocessing",
        "prepared_pages": len(batch_jobs),
        "skipped_pages": len(skipped_pages)
    })

    # STEP 3 — OCR
    yield sse("progress", {
        "step": "ocr",
        "message": "Running batch OCR inference"
    })

    raw_results = []
    if batch_jobs:
        raw_results = await run_batch_inference(batch_jobs, max_new_tokens=11000)

    yield sse("progress", {
        "step": "ocr",
        "status": "done"
    })

    joined = "\n".join(raw_results)
    
    # STEP 4 — Extract structured JSON with OpenAI
    yield sse("progress", {
        "step": "extract_json",
        "message": "Extracting structured JSON from OCR results"
    })
    final_pages = []    
    # Initialize OpenAI client with API key from environment
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.4,
        messages=[
            {"role": "system", "content": """You are an information extraction engine.

Your task is to extract structured JSON from hospital billing and medical documents.

STRICT RULES (MUST FOLLOW):

1. DO NOT calculate, sum, infer, or derive any totals.
   - Only copy totals that are explicitly written in the document.
   - If a grand total is not present, DO NOT create one.

2. ZERO VALUES ARE VALID DATA.
   - 0, 0.00, and "0.00" must ALWAYS be preserved.
   - Never drop, ignore, or omit a field because its value is zero.

3. DO NOT invent or guess any data.
   - If a value is missing or not present in the document, use null.
   - Never generate placeholder values (e.g., fake IDs, dates, numbers).

4. DO NOT translate unless explicitly requested.
   - Preserve service descriptions exactly as written.
   - If Arabic text is present, keep it in Arabic.
   - English fields should only be filled if English text exists in the document.

5. PRESERVE ORIGINAL VALUES.
   - Keep prices exactly as shown (string format).
   - Do not convert strings to numbers.
   - Do not add calculated fields like "amount" or "net_total".

6. STRUCTURE RULES:
   - Group services under their exact section names.
   - Copy section subtotals ONLY if explicitly written.
   - Each service must include all columns shown in the table, including zero columns.
   - IGNORE "فاتورة إيواء" - this is a document title, NOT a section name. Never use it as section_name.

7. HEADER & IDENTITY:
   - Extract header fields only if they appear in the document.
   - Do not infer doctor names, specialties, room types, or identity details.
   - Use null for unknown identity fields.

8. OUTPUT FORMAT:
   - Output ONLY valid JSON.
   - No explanations, no comments, no emojis.
   - Do not say "Completed" or similar text.

9. TOTAL PRICE RULE:
If the document does not contain a single grand total, but contains multiple section totals explicitly labeled
(e.g. "المبلغ الإجمالي"), then the overall total price equals the SUM of those explicit section totals.
This rule applies ONLY to section totals and to no other fields.

This is a medical and insurance document.
Accuracy and data integrity are critical.

Expected JSON structure:
{
  "header": {
    "invoice_number": "String",
    "file_number": "String",
    "patient_name": "String",
    "date": "ISO String or null",
    "admission_date": "ISO String or null",
    "discharge_date": "ISO String or null",
    "company_name": "String or null",
    "doctor_name_en": "String or null",
    "doctor_name_ar": "String or null",
    "specialty": "String or null",
    "insurer_name": "String or null",
    "ward": "String or null",
    "room_type": "String or null"
  },
  "patient_identity": {
    "id_employee_name": "String or null",
    "id_card_number": "String or null",
    "id_date_of_birth": "ISO String or null",
    "id_validity_period": "ISO String or null"
  },
  "sections": [
    {
      "section_name": "String or null",
      "section_subtotal": "String or null",
      "items": [
        {
          "service_description_en": "String or null",
          "service_description_ar": "String or null",
          "code": "String or null",
          "date": "String",
          "time": "String or null",
          "unit_price": "String or null",
          "company_price": "String or null",
          "patient_price": "String or null",
          "net_price": "Number",
          "quantity": "String or null",
          "amount": "Number"
        }
      ]
    }
  ],
  "footer": {
    "net_total_amount": "Number",
    "paid": "String or null",
    "amount_due": "Number"
  }
}"""},
            {"role": "user", "content": joined}
        ],
    )

    final_pages = response.choices[0].message.content

    yield sse("result", {
        "pdf_path": pdf_path,
        "processed_pages": final_pages,
        "raw_text": joined,
        "skipped": skipped_pages
    })

async def run_ocr_pipeline(pdf_path: str, temp_dir: str, max_new_tokens: int = 8192, progress_callback=None):
    """
    Run the OCR part of the pipeline.
    Returns: (joined_text, skipped_pages_list)
    """
    if progress_callback is None:
        progress_callback = default_progress_callback

    pdf_name = Path(pdf_path).stem
    pdf_images_dir = os.path.join(temp_dir, f"{pdf_name}_images")
    os.makedirs(pdf_images_dir, exist_ok=True)

    # STEP 1 — Extract images
    await progress_callback("progress", {
        "step": "extract_images",
        "message": "Extracting images from PDF"
    })

    extracted_images = extract_images_from_pdf(pdf_path, pdf_images_dir)

    await progress_callback("progress", {
        "step": "extract_images",
        "pages": len(extracted_images),
        "status": "done"
    })

    # STEP 2 — Preprocessing
    batch_jobs = []
    skipped_pages = []

    for idx, image_path in enumerate(extracted_images):
        try:
            job = await prepare_page_input(image_path)
            if job:
                job["page_index"] = idx
                batch_jobs.append(job)
            else:
                skipped_pages.append({"page_index": idx, "status": "skipped"})
        except Exception as e:
            skipped_pages.append({"page_index": idx, "error": str(e)})

    await progress_callback("progress", {
        "step": "preprocessing",
        "prepared_pages": len(batch_jobs),
        "skipped_pages": len(skipped_pages)
    })

    # STEP 3 — OCR
    await progress_callback("progress", {
        "step": "ocr",
        "message": "Running batch OCR inference"
    })

    raw_results = []
    if batch_jobs:
        raw_results = await run_batch_inference(batch_jobs, max_new_tokens=11500)

    await progress_callback("progress", {
        "step": "ocr",
        "status": "done"
    })

    joined = "\n".join(raw_results)
    return joined, skipped_pages
    

async def run_gpt_pipeline(text: str, progress_callback=None, system_prompt: str = None):
    """Run GPT extraction using local vLLM"""
    if progress_callback is None:
        progress_callback = default_progress_callback

    await progress_callback("progress", {
        "step": "extract_json",
        "message": "Extracting structured JSON from OCR results"
    })

    final_pages = "{}"
    # Use OpenAI client as in process_single_pdf_batched
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    if system_prompt is None:
        system_prompt = DEFAULT_JANZOUR_PROMPT
        
    # Call model
    try:
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o-mini",
            temperature=0.4,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ]
        )
        final_pages = resp.choices[0].message.content

        
        await progress_callback("progress", {"step": "extract_json", "status": "done"})
        return final_pages

    except Exception as e:
        print(f"GPT Error in pipeline: {e}")
        # Notify of specific error before re-raising
        await progress_callback("progress", {
            "step": "extract_json", 
            "status": "failed",
            "error": str(e)
        })
        raise e



