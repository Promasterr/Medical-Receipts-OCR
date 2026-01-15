import os
import json
import asyncio
import time
from pathlib import Path
from celery import chain
from app.celery_app import celery_app
from app.core.document.pdf_processor import run_ocr_pipeline, run_gpt_pipeline, DEFAULT_JANZOUR_PROMPT, DEFAULT_MASSARA_PROMPT

# Define Prompt Constants
JANZOUR_GPT_PROMPT = DEFAULT_JANZOUR_PROMPT
MASSARA_GPT_PROMPT = DEFAULT_MASSARA_PROMPT
from app.core.document.janzour_processor import process_janzour_pdf
from app.core.document.massara_processor import process_massara_pdf
from app.core.document.validator import validate_json_with_images
from app.core.notifications import publish_update
from app.config import settings

# Directory to store results
RESULTS_DIR = "storage/results"
INTERIM_DIR = "storage/interim"
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(INTERIM_DIR, exist_ok=True)

def get_result_path(task_id: str):
    return os.path.join(RESULTS_DIR, f"{task_id}.json")

async def progress_callback_wrapper(task_id, event, data):
    # Wrapper to publish updates to Redis
    # We include task_id and pdf_name in every update if possible, 
    # but the caller of this wrapper doesn't know pdf_name explicitly unless we pass it.
    # The requirement: "return it along with each stream" (the pdf name).
    # We can retrieve pdf_name from data if we want, or pass it in wrapper.
    # Let's assume the data payload is enough, and we wrap it.
    
    payload = {
        "task_id": task_id,
        "event": event,
        "data": data
    }
    publish_update(task_id, payload)

@celery_app.task(bind=True, name="app.tasks.process_document_pipeline")
def process_document_pipeline(self, pdf_path: str, original_filename: str, batch_id: str = None):
    """
    Orchestrator task.
    This runs OCR then chains to GPT.
    """
    task_id = self.request.id
    
    # Notify start
    publish_update(task_id, {
        "task_id": task_id,
        "filename": original_filename,
        "batch_id": batch_id,
        "status": "started",
        "message": f"Started processing {original_filename}"
    })
    
    # We use chain to ensure strict ordering: OCR -> GPT
    # But we want to pass the result of OCR to GPT.
    # Celery chain passes return value of parent to child.
    
    chain(
        process_ocr_task.s(pdf_path, original_filename, task_id, batch_id),
        process_gpt_extraction.s(original_filename, task_id, batch_id),
        process_validation_task.s(original_filename, task_id, batch_id)
    ).apply_async()



@celery_app.task(bind=True, name="app.tasks.process_ocr_task")
def process_ocr_task(self, pdf_path: str, original_filename: str, parent_task_id: str, batch_id: str = None):

    """
    Task to run OCR.
    """
    # Use parent_task_id for consistent updates
    task_id = parent_task_id
    
    async def run_ocr():
        # Create a persistent interim dir for this task to store images
        task_interim_dir = os.path.join(INTERIM_DIR, task_id)
        os.makedirs(task_interim_dir, exist_ok=True)
        
        async def callback(event, data):
             # Inject filename into data if needed
             msg = {
                "task_id": task_id,
                "filename": original_filename,
                "event": event,
                "data": data
             }
             publish_update(task_id, msg)
         
        try:
             text, skipped = await run_ocr_pipeline(pdf_path, task_interim_dir, progress_callback=callback)
             
             # Collect image paths recursively
             image_paths = []
             if os.path.exists(task_interim_dir):
                 for root, dirs, files in os.walk(task_interim_dir):
                     for file in files:
                         if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                             image_paths.append(os.path.join(root, file))
                 image_paths.sort() # Ensure consistent order
             
             return {"text": text, "skipped": skipped, "pdf_path": pdf_path, "image_paths": image_paths}
        except Exception as e:
             # Send failure notification
             publish_update(task_id, {
                 "task_id": task_id,
                 "filename": original_filename,
                 "event": "error",
                 "data": {"message": f"OCR failed: {str(e)}"}
             })
             raise e 

    # Run async code in sync task
    try:
        return asyncio.run(run_ocr())
    except Exception as e:
        # Failure is handled in run_ocr exception but re-raising for Celery
        raise e

