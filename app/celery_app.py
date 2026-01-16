from celery import Celery
from celery.signals import worker_process_init
from app.config import settings
from app.models.ml_models import model_manager

@worker_process_init.connect
def init_models(**kwargs):
    print("🤖 Worker process initializing... Models will be lazy-loaded on demand.")
    # Removed explicit initialize_all() to prevents OOM in GPT workers
    # model_manager.initialize_all()


celery_app = Celery(
    "ocr_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task routing for optimized concurrency
    task_routes={
        # Batch pipeline tasks (GPU-bound, run 1 at a time)
        "app.tasks.process_janzour_batch_pipeline": {"queue": "batch_ocr"},
        "app.tasks.process_massara_batch_pipeline": {"queue": "batch_ocr"},
        
        # GPT tasks (I/O-bound, high concurrency)
        "app.tasks.process_gpt_extraction": {"queue": "gpt"},
        "app.tasks.process_gpt_extraction_from_file": {"queue": "gpt"},
        
        # Default queue for other tasks
        "app.tasks.*": {"queue": "celery"},
    },
    
    # Prevent task argument bloat in Redis
    task_compression="gzip",
    result_expires=3600,  # Clean up results after 1 hour
    
    include=["app.tasks"],
    beat_schedule={
        "cleanup-every-hour": {
            "task": "app.tasks.cleanup_old_results",
            "schedule": 3600.0, # Every hour
        },
    }
)

# Worker startup documentation
# 
# To start workers with optimized concurrency:
#
# # Batch OCR worker (GPU-bound, 1 concurrent task)
# celery -A app.celery_app worker -Q batch_ocr -c 1 --loglevel=info
#
# # GPT extraction worker (I/O-bound, 20 concurrent tasks)
# celery -A app.celery_app worker -Q gpt -c 20 --loglevel=info
#
# # Default worker (general tasks)
# celery -A app.celery_app worker -Q celery -c 4 --loglevel=info
#
# # Beat scheduler (periodic tasks)
# celery -A app.celery_app beat --log level=info


