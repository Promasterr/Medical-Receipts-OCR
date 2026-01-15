from fastapi import APIRouter, File, UploadFile, HTTPException
from typing import List
import os
import shutil
import uuid
from redis import asyncio as aioredis

from app.config import settings
from app.tasks import process_massara_pipeline

router = APIRouter(tags=["Massara PDF Processing"])

UPLOAD_DIR = "storage/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/process-pdf/massara/")
async def process_massara_pdf(file: UploadFile = File(...)):
    """
    Submit a single PDF for Massara template processing.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    
    task_id = str(uuid.uuid4())
    file_id = f"{task_id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Launch Celery Task for Massara
    task = process_massara_pipeline.apply_async(
        args=[os.path.abspath(file_path), file.filename],
        task_id=task_id
    )
    
    return {"task_id": task_id, "filename": file.filename, "status": "queued", "template": "massara"}


@router.post("/batch-process-pdf/massara/")
async def batch_process_massara_pdf(files: List[UploadFile] = File(...)):
    """
    Submit multiple PDFs for Massara template processing.
    """
    results = []
    
    # Filter valid files first
    valid_files = [f for f in files if f.filename.lower().endswith(".pdf")]
    
    if not valid_files:
        return []
        
    batch_id = str(uuid.uuid4())
    
    # Initialize batch counter in Redis
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await redis.set(f"batch_count:{batch_id}", len(valid_files))
    await redis.close()
    
    for file in valid_files:
        task_id = str(uuid.uuid4())
        file_id = f"{task_id}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, file_id)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        process_massara_pipeline.apply_async(
            args=[os.path.abspath(file_path), file.filename, batch_id],
            task_id=task_id
        )
        
        results.append({
            "task_id": task_id, 
            "filename": file.filename, 
            "status": "queued",
            "batch_id": batch_id,
            "template": "massara"
        })
        
    return results
