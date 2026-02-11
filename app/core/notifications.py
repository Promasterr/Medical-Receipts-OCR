import json
import redis
import asyncio
from app.config import settings

# Global Redis client for async operations in FastAPI
# We will initialize this in main startup
redis_client = None

# Shared Redis client for notifications
_redis_sync = None

def get_redis_sync():
    global _redis_sync
    if _redis_sync is None:
        _redis_sync = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_sync

def publish_update(task_id: str, message: dict):
    """
    Publish an update for a specific task to Redis channel.
    """
    r = get_redis_sync()
    channel = f"task_updates:{task_id}"
    # Ensure message is a string
    try:
        r.publish(channel, json.dumps(message, ensure_ascii=False))
    except Exception as e:
        print(f"FAILED TO PUBLISH: {e}")


# Async version for FastAPI/AsyncIO context if needed
async def async_publish_update(redis_conn, task_id: str, message: dict):
    channel = f"task_updates:{task_id}"
    await redis_conn.publish(channel, json.dumps(message, ensure_ascii=False))