@celery_app.task(bind=True, name="app.tasks.process_gpt_extraction")
def process_gpt_extraction(self, ocr_result: dict, original_filename: str, parent_task_id: str, batch_id: str = None, template: str = None):
    """
    Task to run GPT extraction.
    """
    task_id = parent_task_id
    
    # Log the input for debugging
    print(f"DEBUG: GPT Extraction received task {task_id} for {original_filename}")
    if not isinstance(ocr_result, dict):
        print(f"ERROR: ocr_result is not a dict! Type: {type(ocr_result)}")
        return {"error": "Invalid OCR result type"}
    
    text = ocr_result.get("text", "")
    skipped_pages = ocr_result.get("skipped", [])
    image_paths = ocr_result.get("image_paths", [])
    
    print(f"DEBUG: [{task_id}] OCR Text Length: {len(text)}, Pages Skipped: {len(skipped_pages)}")

    
    def run_gpt():
        async def main_async():
            if not text:
                publish_update(task_id, {
                    "task_id": task_id,
                    "filename": original_filename,
                    "batch_id": batch_id,
                    "event": "completed",
                    "data": {"result": {}, "message": "No text detected in OCR"}
                })
                return {}

            async def callback(event, data):
                 msg = {
                    "task_id": task_id,
                    "filename": original_filename,
                    "batch_id": batch_id,
                    "event": event,
                    "data": data
                 }
                 publish_update(task_id, msg)
            
            # Notify GPT starting
            print(f"DEBUG: [{task_id}] GPT extraction starting for {original_filename}. Text length: {len(text)}")
            await callback("progress", {"step": "gpt_start", "message": f"Initializing GPT extraction ({len(text)} chars)"})
            
            try:
                 # Determine prompt based on template
                 prompt = None
                 if template in ["janzour", "safwa"]:
                     prompt = JANZOUR_GPT_PROMPT
                 elif template in ["massara", "muasafat", "musafat"]:
                     prompt = MASSARA_GPT_PROMPT
                 
                 json_result_str = await run_gpt_pipeline(text, progress_callback=callback, system_prompt=prompt)
                 print(f"DEBUG: [{task_id}] GPT extraction pipeline finished. Response length: {len(json_result_str) if json_result_str else 0}")
                 return json_result_str
            except Exception as e:
                 raise e

        try:
             json_result_str = asyncio.run(main_async())
             parsed_result = None


             if json_result_str:
                 try:
                     parsed_result = json.loads(json_result_str)
                 except:
                     parsed_result = {"raw_response": json_result_str}
             
             # Construct final result object
             result_data = {
                 "task_id": task_id,
                 "filename": original_filename,
                 "batch_id": batch_id,
                 "processed_at": time.time(),
                 "result": parsed_result,
                 "result": parsed_result,
                 "raw_text": text[:50000] + "..." if len(text) > 50000 else text, 
                 "skipped": skipped_pages,
                 "image_paths": image_paths
             }
             
             # Notify completion of extraction step (NOT final completion)
             publish_update(task_id, {
                 "task_id": task_id,
                 "filename": original_filename,
                 "batch_id": batch_id,
                 "event": "step_completed", 
                 "data": {"step": "extraction", "message": "GPT extraction complete"}
             })
             
             return result_data
             
        except Exception as e:
             publish_update(task_id, {
                 "task_id": task_id,
                 "filename": original_filename,
                 "batch_id": batch_id, 
                 "event": "error",
                 "data": {"message": f"GPT failed: {str(e)}"}
             })
             if batch_id:
                 from redis import Redis
                 r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
                 remaining = r.decr(f"batch_count:{batch_id}")
                 if remaining <= 0:
                      publish_update(task_id, {
                         "event": "batch_completed",
                         "batch_id": batch_id,
                         "message": "All PDFs in this batch have been processed (with errors)."
                     })
             raise e

    return run_gpt()


