"""
Main FastAPI application.
Entry point for the OCR Document Processing API.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

import sys
import os

# Add project root to sys.path to allow running script directly
# This resolves ModuleNotFoundError: No module named 'app.config'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings
from app.models.ml_models import model_manager
from app.api.routes import health, pdf, pdf_janzour, pdf_safwa, pdf_massara, pdf_muasafat
# Note: auth module available but not currently exposed as endpoints


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan events.
    Initialize models on startup, cleanup on shutdown.
    """
    # Startup
    print("=" * 60)
    print(f"Starting {settings.APP_TITLE} v{settings.APP_VERSION}")
    print(f"="  * 60)
    
    # Initialize all ML models
    # model_manager.initialize_all() # DISABLED: Models processed in Celery workers only

    
    print("✓ Application ready")
    print("=" * 60)
    
    yield
   
    # Shutdown
    print("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
# app.include_router(auth.router)  # Auth available but not exposed
app.include_router(pdf.router)

# Template-specific routers
app.include_router(pdf_janzour.router)
app.include_router(pdf_safwa.router)
app.include_router(pdf_massara.router)
app.include_router(pdf_muasafat.router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": f"Welcome to {settings.APP_TITLE}",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
