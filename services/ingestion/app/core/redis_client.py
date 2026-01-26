import redis.asyncio as redis

from app.core.config import settings

# Create the Redis client instance
redis_client = redis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
)


async def get_redis_client():
    """Dependency to get the Redis Client"""
    try:
        yield redis_client
    finally:
        # Not closing the connection to reuse the pool
        pass
