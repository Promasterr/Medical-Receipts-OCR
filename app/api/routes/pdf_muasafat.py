from fastapi import APIRouter, File, UploadFile, HTTPException
from typing import List
import os
import shutil
import uuid
from redis import asyncio as aioredis

from app.config import settings
from app.tasks import process_massara_pipeline  # Muasafat uses same pipeline as Massara

router = APIRouter(tags=["Muasafat PDF Processing"])

UPLOAD_DIR = "storage/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/process-pdf/muasafat/")
async def process_muasafat_pdf(file: UploadFile = File(...)):
    """
    Submit a single PDF for Muasafat template processing.
    Muasafat uses the same processing logic as Massara.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    
    task_id = str(uuid.uuid4())
    file_id = f"{task_id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Launch Celery Task (uses Massara pipeline)
    task = process_massara_pipeline.apply_async(
        args=[os.path.abspath(file_path), file.filename],
        task_id=task_id
    )
    
    return {"task_id": task_id, "filename": file.filename, "status": "queued", "template": "muasafat"}


@router.post("/batch-process-pdf/muasafat/")
async def batch_process_muasafat_pdf(files: List[UploadFile] = File(...)):
    """
    Submit multiple PDFs for Muasafat template batch processing using buffered pipeline.
    Muasafat uses the same processing logic as Massara.
    """
    # Filter valid files first
    valid_files = [f for f in files if f.filename.lower().endswith(".pdf")]
    
    if not valid_files:
        return []
        
    batch_id = str(uuid.uuid4())
    
    # Save all PDFs first
    pdf_paths = []
    for file in valid_files:
        task_id = str(uuid.uuid4())
        file_id = f"{task_id}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, file_id)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        pdf_paths.append(os.path.abspath(file_path))
    
    # Initialize batch counter in Redis
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await redis.set(f"batch_count:{batch_id}", len(valid_files))
    await redis.close()
    
    # Trigger SINGLE batch orchestrator task
    from app.tasks import process_massara_batch_pipeline
    process_massara_batch_pipeline.apply_async(
        args=[pdf_paths, batch_id],
        task_id=batch_id
    )
    
    return {
        "batch_id": batch_id,
        "pdf_count": len(pdf_paths),
        "status": "processing",
        "template": "muasafat",
        "message": f"Batch processing started for {len(pdf_paths)} PDFs using buffered pipeline"
    }

