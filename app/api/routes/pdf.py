from fastapi import APIRouter, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect
from typing import List
import os
import shutil
import uuid
import json
import asyncio
from pathlib import Path
from redis import asyncio as aioredis

from app.config import settings
from app.tasks import process_document_pipeline

router = APIRouter(tags=["PDF Processing"])

UPLOAD_DIR = "storage/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/process-pdf/")
async def process_pdf(file: UploadFile = File(...)):
    """
    Submit a single PDF for processing.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    
    task_id = str(uuid.uuid4())
    file_id = f"{task_id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Launch Celery Task
    # Note: We pass original_filename to track it for the response updates
    task = process_document_pipeline.apply_async(
        args=[os.path.abspath(file_path), file.filename],
        task_id=task_id
    )
    
    return {"task_id": task_id, "filename": file.filename, "status": "queued"}

@router.post("/batch-process-pdf/")
async def batch_process_pdf(files: List[UploadFile] = File(...)):
    """
    Submit multiple PDFs for processing.
    """
    results = []
    
    # Filter valid files first
    valid_files = [f for f in files if f.filename.lower().endswith(".pdf")]
    
    if not valid_files:
        return []
        
    batch_id = str(uuid.uuid4())
    
    # Initialize batch counter in Redis
    # We use sync Redis client for simplicity in this blocked route, 
    # or async if we want (but requires aioredis setup here).
    # Let's use aioredis since we imported it.
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await redis.set(f"batch_count:{batch_id}", len(valid_files))
    await redis.close()
    
    for file in valid_files:
        task_id = str(uuid.uuid4())
        file_id = f"{task_id}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, file_id)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        process_document_pipeline.apply_async(
            args=[os.path.abspath(file_path), file.filename, batch_id],
            task_id=task_id
        )
        
        results.append({
            "task_id": task_id, 
            "filename": file.filename, 
            "status": "queued",
            "batch_id": batch_id
        })
        
    return results


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print(f"WS: Attempting connection from {websocket.client}")
    await websocket.accept()
    print("WS: Connection accepted")
    
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    pubsub = redis.pubsub()
    
    # Subscribe to all task updates
    # In a real app we might want to segregate by user/session
    await pubsub.psubscribe("task_updates:*")
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                # Message data is a JSON string
                data_str = message["data"]
                # We can just forward it directly
                await websocket.send_text(data_str)
    except WebSocketDisconnect:
        # Client disconnected
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await pubsub.unsubscribe()
        await redis.close()
