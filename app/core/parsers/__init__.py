"""Parsers module exports"""
from app.core.parsers.text_utils import (
    clean_field,
    extract_field_from_text,
    normalize,
    normalize_jz_date,
    is_arabic,
    header_missing_core_fields,
    remove_consecutive_duplicates
)
from app.core.parsers.header_parser import parse_header, parse_idcard_text
from app.core.parsers.table_parser import (
    html_table_to_json,
    is_section_row,
    find_section_for_table,
    extract_plain_from_header_table
)

__all__ = [
    "clean_field",
    "extract_field_from_text",
    "normalize",
    "normalize_jz_date",
    "is_arabic",
    "header_missing_core_fields",
    "remove_consecutive_duplicates",
    "parse_header",
    "parse_idcard_text",
    "html_table_to_json",
    "is_section_row",
    "find_section_for_table",
    "extract_plain_from_header_table",
]
