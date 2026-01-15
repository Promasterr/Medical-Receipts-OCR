"""
Pydantic models for API requests and responses.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


# Request Models
class ProcessPDFRequest(BaseModel):
    """Request model for PDF processing (if needed for additional parameters)"""
    max_new_tokens: int = Field(default=8192, description="Maximum tokens for inference")


# Response Models
class PageResult(BaseModel):
    """Single page processing result"""
    page_number: int
    text: str
    parsed_data: Optional[Dict[str, Any]] = None


class ProcessPDFResponse(BaseModel):
    """Response model for PDF processing"""
    pdf_path: str
    processed_pages: List[Dict[str, Any]]
    raw_text: str
    skipped: List[Dict[str, Any]] = []


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    models_loaded: bool = False


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Model exports
__all__ = [
    "ProcessPDFRequest",
    "ProcessPDFResponse",
    "PageResult",
    "HealthResponse",
    "ErrorResponse",
]
