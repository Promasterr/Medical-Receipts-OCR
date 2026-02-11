"""
Health check endpoints.
"""
from fastapi import APIRouter
from app.models.schemas import HealthResponse
from app.models.ml_models import model_manager
from datetime import datetime

router = APIRouter(prefix="/api/health", tags=["Health"])


@router.get("/", response_model=HealthResponse)
async def health_check():
    """
    Basic health check endpoint.
    """
    models_loaded = (
        model_manager.layout_model is not None and
        model_manager.barcode_model is not None and
        model_manager.qr_detector is not None and
        model_manager.vllm_client is not None
    )
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        models_loaded=models_loaded
    )


@router.get("/models")
async def check_models():
    """
    Check if all models are loaded and verify vLLM connectivity.
    """
    vllm_ok = False
    vllm_error = None
    
    if model_manager.vllm_client:
        try:
            # Minimal check: list models
            model_manager.vllm_client.models.list()
            vllm_ok = True
        except Exception as e:
            vllm_error = str(e)

    return {
        "layout_model": model_manager.layout_model is not None,
        "barcode_model": model_manager.barcode_model is not None,
        "qr_detector": model_manager.qr_detector is not None,
        "vllm_client": {
            "initialized": model_manager.vllm_client is not None,
            "reachable": vllm_ok,
            "error": vllm_error
        }
    }
