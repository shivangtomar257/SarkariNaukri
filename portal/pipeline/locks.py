from contextlib import contextmanager
from django.conf import settings
try:
    import redis
except ImportError:
    redis = None

@contextmanager
def redis_lock(name: str, ttl: int = 900):
    if redis is None:
        yield True; return
    client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
    key = f"sn:lock:{name}"
    token = client.set(key, "1", nx=True, ex=ttl)
    try:
        yield bool(token)
    finally:
        if token:
            client.delete(key)