@celery_app.task(bind=True, name="app.tasks.process_validation_task")
def process_validation_task(self, extraction_result: dict, original_filename: str, parent_task_id: str, batch_id: str = None):
    """
    Task to validate extracted JSON against images.
    """
    task_id = parent_task_id
    
    print(f"DEBUG: Validation task received for {task_id}")
    
    if "error" in extraction_result:
        return extraction_result

    image_paths = extraction_result.get("image_paths", [])
    json_result = extraction_result.get("result", {})
    
    # Notify start
    publish_update(task_id, {
        "task_id": task_id,
        "filename": original_filename,
        "batch_id": batch_id,
        "event": "progress",
        "data": {"step": "validation", "message": "Validating extraction against document images"}
    })

    try:
        validation_review = validate_json_with_images(image_paths, json_result)
        
        # Add review to result
        final_result = extraction_result.copy()
        final_result["validation_review"] = validation_review
        
        # Determine if failed based on score (optional logic, just including checking for now)
        # score = validation_review.get("score", 0)
        
        # Cleanup images
        task_interim_dir = os.path.join(INTERIM_DIR, task_id)
        if os.path.exists(task_interim_dir):
            import shutil
            try:
                shutil.rmtree(task_interim_dir)
            except Exception as cleanup_err:
                print(f"Error cleaning up interim dir {task_interim_dir}: {cleanup_err}")

        # Remove image_paths from final output as they are deleted
        if "image_paths" in final_result:
            del final_result["image_paths"]

        # Notify FINAL completion
        publish_update(task_id, {
             "task_id": task_id,
             "filename": original_filename,
             "batch_id": batch_id,
             "event": "completed", 
             "data": final_result
        })

        # Check for Batch Completion
        if batch_id:
             from redis import Redis
             r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
             remaining = r.decr(f"batch_count:{batch_id}")
             
             if remaining <= 0:
                 publish_update(task_id, {
                     "event": "batch_completed",
                     "batch_id": batch_id,
                     "message": "All PDFs in this batch have been processed."
                 })
                 r.delete(f"batch_count:{batch_id}")
        
        return final_result

    except Exception as e:
        print(f"Validation failed: {e}")
        # Even if validation fails, return the extraction result but mark error
        extraction_result["validation_error"] = str(e)
        
        publish_update(task_id, {
             "task_id": task_id,
             "filename": original_filename,
             "batch_id": batch_id,
             "event": "completed", 
             "data": extraction_result
        })
        return extraction_result




@celery_app.task(name="app.tasks.cleanup_old_results")
def cleanup_old_results():
    """
    Periodic task to delete files older than 72 hours.
    """
    now = time.time()
    cutoff = now - settings.TASK_RESULT_EXPIRE_TIME
    
    count = 0
    if os.path.exists(RESULTS_DIR):
        for fname in os.listdir(RESULTS_DIR):
            fpath = os.path.join(RESULTS_DIR, fname)
            if os.path.isfile(fpath):
                mtime = os.path.getmtime(fpath)
                if mtime < cutoff:
                    try:
                        os.remove(fpath)
                        count += 1
                    except Exception as e:
                        print(f"Error deleting {fpath}: {e}")
    
    print(f"Cleanup: Removed {count} old result files.")


# ============================================================================
# TEMPLATE-SPECIFIC TASKS - Janzour/Safwa and Massara/Muasafat
# ============================================================================

@celery_app.task(bind=True, name="app.tasks.process_janzour_pipeline")
def process_janzour_pipeline(self, pdf_path: str, original_filename: str, batch_id: str = None):
    """
    Orchestrator task for Janzour template (also used for Safwa).
    Chains OCR -> GPT extraction.
    """
    task_id = self.request.id
    
    # Notify start
    publish_update(task_id, {
        "task_id": task_id,
        "filename": original_filename,
        "batch_id": batch_id,
        "status": "started",
        "template": "janzour",
        "message": f"Started processing {original_filename} (Janzour template)"
    })
    
    chain(
        process_janzour_ocr_task.s(pdf_path, original_filename, task_id, batch_id),
        process_gpt_extraction.s(original_filename, task_id, batch_id, template="janzour"),
        process_validation_task.s(original_filename, task_id, batch_id)
    ).apply_async()


