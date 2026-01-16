#!/bin/bash

# Navigate to project root
cd /home/user/ocrscript

# Activate venv
source venv/bin/activate

# Kill existing services
echo "Cleaning up existing services..."
fuser -k 5000/tcp >> /dev/null 2>&1
pkill -9 -f "celery worker" >> /dev/null 2>&1
pkill -9 -f "celery beat" >> /dev/null 2>&1
pkill -9 -f "uvicorn" >> /dev/null 2>&1
rm -f services.log


# Start Redis if not running

if ! pgrep -x "redis-server" > /dev/null
then
    echo "Starting Redis..."
    ./redis-stable/src/redis-server --daemonize yes
else
    echo "Redis is already running."
fi

# Start Celery Worker for Batch OCR (GPU-bound, 1 concurrent)
echo "Starting Celery Batch OCR Worker..."
celery -A app.celery_app worker -Q batch_ocr -c 1 -n batch_ocr_worker --loglevel=info >> services.log 2>&1 &

# Start Celery Worker for General OCR (General tasks)
echo "Starting Celery General Worker..."
celery -A app.celery_app worker -Q celery -c 1 -n ocr_worker --loglevel=info >> services.log 2>&1 &

# Start Celery Worker for GPT (I/O-bound, 20 concurrent)
echo "Starting Celery GPT Worker..."
celery -A app.celery_app worker -Q gpt -c 20 -n gpt_worker --loglevel=info >> services.log 2>&1 &

# Start Celery Beat for periodic cleanup
echo "Starting Celery Beat..."
celery -A app.celery_app beat --loglevel=info >> services.log 2>&1 &

# Wait a bit for workers to init
sleep 3

# Start FastAPI
echo "Starting FastAPI..."
uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload >> services.log 2>&1


