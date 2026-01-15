from celery import Celery
from celery.signals import worker_process_init
from app.config import settings
from app.models.ml_models import model_manager

@worker_process_init.connect
def init_models(**kwargs):
    print("🤖 Worker process initializing models...")
    model_manager.initialize_all()


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
    # Route GPT tasks to their own queue to control concurrency
    task_routes={
        "app.tasks.process_gpt_extraction": {"queue": "gpt_queue"},
        "app.tasks.*": {"queue": "celery"},
    },
    include=["app.tasks"],
    beat_schedule={
        "cleanup-every-hour": {
            "task": "app.tasks.cleanup_old_results",
            "schedule": 3600.0, # Every hour
        },
    }
)

