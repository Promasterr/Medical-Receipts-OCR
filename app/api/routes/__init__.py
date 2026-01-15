"""
API Routes package.
Exposes all route modules including template-specific routes.
"""
from . import auth, health, pdf, pdf_janzour, pdf_safwa, pdf_massara, pdf_muasafat

__all__ = ["auth", "health", "pdf", "pdf_janzour", "pdf_safwa", "pdf_massara", "pdf_muasafat"]