@celery_app.task(bind=True, name="app.tasks.process_janzour_ocr_task")
def process_janzour_ocr_task(self, pdf_path: str, original_filename: str, parent_task_id: str, batch_id: str = None):
    """
    Task to run OCR using Janzour processor.
    """
    task_id = parent_task_id
    
    async def run_janzour_ocr():
        # Create a persistent interim dir for this task
        task_interim_dir = os.path.join(INTERIM_DIR, task_id)
        os.makedirs(task_interim_dir, exist_ok=True)

        async def callback(event, data):
            msg = {
                "task_id": task_id,
                "filename": original_filename,
                "template": "janzour",
                "event": event,
                "data": data
            }
            publish_update(task_id, msg)
        
        try:
            text, skipped = await process_janzour_pdf(pdf_path, task_interim_dir, progress_callback=callback)
            
            # Collect image paths recursively
            image_paths = []
            if os.path.exists(task_interim_dir):
                for root, dirs, files in os.walk(task_interim_dir):
                    for file in files:
                        if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                            image_paths.append(os.path.join(root, file))
                image_paths.sort()

            return {"text": text, "skipped": skipped, "pdf_path": pdf_path, "image_paths": image_paths}
        except Exception as e:
            publish_update(task_id, {
                "task_id": task_id,
                "filename": original_filename,
                "template": "janzour",
                "event": "error",
                "data": {"message": f"Janzour OCR failed: {str(e)}"}
            })
            raise e

    try:
        return asyncio.run(run_janzour_ocr())
    except Exception as e:
        raise e


@celery_app.task(bind=True, name="app.tasks.process_massara_pipeline")
def process_massara_pipeline(self, pdf_path: str, original_filename: str, batch_id: str = None):
    """
    Orchestrator task for Massara template (also used for Muasafat).
    Chains OCR -> GPT extraction.
    """
    task_id = self.request.id
    
    # Notify start
    publish_update(task_id, {
        "task_id": task_id,
        "filename": original_filename,
        "batch_id": batch_id,
        "status": "started",
        "template": "massara",
        "message": f"Started processing {original_filename} (Massara template)"
    })
    
    chain(
        process_massara_ocr_task.s(pdf_path, original_filename, task_id, batch_id),
        process_gpt_extraction.s(original_filename, task_id, batch_id, template="massara"),
        process_validation_task.s(original_filename, task_id, batch_id)
    ).apply_async()


@celery_app.task(bind=True, name="app.tasks.process_massara_ocr_task")
def process_massara_ocr_task(self, pdf_path: str, original_filename: str, parent_task_id: str, batch_id: str = None):
    """
    Task to run OCR using Massara processor.
    """
    task_id = parent_task_id
    
    async def run_massara_ocr():
        # Create a persistent interim dir for this task
        task_interim_dir = os.path.join(INTERIM_DIR, task_id)
        os.makedirs(task_interim_dir, exist_ok=True)
        
        async def callback(event, data):
            msg = {
                "task_id": task_id,
                "filename": original_filename,
                "template": "massara",
                "event": event,
                "data": data
            }
            publish_update(task_id, msg)
        
        try:
            text, skipped = await process_massara_pdf(pdf_path, task_interim_dir, progress_callback=callback)
            
            # Collect image paths recursively
            image_paths = []
            if os.path.exists(task_interim_dir):
                for root, dirs, files in os.walk(task_interim_dir):
                    for file in files:
                        if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                            image_paths.append(os.path.join(root, file))
                image_paths.sort()

            return {"text": text, "skipped": skipped, "pdf_path": pdf_path, "image_paths": image_paths}
        except Exception as e:
            publish_update(task_id, {
                "task_id": task_id,
                "filename": original_filename,
                "template": "massara",
                "event": "error",
                "data": {"message": f"Massara OCR failed: {str(e)}"}
            })
            raise e

    try:
        return asyncio.run(run_massara_ocr())
    except Exception as e:
        raise e
